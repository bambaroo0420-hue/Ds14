"""End-to-end partial target workflow on a COPY of the real-SAM 19 fixture."""
import argparse
import asyncio
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory; no test outputs are overwritten.')
    out.mkdir(parents=True);shutil.copytree(Path(args.source)/'project',out/'project')
    os.environ['TEM_PROJECT_DIR']=str(out/'project')
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    client=TestClient(api.app);p=api.project;ids=list(p.state['images']);selections={}
    p.state['alignments']={};p.state['measurements']={};p.state['gt_reviews']={}
    for iid in ids:
        items=p.state['candidates'][iid]
        for c in items:c.update(layer_id=None,reviewed=False)
        # Deliberately leave the middle cell unselected for every three-cell case.
        selected=[items[0]['id']] if len(items)==1 else [items[0]['id'],items[-1]['id']]
        selections[iid]=selected
    p.save()
    def post(path,body):
        r=client.post('/api/workflow/'+path,json=body)
        if r.status_code!=200:raise AssertionError(r.text)
        return r
    for iid,selected in selections.items():post('scopes/save',dict(image_id=iid,candidate_ids=selected))
    manager=api.app.state.workflow_jobs;settings=dict(scope_id='target',rotation=dict(scope_id='target',mode='auto',edge='top'),measurement=dict(scope_id='target',start=0,step=10))
    jobs=[]
    async def run(steps):
        manager.start(ids,steps,settings);await manager.task
        jobs.append(copy.deepcopy(manager.current))
        if manager.current['status']!='completed':raise AssertionError(str(manager.current['rows']))
    asyncio.run(run(['rotation']))
    post('confirm-many',dict(image_ids=ids,kind='rotation'))
    asyncio.run(run(['measurement']))
    provisional={iid:copy.deepcopy(p.state['measurements'][iid]) for iid in ids}
    if any(m['review_status']!='provisional_unreviewed_masks' or m['summary']['count']<1 for m in provisional.values()):raise AssertionError('Missing provisional measurement')
    # Workflow-only confirmation, NOT expert material GT certification.
    for iid in ids:post('scopes/confirm',dict(image_id=iid))
    asyncio.run(run(['gt','measurement']))
    zipped=post('export',dict(image_ids=ids,scope_id='target',include_gt=True)).content
    (out/'partial-results.zip').write_bytes(zipped)
    counts=[]
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        for iid in ids:
            lab=np.array(Image.open(io.BytesIO(z.read(iid+'/partial_gt/labels.png'))))
            selected=np.logical_or.reduce([p.mask(iid,cid) for cid in selections[iid]])
            if ((lab==1)&~selected).any():raise AssertionError('Unselected pixels were converted into target')
            unknown=int((lab==65535).sum())
            if unknown==0:raise AssertionError('Partial target must retain unknown area')
            counts.append(dict(image=p.state['images'][iid]['name'],image_id=iid,selected_ids=selections[iid],total_masks=len(p.state['candidates'][iid]),
                               unknown_pixels=unknown,angle=p.state['alignments'][iid]['transform']['angle_deg'],measurement=provisional[iid]['summary']))
    if any(c['layer_id'] is not None for items in p.state['candidates'].values() for c in items):raise AssertionError('A layer was implicitly assigned')
    report=dict(cases=counts,jobs=jobs,contract='Real SAM masks, synthetic repeated-cell fixture. No layers assigned. Middle cell deliberately unknown. GT confirmations test workflow, NOT expert GT. Measurement accuracy not established.')
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(cases=counts,jobs=[dict(status=j['status'],steps=j['steps'],done=j['done']) for j in jobs]),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);main(parser.parse_args())
