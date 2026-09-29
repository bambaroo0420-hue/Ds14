"""Diagnostic paired-mask ECC on known 19 crop/rotation geometry; read-only source."""
import argparse,json,sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.services.prompt_transfer import resize_matrix
from tem_analyzer.operations import excluded
from tem_analyzer.algorithms.metrology import rotation_transform,transform_points


def main(args):
    root=Path(args.project);state=json.loads((root/'project.json').read_text(encoding='utf8'));rows=[]
    for cells in (1,3):
        ids=[i for i,v in state['images'].items() if f'_{cells}cell_' in v['name']]
        source_id=next(i for i in ids if '+00deg' in state['images'][i]['name'])
        source=np.array(Image.open(root/'images'/f'{source_id}.png').convert('RGB'));sh,sw=source.shape[:2]
        source_ex=excluded((sh,sw),state['preprocessing'][source_id].get('auto_regions',{}))
        for iid in ids:
            if iid==source_id:continue
            target=np.array(Image.open(root/'images'/f'{iid}.png').convert('RGB'));h,w=target.shape[:2]
            angle=7 if '+07deg' in state['images'][iid]['name'] else -8
            known=np.array(rotation_transform((460,cells*278+100),angle)['matrix']);known[:2,2]-=20
            known=known@np.array([[1,0,20],[0,1,20],[0,0,1]])
            ratio=min(1,512/max(h,w));size=(round(w*ratio),round(h*ratio));ww,hh=size
            dst=resize_matrix(target.shape,size);src=dst@np.array([[1,0,(w-sw)/2],[0,1,(h-sh)/2],[0,0,1]])
            a=cv2.warpAffine(source.mean(2).astype('float32')/255,src[:2].astype('float32'),size,borderValue=float(np.median(source)/255))
            b=cv2.resize(target.mean(2).astype('float32')/255,size)
            ex=excluded((h,w),state['preprocessing'][iid].get('auto_regions',{}))
            am=cv2.warpAffine(np.uint8(~source_ex)*255,src[:2].astype('float32'),size,flags=cv2.INTER_NEAREST)
            bm=cv2.resize(np.uint8(~ex)*255,size,interpolation=cv2.INTER_NEAREST)
            for margin in (0,.08,.15,.25):
                valid=np.zeros((hh,ww),np.uint8);valid[round(hh*margin):round(hh*(1-margin)),round(ww*margin):round(ww*(1-margin))]=255
                fits=[]
                for seed in (-10,0,10):
                    initial=cv2.getRotationMatrix2D(((ww-1)/2,(hh-1)/2),seed,1).astype('float32')
                    try:
                        score,small=cv2.findTransformECCWithMask(a,b,am&valid,bm&valid,initial,cv2.MOTION_EUCLIDEAN,(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,150,1e-6),5)
                        fits.append((score,small))
                    except cv2.error:pass
                row=dict(name=state['images'][iid]['name'],margin=margin)
                if fits:
                    score,small=max(fits,key=lambda x:x[0]);m=np.eye(3);m[:2]=small;m=np.linalg.inv(dst)@m@src
                    pts=[[sw*.25,sh*.25],[sw*.5,sh*.4],[sw*.75,sh*.6]]
                    row.update(score=score,angle=float(np.degrees(np.arctan2(m[1,0],m[0,0]))),max_control_error_px=float(np.linalg.norm(transform_points(pts,m)-transform_points(pts,known),axis=1).max()))
                else:row['failed']=True
                rows.append(row);print(json.dumps(row),flush=True)
    print('OpenCV',cv2.__version__,flush=True)
    if args.output:Path(args.output).write_text(json.dumps(rows,indent=2),encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--output');main(p.parse_args())
