"""Actual full-frame versus ROI SAM, with equal original-coordinate prompts.

Synthetic local IoU has known GT. Public/attached outputs have no expert GT.
Cropping does not recover missing structure outside the crop.
"""
import argparse,copy,json,sys,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.preprocessing import model_input,exclusion_mask
from tem_analyzer.algorithms.metrology import edge_points,robust_line


def main(args):
    import torch
    torch.set_num_threads(4);out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory')
    out.mkdir(parents=True);p=Project(out/'project');cases=[]
    for angle in (0,30,45):
        h,w=512,1536;yy,xx=np.mgrid[:h,:w];t=np.deg2rad(angle);q=(yy-256)*np.cos(t)-(xx-768)*np.sin(t)
        truth=(q>=0)&(q<3);gray=np.full((h,w),95.);gray[truth]=205;gray[(q>17)&(q<25)]=30;gray[(q>-35)&(q<-28)]=190
        im=np.repeat(np.uint8(np.clip(gray+np.random.default_rng(224).normal(0,7,(h,w)),0,255))[:,:,None],3,2)
        points=[[x,256+(x-768)*np.tan(t)+1.5/np.cos(t),1] for x in (670,750,830)]
        points += [[750,256+(750-768)*np.tan(t)+d/np.cos(t),0] for d in (-10,10)]
        cases.append(dict(name=f'synthetic_thin_{angle:+03d}',image=im,roi=[610,70,910,430],points=points,truth=truth,prep={}))
    attached=Path(args.attached);ast=json.loads((attached/'project.json').read_text(encoding='utf8'));aid=next(iter(ast['images']))
    ai=np.array(Image.open(attached/'images'/f'{aid}.png').convert('RGB'));prep=ast['preprocessing'][aid]
    cases += [dict(name='attached_TaOx_assisted',image=ai,roi=[80,140,440,480],points=[[245,267,1],[160,350,1],[320,190,1],[150,230,0],[320,390,0]],prep=prep),
              dict(name='attached_TiOxNy_assisted',image=ai,roi=[130,210,415,470],points=[[260,350,1],[210,400,1],[330,280,1],[200,310,0],[390,330,0]],prep=prep)]
    public=Path(args.public);pst=json.loads((public/'project.json').read_text(encoding='utf8'))
    for tag,roi,points in [('existing_140',[30,100,315,210],[[80,157,1],[260,150,1],[80,132,0],[260,173,0]]),
                           ('new_hafnia_h',[35,70,190,140],[[65,90,1],[145,91,1],[65,62,0],[145,116,0]])]:
        # Keep only valid points in the actual crop, no silent coordinate scaling.
        sid=next(i for i,v in pst['images'].items() if v['name'].startswith(tag))
        image=np.array(Image.open(public/'images'/f'{sid}.png').convert('RGB'))
        points=[q for q in points if roi[0]<=q[0]<roi[2] and roi[1]<=q[1]<roi[3]]
        cases.append(dict(name=tag+'_assisted',image=image,roi=roi,points=points,prep=pst['preprocessing'][sid]))
    model=ModelService();model.load(args.checkpoint,'vit_b','cpu');report=dict(rows=[],contract='Same manually prepared original-coordinate prompts, cold encoders. Synthetic IoU measured only inside crop, not full target recovery. Public and attached have no expert GT. No automatic material identification.')
    for case in cases:
        raw=case['image'];roi=case['roi'];x0,y0,x1,y1=roi
        for method in ('full','crop'):
            from io import BytesIO
            buf=BytesIO();Image.fromarray(raw).save(buf,format='PNG');iid=p.add_image(buf.getvalue(),case['name']+'_'+method+'.png')
            p.state['preprocessing'][iid].update(copy.deepcopy(case['prep']));image=model_input(p,iid);ex=exclusion_mask(p,iid)
            points=[q for q in case['points'] if not ex[int(q[1]),int(q[0])]]
            model.image_key=None;model.predictor.reset_image();start=time.perf_counter()
            item=model.in_roi(image,roi,points) if method=='crop' else model.prompt(image,points)
            seconds=time.perf_counter()-start;m=item['mask']&~ex;c=p.put_candidate(iid,m,'roi-comparison-'+method,score=item['score'],prompts=dict(points=points,roi=roi if method=='crop' else None))
            local=m[y0:y1,x0:x1];row=dict(name=case['name'],method=method,image_id=iid,candidate_id=c['id'],roi=roi,points=points,seconds=seconds,score=item['score'],area=int(m.sum()),local_area=int(local.sum()),crop_touches=[bool(local[0].any()),bool(local[-1].any()),bool(local[:,0].any()),bool(local[:,-1].any())])
            if 'truth' in case:
                gt=case['truth'][y0:y1,x0:x1];row['local_gt_iou']=float((local&gt).sum()/max(1,(local|gt).sum()))
            try:
                region=[(x0+10)/raw.shape[1],(y0+10)/raw.shape[0],(x1-10)/raw.shape[1],(y1-10)/raw.shape[0]]
                fit=robust_line(edge_points(m,'top',region));row['interior_top_fit']={k:v for k,v in fit.items() if k!='points'}
            except ValueError as e:row['fit_error']=str(e)
            canvas=raw.astype(float);canvas[m]=canvas[m]*.5+np.array([30,230,90])*.5;im=Image.fromarray(np.uint8(canvas));d=ImageDraw.Draw(im);d.rectangle(roi,outline='yellow',width=2)
            for x,y,label in points:d.ellipse((x-3,y-3,x+3,y+3),fill='cyan' if label else 'red')
            im.save(out/(case['name']+'_'+method+'.png'));report['rows'].append(row);p.save();(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps(row,ensure_ascii=False),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--attached',required=True);a.add_argument('--public',required=True);a.add_argument('--checkpoint',required=True);a.add_argument('--output',required=True);main(a.parse_args())
