"""Real SAM controlled comparison. Counts/coverage are NOT segmentation accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.sam_service import ModelService
from tem_analyzer.prompts import grid_points
from tem_analyzer.feature_prompts import propose
from tem_analyzer.operations import excluded
from tem_analyzer.algorithms.annotations import propose_annotations
from tem_analyzer.ocr import read_words
from tem_analyzer.storage import Project


def main(a):
    import torch
    torch.set_num_threads(4)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    report_path=out/'results.json'
    if report_path.exists():raise ValueError('Use a new output directory: existing results are preserved.')
    records=json.loads(Path(a.cases).read_text(encoding='utf8'))
    if isinstance(records,dict):records=records['cases']
    wanted=set(a.names.split(','));records=[r for r in records if r['name'] in wanted]
    records.append(dict(name='attached_45deg',path=a.attached))
    project=Project(out/'project');model=ModelService();start=time.perf_counter();model.load(a.checkpoint,'vit_b','cpu')
    report=dict(model=model.info.copy(),load_seconds=time.perf_counter()-start,rows=[],
                contract='No expert GT. Coverage/overlap/counts are not accuracy. Fresh encoder for EVERY run. Same SAM thresholds across strategies. Nominal 16 prompts; actual count recorded. No model/image uploads.')
    for case in records:
        image=np.array(Image.open(case['path']).convert('RGB'));name=case['name'];h,w=image.shape[:2]
        annotation=propose_annotations(image,read_words(image,a.ocr_dir,'en',enhanced=True))
        ex=excluded((h,w),annotation['template'])
        # SAME raw image, excluding prompt locations and final mask pixels in every mode.
        # Avoid conflating prompt strategy with nearest-neighbour fill/filter changes.
        recipes={
            'grid':grid_points((h,w),4,ex),
            'sobel':propose(image,ex,config=dict(method='sobel',count=16,denoise='median'))['points'],
            'hybrid':propose(image,ex,config=dict(method='hybrid',count=16,denoise='median'))['points']}
        mixed=grid_points((h,w),3,ex)
        mixed+=propose(image,ex,mixed,dict(method='sobel',count=max(1,16-len(mixed)),denoise='median'))['points']
        recipes['grid_features']=mixed
        for decoder in ('legacy_single','native_multi'):
            model.info['single_mask']=decoder=='legacy_single'
            for strategy,points in recipes.items():
                iid=project.add_image(Path(case['path']).read_bytes(),f'{name}_{decoder}_{strategy}.png')
                project.state['preprocessing'][iid]['auto_regions']=annotation['template']
                model.image_key=None;model.predictor.reset_image()
                start=time.perf_counter();items=model.automatic(image,pred_iou=.5,stability=.7,nms=.8,exclude=ex,prepared_points=points)
                seconds=time.perf_counter()-start;counts=np.zeros((h,w),np.uint16);overlay=image.astype(float)
                candidate_ids=[]
                for j,item in enumerate(items):
                    m=item['mask']&~ex;counts+=m
                    c=project.put_candidate(iid,m,f'compare-{strategy}',score=float(item['score']));candidate_ids.append(c['id'])
                    color=np.array([(71*j+50)%255,(131*j+80)%255,(193*j+100)%255]);overlay[m]=.6*overlay[m]+.4*color
                image_out=Image.fromarray(np.uint8(overlay));draw=ImageDraw.Draw(image_out)
                for x,y in points:draw.ellipse((x-2,y-2,x+2,y+2),fill='cyan')
                filename=f'{name}_{decoder}_{strategy}.png';image_out.save(out/filename)
                row=dict(case=name,image_id=iid,decoder=decoder,strategy=strategy,prompt_count=len(points),points=points,
                         candidate_ids=candidate_ids,mask_count=len(items),seconds=seconds,overlay=filename,
                         image_sha256=hashlib.sha256(image.tobytes()).hexdigest(),covered_fraction=float((counts>0).sum()/max(1,(~ex).sum())),
                         overlap_fraction=float((counts>1).sum()/max(1,(~ex).sum())),thresholds=dict(pred_iou=.5,stability=.7,nms=.8),
                         scale=annotation['scale'].get('nm_per_px'),encoder='cold-every-run')
                report['rows'].append(row);report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');project.save()
                print(name,decoder,strategy,len(points),len(items),round(seconds,2),flush=True)
    print('COMPLETE',len(report['rows']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',required=True);p.add_argument('--attached',required=True);p.add_argument('--output',required=True)
    p.add_argument('--checkpoint',required=True);p.add_argument('--ocr-dir',required=True);p.add_argument('--names',default='existing_43,existing_55,existing_76,existing_140,existing_143');main(p.parse_args())
