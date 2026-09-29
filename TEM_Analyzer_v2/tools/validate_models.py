"""Real (not mocked) local SAM and EasyOCR smoke checks, with saved evidence."""
import argparse
import json
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.sam_service import ModelService
from tem_analyzer.ocr import read_words,_reader
from tem_analyzer.algorithms.annotations import propose_annotations


def main(args):
    import torch
    torch.set_num_threads(4)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    model=ModelService();t=time.perf_counter();info=model.load(args.checkpoint,'vit_b','cpu');records=[]
    print('SAM loaded',round(time.perf_counter()-t,2),flush=True)
    for path in sorted(Path(args.fixtures).glob('19_*.png')):
        image=np.array(Image.open(path).convert('RGB'));h,w=image.shape[:2];start=time.perf_counter()
        result=model.prompt(image,[[w*.5,h*.45,1]],None)
        if result['mask'].shape!=(h,w) or not result['mask'].any():raise AssertionError('Invalid real SAM output')
        Image.fromarray(result['mask'].astype('uint8')*255).save(out/(path.stem+'_sam.png'))
        words=read_words(image,args.ocr_dir,'en');proposal=propose_annotations(image,words)
        # The source 19.jpg bar spans approximately 161 original pixels; these
        # fixtures resize 828 -> 720, with rotation but no further scale change.
        expected=100/(161*720/828)
        if not proposal['scale'].get('nm_per_px') or abs(proposal['scale']['nm_per_px']/expected-1)>.03:
            raise AssertionError('19.jpg scale differs by >3%: '+path.name)
        records.append(dict(image=path.name,mask_pixels=int(result['mask'].sum()),score=float(result['score']),seconds=time.perf_counter()-start,ocr=proposal))
        print(path.name,records[-1]['mask_pixels'],'pixels',round(records[-1]['seconds'],2),'s',flush=True)
    for path in sorted(Path(args.fixtures).glob('synthetic_*.png')):
        im=np.array(Image.open(path).convert('RGB'));p=propose_annotations(im,read_words(im,args.ocr_dir,'en'))
        if not p['scale'].get('nm_per_px'):raise AssertionError('Synthetic OCR failed: '+path.name)
        if abs(p['scale']['nm_per_px']-100/120)>.02:raise AssertionError('Synthetic scale incorrect')
        records.append(dict(image=path.name,ocr=p))
    # Automatic generation exercises the actual batched SAM path once.
    im=np.array(Image.open(Path(args.fixtures)/'19_resized.png').convert('RGB'));start=time.perf_counter()
    items=model.automatic(im,4,.5,.7,.8,np.zeros(im.shape[:2],bool))
    if not items:raise AssertionError('Real automatic SAM produced no candidates')
    report=dict(model=info,records=records,automatic=dict(grid=4,count=len(items),seconds=time.perf_counter()-start),ocr_cache=str(_reader.cache_info()))
    (out/'real_model_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS real models;',len(records),'images;',len(items),'automatic candidates; OCR',_reader.cache_info(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--ocr-dir',required=True);p.add_argument('--fixtures',required=True);p.add_argument('--output',required=True);main(p.parse_args())
