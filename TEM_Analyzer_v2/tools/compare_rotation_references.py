"""Read preserved real SAM masks; compare references without new inference/GT."""
import argparse,json,shutil,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.services.scopes import save_scope
from tem_analyzer.services.measurement import compare_alignment


def main(args):
    out=Path(args.output)
    if out.exists():raise ValueError('Use a new output folder')
    shutil.copytree(args.project,out/'project');p=Project(out/'project');rows=[]
    for iid,im in p.state['images'].items():
        for c in p.state['candidates'][iid]:
            if not c.get('active',True) or c.get('deleted'):continue
            save_scope(p,iid,'target',[c['id']]);start=time.perf_counter()
            result=compare_alignment(p,iid,dict(scope_id='target',mode='auto',edge='top',points=[]))
            # An inner section is a separate experiment, not chosen using a GT angle.
            inner=compare_alignment(p,iid,dict(scope_id='target',mode='auto',edge='top',roi=[.3,.1,.6,.9],points=[]))
            rows.append(dict(image_name=im['name'],candidate_id=c['id'],area=c['area'],seconds=time.perf_counter()-start,full=result,inner=inner))
            (out/'results.json').write_text(json.dumps(dict(rows=rows,note='Stored actual SAM masks only. No new inference, expert GT or automatic angle selection. Inner ROI is a fixed image-normalized interval, not a general optimum.'),ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps(dict(name=im['name'],candidate_id=c['id'],full=[(r['name'],r.get('angle_deg'),r.get('residual_px'),r.get('error')) for r in result['rows']],inner=[(r['name'],r.get('angle_deg'),r.get('residual_px'),r.get('error')) for r in inner['rows']]),ensure_ascii=False),flush=True)
    p.save()


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--output',required=True);main(a.parse_args())
