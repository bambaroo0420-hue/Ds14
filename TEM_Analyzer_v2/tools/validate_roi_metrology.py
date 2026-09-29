"""Batch selected real-SAM ROI masks against synthetic 3px band truth.

This is not TEM expert GT. Other candidates and original projects are preserved.
"""
import argparse,asyncio,copy,io,json,os,shutil,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory')
    out.mkdir(parents=True);shutil.copytree(Path(args.source)/'project',out/'project')
    os.environ['TEM_PROJECT_DIR']=str(out/'project')
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    from tem_analyzer.roi_domains import crop_guard
    p=api.project;client=TestClient(api.app);ids=[i for i,v in p.state['images'].items() if v['name'].startswith('synthetic')]
    def post(path,body):
        r=client.post('/api/'+path,json=body)
        if r.status_code!=200:raise AssertionError(r.text)
        return r
    for iid in ids:
        selected=next(c for c in p.state['candidates'][iid] if c.get('mask_choice')==2)
        post('workflow/scopes/save',dict(image_id=iid,candidate_ids=[selected['id']]))
        # Known synthetic calibration only; no inference of physical TEM scale.
        post('scale/manual',dict(image_id=iid,a=[10,10],b=[110,10],length=100))
    manager=api.app.state.workflow_jobs;jobs=[]
    settings=dict(scope_id='target',rotation=dict(scope_id='target',mode='auto'),measurement=dict(scope_id='target',start=0,step=3))
    async def batch(steps):
        manager.start(ids,steps,settings);await manager.task;jobs.append(copy.deepcopy(manager.current))
        if manager.current['status']!='completed':raise AssertionError(manager.current['rows'])
    asyncio.run(batch(['rotation']));post('workflow/confirm-many',dict(image_ids=ids,kind='rotation'))
    asyncio.run(batch(['measurement']));provisional=copy.deepcopy(p.state['measurements'])
    for iid in ids:post('workflow/scopes/confirm',dict(image_id=iid))
    asyncio.run(batch(['gt','measurement']))
    response=post('workflow/export',dict(image_ids=ids,scope_id='target',include_gt=True));(out/'partial-results.zip').write_bytes(response.content)
    rows=[]
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        for iid in ids:
            name=p.state['images'][iid]['name'];angle=int(name.split('_')[-1].split('.')[0])
            selected=[p.candidate(iid,cid) for cid in p.state['mask_scopes'][iid]['target']['candidate_ids']]
            lab=np.array(Image.open(io.BytesIO(z.read(iid+'/partial_gt/labels.png'))));cut=crop_guard(p,iid,selected)
            if not cut.any() or not np.all(lab[cut]==65535):raise AssertionError('Crop cuts must stay unknown')
            m=provisional[iid];mean=m['summary']['mean']
            if m['review_status']!='provisional_unreviewed_masks':raise AssertionError('Must allow measurement before GT')
            rows.append(dict(name=name,known_band_width_px=3,assumed_nm_per_px=1,known_angle=angle,
                             estimated_angle=p.state['alignments'][iid]['fit']['angle_deg'],summary=m['summary'],
                             mean_error_from_3px=None if mean is None else mean-3,cut_pixels=int(cut.sum()),unknown_pixels=int((lab==65535).sum()),
                             unassigned_candidates=len(p.state['candidates'][iid]),selected_ids=[c['id'] for c in selected]))
    if any(c['layer_id'] is not None for cs in p.state['candidates'].values() for c in cs):raise AssertionError('Implicit layer assignment')
    report=dict(rows=rows,jobs=jobs,contract='Three synthetic 3px band images. Existing actual SAM candidate 3 selected, not expert TEM GT. 1nm/px is synthetic calibration. Crop limits unknown in partial GT. All candidates remain unassigned.')
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(rows,ensure_ascii=False),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--output',required=True);main(a.parse_args())
