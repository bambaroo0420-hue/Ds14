"""Known-geometry and negative controls for the experimental direction proposer."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.algorithms.orientation import image_direction


def main(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory.')
    out.mkdir(parents=True);rng=np.random.default_rng(20260930)
    yy,xx=np.mgrid[:512,:512];cases=[]
    for angle in (-80,-60,-45,-25,-7,0,7,25,45,60,80):
        phase=yy*np.cos(np.deg2rad(angle))-xx*np.sin(np.deg2rad(angle))
        for noise in (0,20):
            gray=np.clip(50+140*((phase%60)<25)+rng.normal(0,noise,phase.shape),0,255).astype(np.uint8)
            cases.append((f'stripes_{angle:+03d}_noise{noise}',np.repeat(gray[...,None],3,2),angle,'known_direction'))
    for name,gray in [('uniform',np.full((512,512),128)),('noise',rng.uniform(0,255,(512,512))),
                      ('rings',50+140*((np.hypot(xx-256,yy-256)%50)<22)),
                      ('checkerboard',50+140*((xx//64+yy//64)%2)),
                      ('wavy',50+140*(((yy+30*np.sin(xx/50))%60)<25))]:
        cases.append((name,np.repeat(np.uint8(gray)[...,None],3,2),None,'no_single_global_straight_direction'))
    records=[]
    for name,image,expected,kind in cases:
        Image.fromarray(image).save(out/(name+'.png'))
        item=dict(name=name,kind=kind,expected_angle_deg=expected)
        try:
            result=image_direction(image,np.zeros(image.shape[:2],bool));item.update(status='proposed',result=result)
            if expected is not None:item['error_deg']=float(abs((result['angle_deg']-expected+90)%180-90))
        except ValueError as e:item.update(status='rejected',error=str(e))
        records.append(item)
    (out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([dict(name=r['name'],status=r['status'],error_deg=r.get('error_deg'),reliable=r.get('result',{}).get('reliable_proposal'),coherence=r.get('result',{}).get('tensor_coherence')) for r in records],ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);main(p.parse_args())
