"""Equal-budget actual SAM prompt comparison; synthetic GT vs public no-GT cases."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.feature_prompts import propose
from tem_analyzer.prompts import grid_points
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.ocr import read_words
from tem_analyzer.algorithms.annotations import propose_annotations
from tem_analyzer.operations import excluded


def main(args):
    import torch
    torch.set_num_threads(4);out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory.')
    out.mkdir(parents=True);project=Project(out/'project');cases=[];rng=np.random.default_rng(32)
    for angle in (0,25,-45):
        yy,xx=np.mgrid[:256,:384];phase=(yy-128)*np.cos(np.deg2rad(angle))-(xx-192)*np.sin(np.deg2rad(angle))
        gray=np.full((256,384),80.,float);truth=[]
        for level,width,value in [(-50,4,210),(-25,6,20),(0,10,200),(35,5,15)]:
            m=(phase>=level)&(phase<level+width);gray[m]=value;truth.append(m)
        gray=np.uint8(np.clip(gray+rng.normal(0,5,gray.shape),0,255));im=np.repeat(gray[...,None],3,2)
        path=out/f'synthetic_{angle:+03d}.png';Image.fromarray(im).save(path)
        cases.append(dict(name=path.stem,path=str(path),truth=truth))
    wanted=set(args.names.split(','));public=json.loads(Path(args.cases).read_text(encoding='utf8'))
    cases.extend(c for c in public if c['name'] in wanted)
    model=ModelService();model.load(args.checkpoint,'vit_b','cpu');report=dict(rows=[],contract='Equal nominal16 points; native SAM multi-mask, cold encoder each run, pred .5/stability .7/NMS .8. Synthetic four bands are exact generated GT. Public images have NO expert GT; counts/coverage are not accuracy.')
    for case in cases:
        image=np.array(Image.open(case['path']).convert('RGB'));h,w=image.shape[:2]
        if 'truth' in case:annotation=None;ex=np.zeros((h,w),bool)
        else:
            annotation=propose_annotations(image,read_words(image,args.ocr_dir,'en',enhanced=True));ex=excluded((h,w),annotation['template'])
        basecfg=dict(count=16,denoise='median',edge_clearance=1,min_distance=8)
        profilecfg=dict(basecfg,method='profile',profile_max_width=40,analysis_side=1024)
        profile=propose(image,ex,config=profilecfg,preview=True)
        recipes={'grid':(grid_points((h,w),4,ex),{}),'sobel':(propose(image,ex,config=dict(basecfg,method='sobel'))['points'],dict(basecfg,method='sobel')),
                 'profile':(profile['points'],profilecfg)}
        mixed=grid_points((h,w),3,ex);mcfg=dict(profilecfg,count=max(1,16-len(mixed)))
        mixed+=propose(image,ex,mixed,mcfg)['points'];recipes['grid_profile']=(mixed,mcfg)
        for strategy,(points,cfg) in recipes.items():
            iid=project.add_image(Path(case['path']).read_bytes(),case['name']+'_'+strategy+'.png')
            if annotation:project.state['preprocessing'][iid]['auto_regions']=annotation['template'];project.state.setdefault('annotation_proposals',{})[iid]=annotation
            project.state.setdefault('prepared_prompts',{})[iid]=dict(auto_points=points,settings=cfg,source='compare-profile')
            model.image_key=None;model.predictor.reset_image();start=time.perf_counter()
            items=model.automatic(image,prepared_points=points,exclude=ex,pred_iou=.5,stability=.7,nms=.8) if points else []
            seconds=time.perf_counter()-start;masks=[];canvas=image.astype(float);cids=[]
            for j,item in enumerate(items):
                m=item['mask']&~ex;masks.append(m)
                c=project.put_candidate(iid,m,'profile-comparison-'+strategy,score=float(item['score']));cids.append(c['id'])
                color=np.array([(43*j+20)%255,(91*j+200)%255,(137*j+65)%255]);canvas[m]=canvas[m]*.55+color*.45
            im=Image.fromarray(np.uint8(canvas));draw=ImageDraw.Draw(im)
            for x,y in points:draw.ellipse((x-2,y-2,x+2,y+2),fill='cyan')
            filename=case['name']+'_'+strategy+'.png';im.save(out/filename)
            row=dict(case=case['name'],strategy=strategy,image_id=iid,candidate_ids=cids,prompt_count=len(points),mask_count=len(items),seconds=seconds,points=points,overlay=filename,settings=cfg,
                     profile_diagnostics=profile['diagnostics'],profile_warnings=profile['warnings'])
            if 'truth' in case:
                row['band_point_hits']=[any(t[int(y),int(x)] for x,y in points) for t in case['truth']]
                row['best_iou_per_band']=[max((float((m&t).sum()/max(1,(m|t).sum())) for m in masks),default=0.) for t in case['truth']]
            report['rows'].append(row);project.save();(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps({k:row[k] for k in ('case','strategy','prompt_count','mask_count','seconds','band_point_hits','best_iou_per_band') if k in row}),flush=True)
    print('COMPLETE',len(report['rows']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',required=True);p.add_argument('--names',default='existing_140,existing_158,new_hafnia_h')
    p.add_argument('--checkpoint',required=True);p.add_argument('--ocr-dir',required=True);p.add_argument('--output',required=True);main(p.parse_args())
