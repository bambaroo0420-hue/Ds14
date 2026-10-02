"""Actual SAM mixed-recipe/ROI/evidence audit. New output directory required."""
import argparse,asyncio,copy,hashlib,io,json,os,sys,time
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

async def main(args):
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    source=Path(args.source).resolve();original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    os.environ['TEM_PROJECT_DIR']=str(out/'project')
    import torch
    torch.set_num_threads(4)
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    from tem_analyzer.storage import Project
    from tem_analyzer.services.prompt_batches import transfer_signature,current_transfer
    from tem_analyzer.algorithms.metrology import transform_points
    import cv2
    report={'contract':'Actual SAM; 19-derived consistency, NOT expert GT or company accuracy','checks':[]}
    def record(name,ok,**details):
        report['checks'].append(dict(name=name,passed=bool(ok),**details));(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report['checks'][-1],ensure_ascii=True),flush=True)
        if not ok:raise AssertionError(name)
    with TestClient(api.app) as c:
        def post(path,body):
            r=c.post('/api/'+path,json=body)
            if r.status_code!=200:raise AssertionError(path+': '+r.text[:600])
            return r.json()
        rgb=np.asarray(Image.open(source).convert('RGB'));h,w=rgb.shape[:2];montage=np.concatenate([rgb,rgb],axis=1)
        targets=[]
        for name,im in [('19_two_cells',montage),('19_two_cells_dark',np.uint8(montage*.75)),('19_two_cells_noise',np.uint8(np.clip(montage.astype(float)+np.random.default_rng(230).normal(0,8,montage.shape),0,255)))]:
            b=io.BytesIO();Image.fromarray(im).save(b,format='PNG');r=c.post('/api/images',files={'file':(name+'.png',b.getvalue(),'image/png')});targets.append(r.json()['image_id'])
        groups=[dict(name=f'Manual {n+1}',points=[[170+n*w,113,1]],box=[53.5+n*w,46.5,289+n*w,193],roi=None,locked=False) for n in range(2)]
        post('workbench/groups',dict(image_id=targets[0],groups=groups))
        post('workflow/prompt-presets/save',dict(image_id=targets[0],preset_id='v230_mixed',draft=dict(manual_groups=groups,auto_policy='grid_features',grid=2,feature_settings={'method':'canny','count':2,'denoise':'gaussian'},auto_points=[],manual_points=[],box=None)))
        post('model/load',{'checkpoint':args.checkpoint,'variant':'vit_b','device':'cpu'})
        async def job(name,steps,settings):
            manager=api.app.state.workflow_jobs;start=time.perf_counter();manager.start(targets,steps,settings);await manager.task
            r=copy.deepcopy(manager.current);record(name,r['status']=='completed',seconds=time.perf_counter()-start,rows=r['rows']);return r
        await job('recipe_batch_prepare',['prompt_transfer'],{'prompt_transfer':{'preset_id':'v230_mixed','method':'normalized'}})
        for iid in targets:
            value=current_transfer(api.project,iid);image=c.get(f'/api/workflow/prompt-transfers/{iid}/preview.png');record('group_preview_'+iid,image.status_code==200,groups=len(value['draft']['manual_groups']),auto_points=len(value['draft']['auto_points']))
        post('workflow/prompt-transfers/confirm',{'entries':[dict(image_id=iid,signature=transfer_signature(current_transfer(api.project,iid))) for iid in targets]})
        await job('actual_SAM_Grid_Canny_two_manual_groups',['sam'],{'sam':{'prompt_source':'transferred','grid':2,'pred_iou':.8,'stability':.85,'nms':.8}})
        for iid in targets:
            groups_out=[x for x in api.project.state['candidates'][iid] if x['source']=='transferred-group'];record('two_manual_outputs_'+iid,len(groups_out)==2,areas=[x['area'] for x in groups_out])
            post('workflow/scopes/save',{'image_id':iid,'scope_id':'selected_cells','candidate_ids':[x['id'] for x in groups_out]})
            post('scale/manual',dict(image_id=iid,a=[0,h-5],b=[100,h-5],length=100,unit='nm')) # Synthetic test calibration only.
        await job('partial_mask_batch_rotation',['rotation'],{'rotation':{'scope_id':'selected_cells','mode':'objects','edge':'bottom'}})
        for iid in targets:post('workflow/rotation/confirm',{'image_id':iid})
        for axis in ('thickness','cd'):
            await job('partial_mask_batch_'+axis,['measurement'],{'measurement':{'scope_id':'selected_cells','axis':axis,'step':20,'start':20}})
        for iid in targets:
            for endpoint in ('rotation','measurement'):
                r=c.get(f'/api/workbench/{iid}/{endpoint}.png?aligned=true');record(endpoint+'_evidence_'+iid,r.status_code==200)
                (out/f'{iid}_{endpoint}.png').write_bytes(r.content)
        r=post('sam/roi-auto/preview',dict(image_id=targets[0],roi=[30,20,310,215],grid=2,prompt_source='grid_features',pred_iou=.7,stability=.8,nms=.8,feature_settings={'method':'sobel','count':2}))
        record('actual_independent_ROI_candidates',r['count']>0,count=r['count'],prompt_count=r['prompt_count'])
        png=c.get('/api/roi-auto/'+r['token']+'.png');(out/'roi_auto.png').write_bytes(png.content)
        saved=post('sam/roi-auto/accept',dict(token=r['token'],indices=[0],image_id=targets[0]));item=saved['created'][0];mask=api.project.mask(targets[0],item['id']);domain=np.zeros_like(mask);domain[20:215,30:310]=1
        record('ROI_candidate_domain',not (mask&~domain).any(),area=item['area'])
        # Tilt a real montage and transfer known prompts by the known augmentation matrix.
        from tem_analyzer.algorithms.metrology import rotation_transform,warp
        transform=rotation_transform(montage.shape,-12);matrix=np.array(transform['matrix']);tilted=warp(montage,transform,order=1,fill=150)
        b=io.BytesIO();Image.fromarray(tilted).save(b,format='PNG');iid=c.post('/api/images',files={'file':('19_two_cells_tilt12.png',b.getvalue(),'image/png')}).json()['image_id']
        tg=copy.deepcopy(groups)
        for g in tg:
            g['points']=[transform_points([p[:2]],matrix)[0].tolist()+[p[2]] for p in g['points']]
            x0,y0,x1,y1=g['box'];pts=transform_points([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],matrix);g['box']=np.r_[pts.min(axis=0),pts.max(axis=0)].tolist()
        r=post('sam/prepared',dict(image_id=iid,manual_groups=tg));ids=[x['id'] for x in r['created']]
        post('workflow/scopes/save',dict(image_id=iid,scope_id='tilted_cells',candidate_ids=ids))
        rotation=post('workflow/rotation/preview',dict(image_id=iid,config={'scope_id':'tilted_cells','mode':'objects','edge':'bottom'}))
        record('tilted_19_actual_SAM_rotation',len(ids)==2,rotation=rotation,note='Known affine used only to place SAM prompts, not to set measured rotation.')
        (out/'tilted_rotation.png').write_bytes(c.get(f'/api/workbench/{iid}/rotation.png?aligned=true').content)
        record('source_preserved',hashlib.sha256(source.read_bytes()).hexdigest()==original_hash)
        reloaded=Project(api.project.root);record('reload_recipes_and_groups',len(reloaded.state['manual_groups'][targets[0]])==2 and reloaded.state['prompt_presets']['v230_mixed']['schema_version']==2)
        report['project']=str(api.project.root);report['images']=targets+[iid];(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--checkpoint',required=True);p.add_argument('--output',required=True);asyncio.run(main(p.parse_args()))
