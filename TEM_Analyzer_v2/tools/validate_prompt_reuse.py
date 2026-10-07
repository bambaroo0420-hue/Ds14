"""Actual SAM on reviewed transfer drafts, with known-source TEM transformations.

Agreement with previous SAM masks is NOT expert GT or material accuracy.
"""
import argparse
import asyncio
import copy
import io
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage as ndi
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.services.prompt_transfer import save_preset
from tem_analyzer.services.prompt_batches import current_transfer,confirm_transfers,transfer_signature


async def main(args):
    import torch
    torch.set_num_threads(4);out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory.')
    source=Path(args.project).resolve();state=json.loads((source/'project.json').read_text(encoding='utf8'))
    out.mkdir(parents=True);os.environ['TEM_PROJECT_DIR']=str(out/'project')
    import tem_analyzer.api as api
    p=api.project;manager=api.app.state.workflow_jobs;rows=[];group_ids={};references={};truth={};names={}
    for method in args.methods:
        for iid,info in state['images'].items():
            name=info['name'];kind='cell1' if '_1cell_' in name else 'cell3'
            target=p.add_image((source/'images'/f'{iid}.png').read_bytes(),method+'_'+name)
            p.state['preprocessing'][target]['auto_regions']=copy.deepcopy(state['preprocessing'][iid].get('auto_regions',{}))
            names[target]=name;group_ids.setdefault((method,kind),[]).append(target)
            mask_ids=state['mask_scopes'][iid]['target']['candidate_ids']
            masks=[np.array(Image.open(source/'masks'/f'{iid}_{cid}.png').convert('L'))>0 for cid in mask_ids]
            truth[target]=masks
            if '+00deg' in name:
                references[(method,kind)]=target;points=[]
                for mask in masks:
                    y,x=np.unravel_index(ndi.distance_transform_edt(mask).argmax(),mask.shape);points.append([float(x),float(y)])
                draft=dict(auto_points=points,manual_points=[],box=None,manual_mode='object')
                if kind=='cell1':
                    yy,xx=np.nonzero(masks[0]);h,w=masks[0].shape
                    draft['manual_points']=[points[0]+[1],[points[0][0],float(min(h-1,yy.max()+20)),0]]
                    draft['box']=[float(max(0,xx.min()-3)),float(max(0,yy.min()-3)),float(min(w,xx.max()+4)),float(min(h,yy.max()+4))]
                save_preset(p,target,method+'_'+kind,draft)
    # Flat, same-sized target cannot pass ECC. It must not fall back to Grid.
    negative_method=next((m for m in args.methods if m!='normalized'),None)
    reference=references[(args.methods[0],'cell3')];info=p.state['images'][reference]
    buf=io.BytesIO();Image.new('RGB',(info['width'],info['height']),'gray').save(buf,format='PNG')
    if negative_method:
        blank=p.add_image(buf.getvalue(),negative_method+'_flat_negative.png');group_ids[(negative_method,'cell3')].append(blank);names[blank]='flat_negative'
    jobs=[]
    for (method,kind),ids in group_ids.items():
        manager.start(ids,['prompt_transfer'],{'prompt_transfer':{'preset_id':method+'_'+kind,'method':method}});await manager.task
        jobs.append(copy.deepcopy(manager.current))
    api.model.load(args.checkpoint,'vit_b','cpu')
    for iid,name in names.items():
        row=dict(image_id=iid,name=p.state['images'][iid]['name'])
        try:
            value=current_transfer(p,iid);draft=value['draft'];confirm_transfers(p,[dict(image_id=iid,signature=transfer_signature(value))])
            row.update(method=value['method'],ecc_score=value['ecc_score'],matrix=value['matrix'],warnings=value['warnings'])
            # Workflow confirmation here verifies execution plumbing, not human scientific approval.
            start=time.perf_counter();manager.start([iid],['sam'],{'sam':{'prompt_source':'transferred','pred_iou':.5,'stability':.7,'nms':.8}});await manager.task
            row.update(seconds=time.perf_counter()-start,job=copy.deepcopy(manager.current));candidates=p.state['candidates'][iid]
            masks=[p.mask(iid,c['id']) for c in candidates]
            row.update(count=len(candidates),all_unassigned=all(c['layer_id'] is None for c in candidates),
                       best_previous_sam_iou=[max((float((a&b).sum()/max(1,(a|b).sum())) for a in masks),default=0) for b in truth[iid]])
            rgb=p.image(iid).astype(float)
            for k,mask in enumerate(masks):rgb[mask]=rgb[mask]*.6+np.array([(k*73+30)%255,(k*137+170)%255,(k*51+20)%255])*.4
            im=Image.fromarray(np.uint8(rgb));draw=ImageDraw.Draw(im)
            for point in draft['auto_points']+draft['manual_points']:
                x,y=point[:2];draw.ellipse((x-3,y-3,x+3,y+3),fill='cyan' if len(point)==2 else ('lime' if point[2] else 'red'))
            if draft['box']:draw.rectangle(draft['box'],outline='yellow',width=2)
            im.save(out/(Path(p.state['images'][iid]['name']).stem+'_result.png'));row['status']='sam_completed' if manager.current['status']=='completed' else 'sam_failed'
        except ValueError as exc:row.update(status='blocked',error=str(exc),count=len(p.state['candidates'][iid]))
        rows.append(row);p.save();(out/'results.json').write_text(json.dumps(dict(contract='Real SAM execution; old SAM-mask IoU is consistency only, not expert GT. Programmatic prompt confirmation is a pipeline check. Sources read-only; new project.',preparation_jobs=jobs,rows=rows),ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({k:row[k] for k in ('name','status','ecc_score','count','best_previous_sam_iou') if k in row}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--checkpoint',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--methods',nargs='+',choices=['normalized','ecc','ecc_masked'],default=['normalized','ecc'])
    asyncio.run(main(parser.parse_args()))
