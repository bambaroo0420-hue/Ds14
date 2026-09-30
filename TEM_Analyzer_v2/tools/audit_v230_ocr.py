"""Actual offline EasyOCR on a provided local fixture, original preserved."""
import argparse,copy,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main(args):
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False);source=Path(args.image);data=source.read_bytes();before=hashlib.sha256(data).hexdigest()
    os.environ['TEM_PROJECT_DIR']=str(out/'project')
    import torch
    torch.set_num_threads(4)
    from fastapi.testclient import TestClient
    from tem_analyzer import api
    records=[]
    with TestClient(api.app) as c:
        iid=c.post('/api/images',files={'file':('annotation_45_fixture.png',data,'image/png')}).json()['image_id']
        def call(name,path,body):
            start=time.perf_counter();r=c.post('/api/'+path,json=body);record=dict(name=name,status=r.status_code,seconds=time.perf_counter()-start,result=r.json());records.append(record)
            (out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8');print(name,r.status_code,flush=True)
            if r.status_code!=200:raise AssertionError(r.text)
            return r.json()
        call('global_ocr','workflow/annotations/detect',dict(image_id=iid,ocr_dir=args.ocr,enhanced_ocr=True))
        (out/'global.png').write_bytes(c.get(f'/api/workflow/annotations/{iid}.png').content)
        call('local_upscale_ocr','workflow/annotations/detect',dict(image_id=iid,ocr_dir=args.ocr,retry_roi=[.15,.82,.36,.95]))
        (out/'local.png').write_bytes(c.get(f'/api/workflow/annotations/{iid}.png').content)
        call('manual_grouped_box','workflow/annotations/manual-box',dict(image_id=iid,roi=[.18,.84,.32,.93],kind='scale'))
        call('synthetic_calibration_for_preservation_check','scale/manual',dict(image_id=iid,a=[120,542],b=[185,542],length=5,unit='nm'))
        scale=copy.deepcopy(api.project.state['scale'][iid])
        call('exclusion_only','workflow/annotations/apply',dict(image_id=iid))
        records.append(dict(name='confirmed_scale_preserved',passed=scale==api.project.state['scale'][iid]))
        records.append(dict(name='original_preserved',passed=before==hashlib.sha256(source.read_bytes()).hexdigest()))
        (out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--ocr',required=True);p.add_argument('--output',required=True);main(p.parse_args())
