"""Actual base-SAM preview/accept and rotation API, without layer assignment."""
import argparse,copy,json,os,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(args):
    import torch
    from fastapi.testclient import TestClient
    from tem_analyzer.storage import Project
    torch.set_num_threads(4);out=Path(args.output)
    if out.exists():raise ValueError('Use a new output folder')
    os.environ['TEM_PROJECT_DIR']=str(out.resolve()/'project')
    from tem_analyzer import api
    source=Path(args.source);src=Project(source/'project');p=api.project;client=TestClient(api.app)
    rows=json.loads((source/'results.json').read_text(encoding='utf8'))['rows'];experiment=Project(Path(args.experiment)/'project')
    erows=json.loads((Path(args.experiment)/'results.json').read_text(encoding='utf8'))['rows'];results=[]
    def post(path,data):
        r=client.post('/api/'+path,json=data)
        if r.status_code!=200:raise AssertionError(r.text)
        return r.json()
    post('model/load',dict(checkpoint=args.checkpoint,variant='vit_b',device='cpu'))
    for name,margin,choice in [('synthetic_thin_+45',6,2),('attached_TaOx_assisted',18,0),('attached_TiOxNy_assisted',6,2),('existing_140_assisted',6,1)]:
        r=next(r for r in rows if r['method']=='crop' and r['name']==name)
        iid=p.add_image((source/'project'/'images'/(r['image_id']+'.png')).read_bytes(),name+'.png');p.state['preprocessing'][iid]=copy.deepcopy(src.state['preprocessing'][r['image_id']]);p.save()
        start=time.perf_counter();preview=post('sam/prompt',dict(image_id=iid,roi=r['roi'],points=r['points'],align_positive=True,box_margin=margin,mask_choice=choice,preview=True));seconds=time.perf_counter()-start
        if p.state['candidates'][iid]:raise AssertionError('Preview wrote a candidate')
        saved=post('roi-previews/'+preview['preview_token']+'/accept',{});post('workflow/scopes/save',dict(image_id=iid,candidate_ids=[saved['id']]))
        erow=next(e for e in erows if e['name']==name and e['mode']==f'aligned_box{margin}' and e['choice']==choice)
        old=experiment.mask(erow['image_id'],erow['candidate_id']);new=p.mask(iid,saved['id'])
        riou=float((old&new).sum()/max(1,(old|new).sum()))
        if riou<.999:raise AssertionError('Production result differs from prototype')
        rot=client.post('/api/workflow/rotation/preview',json=dict(image_id=iid,config=dict(scope_id='target',mode='auto')))
        result=dict(name=name,image_id=iid,candidate_id=saved['id'],preview_seconds=seconds,prototype_iou=riou,area=int(new.sum()),prompt_violations=saved['prompt_violations'],alignment=saved['roi_alignment'],rotation=rot.json(),rotation_http=rot.status_code)
        if saved['layer_id'] is not None:raise AssertionError('Unexpected layer assignment')
        results.append(result);(out/'results.json').write_text(json.dumps(dict(rows=results,contract='4 actual SAM preview/accept calls. Prototype agreement is implementation parity, not expert GT. No layer assignment or automatic GT approval.'),ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k not in ('rotation','alignment')}),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--experiment',required=True);a.add_argument('--checkpoint',required=True);a.add_argument('--output',required=True);main(a.parse_args())
