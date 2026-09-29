"""Geometric controls, not material GT. Sources read-only; output JSON only."""
import argparse,json,sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.services.prompt_transfer import transfer_matrix
from tem_analyzer.operations import excluded
from tem_analyzer.algorithms.metrology import rotation_transform,transform_points


def main(args):
    root=Path(args.project);state=json.loads((root/'project.json').read_text(encoding='utf8'));rows=[]
    for cells in (1,3):
        ids=[i for i,v in state['images'].items() if f'_{cells}cell_' in v['name']]
        sid=next(i for i in ids if '+00deg' in state['images'][i]['name'])
        a=np.array(Image.open(root/'images'/f'{sid}.png').convert('RGB'));sh,sw=a.shape[:2]
        se=excluded((sh,sw),state['preprocessing'][sid].get('auto_regions',{}))
        for iid in ids:
            b=np.array(Image.open(root/'images'/f'{iid}.png').convert('RGB'));h,w=b.shape[:2]
            te=excluded((h,w),state['preprocessing'][iid].get('auto_regions',{}))
            angle=0 if iid==sid else 7 if '+07deg' in state['images'][iid]['name'] else -8
            known=np.eye(3)
            if angle:
                known=np.array(rotation_transform((460,cells*278+100),angle)['matrix']);known[:2,2]-=20
                known=known@np.array([[1,0,20],[0,1,20],[0,0,1]])
            row=dict(name=state['images'][iid]['name'],angle=angle)
            try:
                m,score=transfer_matrix(a,b,'ecc_masked',se,te)
                pts=[[sw*.25,sh*.25],[sw*.5,sh*.4],[sw*.75,sh*.6]]
                row.update(score=score,max_control_error_px=float(np.linalg.norm(transform_points(pts,m)-transform_points(pts,known),axis=1).max()),matrix=m.tolist())
            except ValueError as e:row['error']=str(e)
            rows.append(row)
    negatives=[]
    for name,b in [('flat',np.full_like(a,128)),('unrelated_noise',np.random.default_rng(333).integers(0,255,a.shape,dtype='uint8'))]:
        try:
            m,s=transfer_matrix(a,b,'ecc_masked',se,np.zeros(b.shape[:2],bool));negatives.append(dict(name=name,rejected=False,score=s))
        except ValueError as e:negatives.append(dict(name=name,rejected=True,reason=str(e)))
    result=dict(opencv=cv2.__version__,contract='Known generated 19 geometry is not material/semantic GT. Final paired-mask coarse-to-fine method.',rows=rows,negatives=negatives)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--output',required=True);main(p.parse_args())
