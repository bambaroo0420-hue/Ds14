"""Reproducible 19-derived augmentation consistency audit (not material GT).

Known affine maps separate segmentation failure from prompt-transfer failure.
The oracle map is test instrumentation, NOT an implemented automatic registration.
"""
import argparse
import io
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.services.prompt_transfer import save_preset, preview_preset, transfer_matrix
from tem_analyzer.preprocessing import exclusion_mask, model_input
from tem_analyzer.labels import pack
from tem_analyzer.algorithms.metrology import transform_points


def main(args):
    import torch
    torch.set_num_threads(4)
    source=Path(args.source).resolve();out=Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=False)
    original=json.loads((source/'project.json').read_text(encoding='utf8'))
    iid='8d0ab21d53e9';info=original['images'][iid];candidate=original['candidates'][iid][0]
    image=np.asarray(Image.open(source/'images'/f'{iid}.png').convert('RGB'))
    reference=np.asarray(Image.open(source/'masks'/f"{iid}_{candidate['id']}.png").convert('L'))>0
    h,w=image.shape[:2];p=Project(out/'project');buf=io.BytesIO();Image.fromarray(image).save(buf,format='PNG')
    source_id=p.add_image(buf.getvalue(),'source_19_1cell.png')
    p.state['preprocessing'][source_id].update(original['preprocessing'][iid]);source_ex=exclusion_mask(p,source_id)
    draft=dict(auto_points=[],manual_points=candidate['prompts']['points'],box=candidate['prompts']['box'],manual_mode='object')
    save_preset(p,source_id,'manual_reference',draft);p.save()
    identity=np.eye(3);rotate=identity.copy();rotate[:2]=cv2.getRotationMatrix2D(((w-1)/2,(h-1)/2),12,1)
    translate=identity.copy();translate[:2,2]=[22,-9]
    scale=identity.copy();nw,nh=round(w*1.2),round(h*1.2);scale[0,0]=nw/w;scale[1,1]=nh/h;scale[:2,2]=[(nw/w-1)/2,(nh/h-1)/2]
    stretch=identity.copy();stretch[0,0]=1.25;stretch[1,1]=.9
    specs=[('baseline',identity,(w,h),'none'),('brightness_065',identity,(w,h),'dark'),
           ('noise_sigma12',identity,(w,h),'noise'),('shift_22_minus9',translate,(w,h),'none'),
           ('resize_120pct',scale,(nw,nh),'none'),('stretch_x125_y090',stretch,(round(w*1.25),round(h*.9)),'none'),
           ('rotate12_same_frame',rotate,(w,h),'none')]
    model=ModelService();model.load(args.checkpoint,'vit_b','cpu')
    report=dict(contract='19-derived controlled consistency, previous SAM is not expert GT; known affine is oracle only. Anisotropic stretch cannot use a single nm/px.',seed=20261001,rows=[])
    rng=np.random.default_rng(20261001)
    for name,matrix,size,photo in specs:
        rgb=cv2.warpAffine(image,matrix[:2],size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(180,180,180))
        truth=cv2.warpAffine(reference.astype('uint8'),matrix[:2],size,flags=cv2.INTER_NEAREST)>0
        excluded=cv2.warpAffine(source_ex.astype('uint8'),matrix[:2],size,flags=cv2.INTER_NEAREST,borderValue=1)>0
        if photo=='dark':rgb=np.uint8(np.clip(rgb.astype(float)*.65,0,255))
        if photo=='noise':rgb=np.uint8(np.clip(rgb.astype(float)+rng.normal(0,12,rgb.shape),0,255))
        stream=io.BytesIO();Image.fromarray(rgb).save(stream,format='PNG');target=p.add_image(stream.getvalue(),name+'.png')
        p.state['annotations'][target]={'exclude':pack(excluded)};p.save()
        methods=['normalized','known_affine'] if name not in ('baseline','brightness_065','noise_sigma12') else ['normalized']
        if name in ('shift_22_minus9','rotate12_same_frame'):methods.append('ecc')
        for method in methods:
            started=time.perf_counter();row=dict(name=name,method=method,matrix=matrix.tolist(),size=list(size))
            try:
                if method=='known_affine':
                    dots=transform_points(np.array(draft['manual_points'])[:,:2],matrix)
                    points=[[*xy,int(old[2])] for xy,old in zip(dots,draft['manual_points'])]
                    x0,y0,x1,y1=draft['box'];corners=transform_points([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],matrix)
                    lo=corners.min(0);hi=corners.max(0);box=[max(0,float(lo[0])),max(0,float(lo[1])),min(size[0],float(hi[0])),min(size[1],float(hi[1]))]
                    row['registration_note']='Known injected map; not app auto-registration'
                else:
                    proposal=preview_preset(p,target,'manual_reference',method)
                    points=proposal['draft']['manual_points'];box=proposal['draft']['box']
                    row.update(ecc_score=proposal['ecc_score'],warnings=proposal['warnings'],used_matrix=proposal['matrix'])
                result=model.prompt(model_input(p,target),points,box)
                mask=np.asarray(result['mask'])&~excluded
                known=truth&~excluded
                iou=float((known&mask).sum()/max(1,(known|mask).sum()))
                saved=p.put_candidate(target,mask,'actual-SAM-'+method,score=float(result['score']),prompts=dict(points=points,box=box))
                row.update(status='executed',candidate_id=saved['id'],iou_to_transformed_previous_sam=iou,area=int(mask.sum()),reference_area=int(known.sum()),score=float(result['score']))
                # Diagnostic overlay only; never writes back to source or measurement pixels.
                overlay=rgb.astype(float);overlay[mask]=overlay[mask]*.6+np.array([20,220,150])*.4
                Image.fromarray(np.uint8(overlay)).save(out/f'{name}_{method}_overlay.png')
            except Exception as exc:row.update(status='blocked',error=str(exc))
            row['seconds']=round(time.perf_counter()-started,3);report['rows'].append(row)
            (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');p.save()
            print(json.dumps({k:v for k,v in row.items() if k not in ('matrix','used_matrix')},ensure_ascii=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);parser.add_argument('--checkpoint',required=True)
    main(parser.parse_args())
