"""Compare explicit sampling policies on copied, already aligned real-SAM masks.

This measures policy sensitivity, not accuracy against expert thickness GT.
"""
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
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory; inputs are never overwritten.')
    out.mkdir(parents=True);shutil.copytree(Path(args.source)/'project',out/'project')
    os.environ['TEM_PROJECT_DIR']=str(out/'project')
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    p=api.project;client=TestClient(api.app);ids=list(p.state['images']);manager=api.app.state.workflow_jobs
    policies={'all':{},'center80':dict(mode='component_center',center_fraction=.8),
              'center60':dict(mode='component_center',center_fraction=.6),
              'center60_single':dict(mode='component_center',center_fraction=.6,single_interval_only=True),
              'center60_single_frame':dict(mode='component_center',center_fraction=.6,single_interval_only=True,reject_frame_endpoints=True)}
    report={'contract':'Same selected SAM masks, same scale/confirmed rotations, no layer assignment. Policy sensitivity only; no expert thickness GT. Exclusions stay in rows and raw_length_nm, never silently deleted.','policies':{}}
    counts={}
    for name,policy in policies.items():
        async def run():
            manager.start(ids,['measurement'],dict(measurement=dict(scope_id='target',start=0,step=10,sampling=policy)))
            await manager.task
        asyncio.run(run())
        if manager.current['status']!='completed':raise AssertionError(manager.current['rows'])
        values=[]
        for iid in ids:
            result=copy.deepcopy(p.state['measurements'][iid])
            if name=='all':counts[iid]=len(result['rows'])
            if counts[iid]!=len(result['rows']):raise AssertionError('Sampling deleted raw rows')
            if any(r.get('length_nm') is not None for r in result['rows'] if r['status']!='ok'):raise AssertionError('Excluded row became accepted nm')
            values.append(dict(image_id=iid,name=p.state['images'][iid]['name'],summary=result['summary'],warnings=result['warnings'],components=result['components']))
        response=client.post('/api/workflow/export',json=dict(image_ids=ids,scope_id='target',include_gt=True))
        if response.status_code!=200:raise AssertionError(response.text)
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            columns=z.read('measurements.csv').decode('utf-8-sig').splitlines()[0]
            if not all(c in columns for c in ('raw_length_nm','exclusion_reasons','component_id')):raise AssertionError('Missing audit columns')
        (out/(name+'.zip')).write_bytes(response.content)
        report['policies'][name]=dict(cases=values,job=copy.deepcopy(manager.current))
        print(json.dumps(dict(policy=name,cases=values),ensure_ascii=False),flush=True)
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);main(parser.parse_args())
