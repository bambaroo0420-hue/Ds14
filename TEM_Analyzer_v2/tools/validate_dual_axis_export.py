"""Preserved actual SAM output plus exact rectangle: axis storage/export QA."""
import argparse,copy,csv,hashlib,io,json,os,shutil,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output folder')
    source=Path(args.project);shutil.copytree(source,out/'project');os.environ['TEM_PROJECT_DIR']=str(out/'project')
    source_hashes={str(f.relative_to(source)):hashlib.sha256(f.read_bytes()).hexdigest() for d in ('images','masks') for f in (source/d).glob('*.png')}
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    from tem_analyzer.storage import Project
    from tem_analyzer.algorithms.metrology import transform_points
    p=api.project;c=TestClient(api.app)
    def post(path,body):
        r=c.post('/api/'+path,json=body)
        if r.status_code!=200:raise AssertionError(r.text)
        return r
    iid=next(i for i,v in p.state['images'].items() if v['name'].startswith('synthetic'))
    cfg=dict(scope_id='target',start=0,step=1)
    values={axis:post('workflow/measurement',dict(image_id=iid,config=dict(cfg,axis=axis))).json() for axis in ('thickness','cd')}
    before=copy.deepcopy(p.state)
    response=post('workflow/export',dict(image_ids=[iid],scope_id='target',export_all_axes=True));(out/'both-axes.zip').write_bytes(response.content)
    if p.state!=before:raise AssertionError('Export mutated state')
    max_error=0.
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        rows=list(csv.DictReader(io.StringIO(z.read('measurements.csv').decode('utf-8-sig'))))
        for axis,m in values.items():
            if sum(r['axis']==axis for r in rows)!=len(m['rows']):raise AssertionError('CSV row loss')
            if json.loads(z.read(iid+'/measurements/'+axis+'.json'))!=m:raise AssertionError('JSON mismatch')
            for row in m['rows']:
                if 'original_endpoints' not in row:continue
                points=np.array(row['original_endpoints']);aligned=transform_points(points,m['transform']['matrix'])
                max_error=max(max_error,float(np.max(np.abs(aligned-np.array(row['aligned_endpoints'])))),abs(float(np.linalg.norm(points[1]-points[0]))-row['length_px']))
    if max_error>1e-8:raise AssertionError('Coordinate/length roundtrip changed')
    reloaded=Project(out/'project')
    if set(reloaded.state['measurements_by_axis'][iid])!={'thickness','cd'}:raise AssertionError('Restart lost axis')
    # Synthetic fixture only: deliberately alter calibration to test stale gating.
    post('scale/manual',dict(image_id=iid,a=[10,10],b=[110,10],length=200))
    post('workflow/measurement',dict(image_id=iid,config=dict(cfg,axis='thickness')))
    rejected=c.post('/api/workflow/export',json=dict(image_ids=[iid],scope_id='target',export_all_axes=True))
    if rejected.status_code!=400 or 'cd' not in rejected.text:raise AssertionError('Stale CD should block combined export')
    post('workflow/export',dict(image_ids=[iid],scope_id='target',export_all_axes=False))
    post('workflow/measurement',dict(image_id=iid,config=dict(cfg,axis='cd')))
    post('workflow/export',dict(image_ids=[iid],scope_id='target',export_all_axes=True))
    # Independent exact-geometry GUI control, not a SAM segmentation or TEM image.
    image=np.full((60,80,3),40,np.uint8);image[20:40,10:70]=180;b=io.BytesIO();Image.fromarray(image).save(b,format='PNG')
    control=p.add_image(b.getvalue(),'known_rectangle_20x60.png');mask=np.zeros((60,80),bool);mask[20:40,10:70]=True
    cand=p.put_candidate(control,mask,'exact-geometry-control');post('workflow/scopes/save',dict(image_id=control,candidate_ids=[cand['id']]))
    post('workflow/rotation/preview',dict(image_id=control,config=dict(scope_id='target',mode='auto')));post('workflow/rotation/confirm',dict(image_id=control))
    post('scale/manual',dict(image_id=control,a=[5,5],b=[55,5],length=50))
    for rel,digest in source_hashes.items():
        if hashlib.sha256((source/rel).read_bytes()).hexdigest()!=digest or hashlib.sha256((out/'project'/rel).read_bytes()).hexdigest()!=digest:raise AssertionError('Original image/mask changed')
    result=dict(actual_sam_axes={a:m['summary'] for a,m in values.items()},csv_rows={a:len(m['rows']) for a,m in values.items()},coordinate_roundtrip_max_error_px=max_error,
                rejected_stale_cd=rejected.json(),preserved_source_files=len(source_hashes),gui_control_image_id=control,
                note='No new SAM. Existing generated thin-band SAM mask, 1nm/px initially; 2nm/px only to test stale calibration. Exact 20px by 60px rectangle is a separate non-SAM control. No physical TEM accuracy claims.')
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--output',required=True);main(a.parse_args())
