"""Inspect all three base-SAM ROI outputs; never label score as GT accuracy."""
import argparse,copy,io,json,sys,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.preprocessing import model_input,exclusion_mask
from tem_analyzer.v2_api import save_prediction
from tem_analyzer.algorithms.metrology import edge_points,robust_line


def main(args):
    import torch
    torch.set_num_threads(4);source=Path(args.source);out=Path(args.output)
    if out.exists():raise ValueError('Use a new output directory')
    rows=json.loads((source/'results.json').read_text(encoding='utf8'))['rows'];state=json.loads((source/'project'/'project.json').read_text(encoding='utf8'))
    p=Project(out/'project');model=ModelService();model.load(args.checkpoint,'vit_b','cpu');report=[]
    for row in rows:
        if row['method']!='crop':continue
        iid=p.add_image((source/'project'/'images'/(row['image_id']+'.png')).read_bytes(),row['name']+'.png')
        p.state['preprocessing'][iid]=copy.deepcopy(state['preprocessing'][row['image_id']]);im=model_input(p,iid);ex=exclusion_mask(p,iid);raw=p.image(iid)
        for choice in range(3):
            start=time.perf_counter();item=model.in_roi(im,row['roi'],row['points'],mask_choice=choice);seconds=time.perf_counter()-start
            c=save_prediction(p,iid,item,'roi-extract',prompts=dict(roi=row['roi'],points=row['points'],mask_choice=choice));m=p.mask(iid,c['id']);r=dict(name=row['name'],image_id=iid,candidate_id=c['id'],choice=choice,score=item['score'],area=int(m.sum()),seconds=seconds,embedding_reused=item['embedding_reused'],prompt_violations=item['prompt_violations'])
            x0,y0,x1,y1=row['roi'];h,w=m.shape
            if row['name'].startswith('synthetic'):
                angle=int(row['name'].split('_')[-1]);t=np.deg2rad(angle);yy,xx=np.mgrid[:h,:w];q=(yy-256)*np.cos(t)-(xx-768)*np.sin(t);gt=((q>=0)&(q<3))[y0:y1,x0:x1];local=m[y0:y1,x0:x1];r['local_gt_iou']=float((local&gt).sum()/max(1,(local|gt).sum()))
            try:r['interior_top_fit']={k:v for k,v in robust_line(edge_points(m,'top',[(x0+10)/w,(y0+10)/h,(x1-10)/w,(y1-10)/h])).items() if k!='points'}
            except ValueError as e:r['fit_error']=str(e)
            rgb=raw.astype(float);rgb[m]=rgb[m]*.5+np.array([30,230,90])*.5;pic=Image.fromarray(np.uint8(rgb));d=ImageDraw.Draw(pic);d.rectangle(row['roi'],outline='yellow',width=2)
            for x,y,label in row['points']:d.ellipse((x-3,y-3,x+3,y+3),fill='cyan' if label else 'red')
            pic.save(out/(row['name']+f'_choice{choice+1}.png'));report.append(r);p.save();(out/'results.json').write_text(json.dumps(dict(contract='All three native SAM candidates. Shared crop embedding reused for choices 2/3. Point adherence is QC, not material GT. Human-assisted prompts; synthetic local IoU only.',rows=report),ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(r),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--checkpoint',required=True);p.add_argument('--output',required=True);main(p.parse_args())
