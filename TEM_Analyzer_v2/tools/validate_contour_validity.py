"""Separate binary contour metrology validity from SAM segmentation quality.

Generated band widths are continuous definitions sampled at pixel centres; thin
diagonal bands have rasterization uncertainty. No model inference or source edits.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.algorithms.metrology import measure,rotation_transform
from tem_analyzer.storage import Project
from tem_analyzer.services.measurement import run_measurement


def main(args):
    out=Path(args.output)
    if out.exists():raise ValueError('Use a new JSON path')
    out.parent.mkdir(parents=True,exist_ok=True);rows=[];start=time.perf_counter()
    for width in (1,3,10,20):
        for angle in (0,7,30,45,-30,89):
            yy,xx=np.mgrid[:128,:192];t=np.deg2rad(angle);q=(yy-64)*np.cos(t)-(xx-96)*np.sin(t);mask=(q>=0)&(q<width)
            tr=rotation_transform(mask.shape,-angle);mid=tr['width']//2
            # Validity=mask is the actual partial-GT target contract. all_true is
            # diagnostic control only, never substituted into a saved project.
            for mode in ('target_valid','all_true_diagnostic','explicit_invalid'):
                valid=mask.copy() if mode!='all_true_diagnostic' else np.ones_like(mask)
                if mode=='explicit_invalid':valid[:,94:98]=False
                r=measure(mask,valid,tr,'thickness',mid-20,mid+20,1,1)
                rows.append(dict(width=width,angle=angle,validity=mode,summary=r['summary'],rows=r['rows']))
    real=[]
    if args.project:
        p=Project(args.project)
        for iid,old in p.state['measurements'].items():
            # In-memory hash refresh of saved rotation only, never p.save(). The
            # rotation matrices and actual SAM masks must remain byte-identical.
            from tem_analyzer.services.layers import fingerprint
            p.state['alignments'][iid]['input_hash']=fingerprint(p,iid)
            r=run_measurement(p,iid,old['config'])
            before={tuple([x['position_px'],x.get('segment')]):x for x in old['rows']}
            changes=[dict(position_px=x['position_px'],segment=x.get('segment'),before=before[(x['position_px'],x.get('segment'))]['status'],after=x['status']) for x in r['rows'] if x['status']!=before[(x['position_px'],x.get('segment'))]['status']]
            unchanged_lengths=all(x.get('raw_length_nm')==before[(x['position_px'],x.get('segment'))].get('raw_length_nm') for x in r['rows'])
            if not unchanged_lengths:raise AssertionError('Validity change modified geometry')
            real.append(dict(name=p.state['images'][iid]['name'],image_id=iid,old=old['summary'],new=r['summary'],changes=changes,raw_lengths_unchanged=unchanged_lengths))
    report=dict(cases=rows,actual_masks=real,seconds=time.perf_counter()-start,contract='No SAM calls. Same synthetic binary geometry across validity modes. all_true is diagnostic only. Real project matrices/masks retained; no project save. Thickness bias includes binary sampling; not TEM expert accuracy.')
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(cases=len(rows),seconds=report['seconds'],actual_masks=[{**{k:v for k,v in r.items() if k!='changes'},'changed_rows':len(r['changes'])} for r in real]),ensure_ascii=False),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--project');main(a.parse_args())
