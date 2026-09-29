"""Rotation equivariance on real images; this is NOT expert orientation accuracy."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.algorithms.orientation import image_direction
from tem_analyzer.algorithms.metrology import rotation_transform,warp
from tem_analyzer.operations import excluded


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory.')
    out.mkdir(parents=True);rows=[]
    roots=[Path(p).resolve() for p in args.project]
    for root in roots:
        if not (root/'project.json').is_file():raise ValueError(f'Not a project directory: {root}')
    def save():
        report=dict(contract='Known added rotation compared with same-image baseline. Baseline may be wrong; equivariance is NOT layer-boundary accuracy. Original files/projects read only. OCR exclusion/padding transformed identically.',rows=rows)
        (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    for root in roots:
        state=json.loads((root/'project.json').read_text(encoding='utf8'));selected={}
        for prefix in args.names.split(','):
            ids=[i for i,v in state['images'].items() if v['name'].startswith(prefix)]
            if ids:selected[prefix]=ids[0]
        for name,iid in selected.items():
            image=np.array(Image.open(root/'images'/f'{iid}.png').convert('RGB'));h,w=image.shape[:2]
            template=state['preprocessing'][iid].get('auto_regions',{'scale_roi':None,'text_rois':[]})
            ex=excluded((h,w),template);base=None
            for angle in (0,-60,-30,-15,15,30,60):
                transform=rotation_transform((h,w),angle);im=warp(image,transform,1,0)
                rotated_ex=warp(ex.astype('uint8'),transform,0,1).astype(bool)
                # Rotated canvas padding is excluded explicitly, never treated as structure.
                valid=warp(np.ones((h,w),np.uint8),transform,0,0).astype(bool);rotated_ex|=~valid
                record=dict(case=name,added_angle_deg=angle,source_project=root.parent.name+'/'+root.name)
                try:
                    fit=image_direction(im,rotated_ex);record.update(status='proposed',fit=fit)
                    if angle==0:base=fit['angle_deg']
                    if base is not None:record['equivariance_error_deg']=float(abs((fit['angle_deg']-base-angle+90)%180-90))
                except ValueError as e:record.update(status='rejected',error=str(e))
                rows.append(record);Image.fromarray(im).save(out/f'{root.parent.name}_{root.name}_{name}_{angle:+03d}.png');save()
                print(json.dumps({k:record[k] for k in ('case','added_angle_deg','status','equivariance_error_deg') if k in record}),flush=True)
    save()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',action='append',required=True);p.add_argument('--names',default='existing_43,existing_140,existing_143,attached_45deg')
    p.add_argument('--output',required=True);main(p.parse_args())
