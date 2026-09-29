"""Human-assisted aligned-ROI SAM ablation, not automatic material GT.

Source images/projects remain unchanged. Rigidly transform local pixels/prompts,
optionally form a narrow box from positive points, infer, restore probability to
the original grid, and keep original ROI provenance. No geometric hard-clipping
to the prompt box is allowed; actual negative-point adherence is reported.
"""
import argparse,copy,io,json,sys,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.preprocessing import model_input,exclusion_mask
from tem_analyzer.sam_service import ModelService
from tem_analyzer.algorithms.metrology import rotation_transform,transform_points,warp,robust_line,edge_points
from tem_analyzer.v2_api import save_prediction


def main(args):
    import torch
    torch.set_num_threads(4);source=Path(args.source);out=Path(args.output)
    if out.exists():raise ValueError('Use a new output folder')
    out.mkdir(parents=True);src=Project(source/'project');p=Project(out/'project')
    cases=[r for r in json.loads((source/'results.json').read_text(encoding='utf8'))['rows'] if r['method']=='crop']
    model=ModelService();model.load(args.checkpoint,'vit_b','cpu');report=[]
    for case in cases:
        iid=p.add_image((source/'project'/'images'/(case['image_id']+'.png')).read_bytes(),case['name']+'.png')
        p.state['preprocessing'][iid]=copy.deepcopy(src.state['preprocessing'][case['image_id']]);image=model_input(p,iid);raw=p.image(iid);ex=exclusion_mask(p,iid)
        roi=case['roi'];x0,y0,x1,y1=roi;local=image[y0:y1,x0:x1];points=case['points'];positive=np.array([q[:2] for q in points if q[2]])
        if len(positive)<2:
            report.append(dict(name=case['name'],skipped='Fewer than two positive points; no direction inferred'))
            continue
        fit=robust_line(positive);angle=-fit['angle_deg'];tr=rotation_transform(local.shape,angle)
        moved=transform_points(np.array([q[:2] for q in points])-[x0,y0],tr['matrix'])
        pp=np.c_[moved,[q[2] for q in points]].tolist();rotated=warp(local,tr,order=1,fill=int(np.median(local)))
        support=warp(np.ones(local.shape[:2],np.uint8),tr,order=0)>0
        back=dict(inverse=tr['matrix'],width=x1-x0,height=y1-y0)
        for mode in ('native_box','aligned_points','aligned_box6','aligned_box18'):
            aligned=mode!='native_box';im=rotated if aligned else local;prompt=pp if aligned else [[q[0]-x0,q[1]-y0,q[2]] for q in points]
            pos=np.array([q[:2] for q in prompt if q[2]]);box=None
            if mode!='aligned_points':
                margin=6 if mode=='aligned_box6' else 18
                lo=pos.min(axis=0)-[30,margin];hi=pos.max(axis=0)+[30,margin]
                box=np.r_[np.maximum(lo,0),np.minimum(hi,[im.shape[1],im.shape[0]])].tolist()
            for choice in range(3):
                start=time.perf_counter();item=model.prompt(im,prompt,box,mask_choice=choice);seconds=time.perf_counter()-start
                prob=item['probability'].copy()
                if aligned:prob[~support]=0;prob=warp(prob,back,order=1)
                localmask=prob>=.5;mask=np.zeros(ex.shape,bool);mask[y0:y1,x0:x1]=localmask;mask&=~ex
                item.update(mask=mask,inference_domains=[roi],prompt_violations=[k for k,(x,y,lab) in enumerate(points) if bool(mask[int(np.floor(y+.5)),int(np.floor(x+.5))])!=bool(lab)])
                for key in ('context','probability','logits'):item.pop(key,None)
                c=save_prediction(p,iid,item,'oriented-roi-experiment',prompts=dict(points=points,roi=roi,mode=mode,angle=angle if aligned else 0,aligned_box=box,transform=tr if aligned else None))
                row=dict(name=case['name'],mode=mode,choice=choice,seconds=seconds,image_id=iid,candidate_id=c['id'],score=item['score'],area=int(mask.sum()),prompt_violations=item['prompt_violations'],embedding_reused=item['embedding_reused'],assisted_rotation=angle if aligned else 0,box=box)
                if case['name'].startswith('synthetic'):
                    a=int(case['name'].split('_')[-1]);t=np.deg2rad(a);yy,xx=np.mgrid[:mask.shape[0],:mask.shape[1]];q=(yy-256)*np.cos(t)-(xx-768)*np.sin(t);gt=((q>=0)&(q<3))[y0:y1,x0:x1];m=mask[y0:y1,x0:x1];row['local_gt_iou']=float((m&gt).sum()/max(1,(m|gt).sum()))
                try:row['fit']={k:v for k,v in robust_line(edge_points(mask,'top',[(x0+10)/mask.shape[1],(y0+10)/mask.shape[0],(x1-10)/mask.shape[1],(y1-10)/mask.shape[0]])).items() if k!='points'}
                except ValueError as e:row['fit_error']=str(e)
                rgb=raw.astype(float);rgb[mask]=rgb[mask]*.5+np.array([30,230,90])*.5;pic=Image.fromarray(np.uint8(rgb));d=ImageDraw.Draw(pic);d.rectangle(roi,outline='orange',width=2)
                for x,y,lab in points:d.ellipse((x-3,y-3,x+3,y+3),fill='cyan' if lab else 'red')
                pic.save(out/(case['name']+'_'+mode+f'_{choice+1}.png'))
                report.append(row);p.save();(out/'results.json').write_text(json.dumps(dict(contract='Human-assisted positive-point direction and boxes. No new labels, no expert GT. Geometry restored to original grid; no prompt-box clipping. Fixed base SAM threshold .5; not adaptation-model validation.',rows=report),ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(row),flush=True)
    # Preserve a final skipped case too, even when it performed no inference.
    (out/'results.json').write_text(json.dumps(dict(contract='Human-assisted positive-point direction and boxes; no expert GT or prompt-box clipping.',rows=report),ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--checkpoint',required=True);a.add_argument('--output',required=True);main(a.parse_args())
