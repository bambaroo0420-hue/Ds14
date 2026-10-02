"""Stored actual SAM selections: review failure, skipped steps, partial recovery."""
import argparse,asyncio,copy,io,json,os,shutil,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output folder')
    shutil.copytree(args.project,out/'project');os.environ['TEM_PROJECT_DIR']=str(out/'project')
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    p=api.project;client=TestClient(api.app);ids=list(p.state['images']);jobs=[]
    # New test copy only: make every selected scope deliberately unreviewed.
    for iid in ids:p.state['mask_scopes'][iid]['target']['review_hash']=None
    p.save();manager=api.app.state.workflow_jobs
    settings=dict(scope_id='target',measurement=dict(scope_id='target',start=0,step=3))
    async def run():
        manager.start(ids,['gt','measurement'],settings);await manager.task;jobs.append(copy.deepcopy(manager.current))
    asyncio.run(run());first=jobs[-1]
    if first['done']!=first['total'] or sum(r['status']=='skipped' for r in first['rows'])!=len(ids):raise AssertionError('Missing skipped rows')
    iid=next(i for i in ids if p.state['images'][i]['name'].startswith('synthetic'))
    def post(path,body):
        r=client.post('/api/workflow/'+path,json=body)
        if r.status_code!=200:raise AssertionError(r.text)
        return r
    post('rotation/preview',dict(image_id=iid,config=dict(scope_id='target',mode='auto')));post('rotation/confirm',dict(image_id=iid))
    r=client.post('/api/scale/manual',json=dict(image_id=iid,a=[10,10],b=[110,10],length=100))
    if r.status_code!=200:raise AssertionError(r.text)
    post('scopes/confirm',dict(image_id=iid))
    # Same plan as retry; then exercise the actual retry endpoint on the same loop.
    async def retry():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://test') as ac:
            r=await ac.post('/api/workflow/jobs/retry',json=dict(job_id=first['id']))
            if r.status_code!=200:raise AssertionError(r.text)
            await manager.task;jobs.append(copy.deepcopy(manager.current))
    asyncio.run(retry());second=jobs[-1]
    if sum(r['status']=='done' for r in second['rows'])!=2 or second['done']!=second['total']:raise AssertionError('Unexpected retry accounting')
    zbytes=post('export',dict(image_ids=[iid],scope_id='target',include_gt=True)).content;(out/'synthetic-partial.zip').write_bytes(zbytes)
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        labels=np.array(Image.open(io.BytesIO(z.read(iid+'/partial_gt/labels.png'))));valid=np.array(Image.open(io.BytesIO(z.read(iid+'/partial_gt/valid.png'))))>0
        if not (labels==65535).any() or not valid.any():raise AssertionError('Partial GT missing unknown or target')
    if any(c['layer_id'] is not None for cs in p.state['candidates'].values() for c in cs):raise AssertionError('Implicit layer assignment')
    result=dict(jobs=jobs,synthetic_measurement=p.state['measurements'][iid]['summary'],unknown_pixels=int((labels==65535).sum()),valid_pixels=int(valid.sum()),
                candidates_preserved=sum(map(len,p.state['candidates'].values())),note='Only synthetic image review/rotation/1nm-per-pixel confirmed by test harness. Other three real-image GT failures deliberately remain. Not expert GT. No new SAM calls.')
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='jobs'},ensure_ascii=False),flush=True)
    for j in jobs:print(json.dumps(dict(status=j['status'],done=j['done'],total=j['total'],counts={s:sum(r['status']==s for r in j['rows']) for s in ('done','failed','skipped')})),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--output',required=True);main(a.parse_args())
