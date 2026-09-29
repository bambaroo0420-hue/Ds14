"""Reproducible public-image robustness audit; no GT accuracy claims or training."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import zipfile
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.feature_prompts import propose
from tem_analyzer.preprocessing import exclusion_mask, model_input
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.ocr import read_words
from tem_analyzer.algorithms.annotations import propose_annotations


def sheet(images,path,columns=4,tile=(280,270)):
    canvas=Image.new('RGB',(columns*tile[0],((len(images)+columns-1)//columns)*tile[1]),'#222222')
    draw=ImageDraw.Draw(canvas)
    for i,(label,im) in enumerate(images):
        copy=im.copy();copy.thumbnail((tile[0]-10,tile[1]-34))
        x,y=(i%columns)*tile[0],(i//columns)*tile[1]
        canvas.paste(copy,(x+(tile[0]-copy.width)//2,y+28));draw.text((x+5,y+5),label,fill='white')
    canvas.save(path)


def prepare(collection,out):
    out.mkdir(parents=True,exist_ok=True);case_dir=out/'cases';case_dir.mkdir(exist_ok=True)
    records=[];manifest=json.loads((collection/'manifest.json').read_text(encoding='utf8'))
    for original in manifest:
        if original['id'] not in (43,55,58,76,140,143,153,157,158,172):continue
        path=collection/original['file'];im=Image.open(path).convert('RGB');name=f"existing_{original['id']}"
        target=case_dir/(name+'.png');im.save(target)
        records.append(dict(name=name,path=str(target.resolve()),source=original['url'],source_title=original['source'],
            original_file=original['file'],source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            license=original['license_status'],group=original['group'],kind=original['category'],transform='existing collection crop; no new geometric transform'))
    path=out/'new'/'hafnia_fig1.jpg';im=Image.open(path).convert('RGB');w,h=im.size
    for name,box in [('new_hafnia_b',(.236,.042,.330,.492)),('new_hafnia_h',(.711,.551,1.,.980))]:
        rect=[round(box[0]*w),round(box[1]*h),round(box[2]*w),round(box[3]*h)];target=case_dir/(name+'.png');im.crop(rect).save(target)
        records.append(dict(name=name,path=str(target.resolve()),source='https://pmc.ncbi.nlm.nih.gov/articles/PMC13201757/',
            source_title='Geng et al. Roadmap of phase transitions in hafnia-based superlattice films (2026)',
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),license='CC BY 4.0',group='PMC13201757',
            kind='superlattice / atomic contrast',transform={'crop_xyxy':rect,'source_size':[w,h]}))
    path=out/'new'/'TEM.zip'
    if hashlib.md5(path.read_bytes()).hexdigest()!='8acf6e93baa88fadf26d0bd6a3f80395':raise ValueError('Public ZIP checksum mismatch')
    with zipfile.ZipFile(path) as z:
        for i,name in enumerate(n for n in z.namelist() if n.lower().endswith('.tif')):
            # Read image bytes only; never extract archive paths or execute contents.
            raw=z.read(name);src=Image.open(io.BytesIO(raw));arr=np.asarray(src);transform={'source_mode':src.mode,'source_size':src.size}
            if src.mode not in ('RGB','RGBA','L','P'):
                lo,hi=np.percentile(arr,[.1,99.9]);arr=np.uint8(np.clip((arr.astype(float)-lo)/max(hi-lo,1e-9),0,1)*255)
                src=Image.fromarray(arr);transform['explicit_8bit_percentiles']=[float(lo),float(hi)]
            im=src.convert('RGB');im.thumbnail((768,768));transform['evaluation_size']=im.size
            target=case_dir/f'new_gold_{i+1}.png';im.save(target)
            records.append(dict(name=f'new_gold_{i+1}',path=str(target.resolve()),source='https://doi.org/10.18150/SDSH8E',
                source_title='Kravets (2026), Raw Data for Confined Reactions under Light-Driven Monolayer Compaction',
                original_file=name,source_sha256=hashlib.sha256(raw).hexdigest(),license='CC0 (repository file listing)',
                group='SDSH8E',kind='gold particles (out-of-domain control)',transform=transform))
    (out/'cases.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    sheet([(r['name'],Image.open(r['path']).convert('RGB')) for r in records],out/'contact.png')
    return records


def main(args):
    out=Path(args.output);records=prepare(Path(args.collection),out)
    if args.prepare_only:print('Prepared',len(records),'cases');return
    import torch
    torch.set_num_threads(4)
    model=ModelService();model.load(args.checkpoint,'vit_b','cpu')
    project=Project(out/'audit-project');report=[];masks_sheet=[];prompt_sheet=[];ocr_sheet=[]
    for case in records:
        im=np.asarray(Image.open(case['path']).convert('RGB'));h,w=im.shape[:2];t=time.perf_counter()
        iid=project.add_image(Path(case['path']).read_bytes(),case['name']+'.png')
        row=dict(case=case['name'],image_id=iid,shape=[h,w],prompt_tests=[],sam_tests=[])
        try:
            ocr=propose_annotations(im,read_words(im,args.ocr_dir,'en'));row['ocr']=ocr
            # Proposals stay unconfirmed. Exclusions are applied to this disposable audit only.
            project.state['preprocessing'][iid]['auto_regions']=ocr['template']
            pic=Image.fromarray(im);d=ImageDraw.Draw(pic)
            for region in ocr['regions']:d.rectangle(region['box'],outline='red',width=2)
            ocr_sheet.append((case['name'],pic))
        except Exception as exc:row['ocr_error']=str(exc)
        try:
            clean=model_input(project,iid,'prompt');excluded=exclusion_mask(project,iid)
            for method in ('kmeans','canny','sobel','scharr','hybrid'):
                for denoise in ('none','gaussian','median','bilateral','nlm'):
                    start=time.perf_counter();result=propose(clean,excluded,config={'method':method,'denoise':denoise,'count':12},preview=denoise=='median')
                    row['prompt_tests'].append(dict(method=method,denoise=denoise,count=result['count'],seconds=time.perf_counter()-start,warnings=result['warnings']))
                    if denoise=='median':
                        pic=Image.open(io.BytesIO(base64.b64decode(result['proposal_preview'].split(',')[1]))).convert('RGB')
                        if method in ('kmeans','canny','sobel'):prompt_sheet.append((case['name']+' '+method,pic))
                    if method not in ('kmeans','canny','sobel') or denoise!='median':continue
                    start=time.perf_counter();items=model.automatic(clean,pred_iou=.5,stability=.7,nms=.8,exclude=excluded,prepared_points=result['points'])
                    counts=np.zeros((h,w),np.uint16);overlay=im.copy().astype(float)
                    for j,item in enumerate(items):
                        m=item['mask']&~excluded;counts+=m
                        color=np.array([(71*j+50)%255,(131*j+80)%255,(193*j+100)%255]);overlay[m]=.6*overlay[m]+.4*color
                        saved=project.put_candidate(iid,m,'public-audit-'+method);saved['reviewed']=False
                    valid=max(1,int((~excluded).sum()))
                    row['sam_tests'].append(dict(method=method,prompts=result['count'],candidates=len(items),seconds=time.perf_counter()-start,
                        covered_fraction=float((counts>0).sum()/valid),overlap_fraction=float((counts>1).sum()/valid),
                        note='No GT; coverage and overlap are NOT accuracy. pred_iou=.5 stability=.7 nms=.8; median for prompts only'))
                    masks_sheet.append((case['name']+' '+method,Image.fromarray(np.uint8(overlay))))
            row['seconds']=time.perf_counter()-t
        except Exception as exc:row['error']=str(exc)
        report.append(row);project.save()
        (out/'results.json').write_text(json.dumps(dict(cases=records,results=report,model=model.info),ensure_ascii=False,indent=2),encoding='utf8')
        print(case['name'],'prompts',len(row['prompt_tests']),'SAM',[(s['method'],s['candidates']) for s in row['sam_tests']],row.get('error',''),flush=True)
    sheet(masks_sheet,out/'sam_contact.png',columns=3);sheet(prompt_sheet,out/'prompt_contact.png',columns=3)
    sheet(ocr_sheet,out/'ocr_contact.png')
    print('COMPLETE',len(report),'images',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--collection',required=True);p.add_argument('--output',required=True)
    p.add_argument('--checkpoint');p.add_argument('--ocr-dir');p.add_argument('--prepare-only',action='store_true');main(p.parse_args())
