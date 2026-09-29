"""Deterministic 19.jpg augmentations and an independent synthetic UI/QC project."""
import argparse
import io
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageEnhance
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project


def build(source,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=Path(source);original=Image.open(source).convert('RGB');original.thumbnail((720,720))
    rng=np.random.default_rng(19)
    variations=[('19_resized',original,{'kind':'resize','source_size':list(Image.open(source).size),'size':list(original.size)}),
        ('19_brightness',ImageEnhance.Brightness(original).enhance(.8),{'kind':'brightness','factor':.8}),
        ('19_noise',Image.fromarray(np.clip(np.asarray(original).astype(float)+rng.normal(0,3,(*original.size[::-1],1)),0,255).astype('uint8')),{'kind':'noise','std':3,'seed':19}),
        ('19_rotated',original.rotate(4,resample=Image.Resampling.BICUBIC,expand=True,fillcolor=(30,30,30)),{'kind':'rotation','pil_ccw_angle':4,'expanded':True})]
    records=[]
    for name,img,transform in variations:
        img.save(output/(name+'.png'));records.append(dict(name=name+'.png',transform=transform,accuracy_reference=False))
    p=Project(output/'ui-project')
    if p.state['images']:raise ValueError('검증 프로젝트가 이미 있습니다. 새 출력 폴더를 사용하세요.')
    p.state['layers']=[dict(id=1,name='Upper film',color='#28dc82',locked=False),dict(id=2,name='Lower film',color='#66aaff',locked=False)]
    fontpath=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(fontpath),22) if fontpath.exists() else ImageFont.load_default(size=22)
    for index,(slope,shift) in enumerate([(0.,0),(.05,12),(-.06,24)]):
        h,w=400,600;yy,xx=np.mgrid[:h,:w]
        a=(yy>=85+slope*xx)&(yy<145+slope*xx)&(xx>=35)&(xx<565)
        b=(yy>=145+slope*xx)&(yy<215+slope*xx)&(xx>=35)&(xx<565)
        image=np.full((h,w,3),38,np.uint8);image[a]=110;image[b]=190
        im=Image.fromarray(image);draw=ImageDraw.Draw(im)
        draw.text((16,10),'120 k',fill='white',font=font)
        draw.rectangle((20+shift,335,139+shift,340),fill='white');draw.text((30+shift,301),'100 nm',fill='white',font=font)
        draw.text((14,370),'DEMO TEM  |  Sample 19  |  Synthetic QA',fill='white',font=font)
        buf=io.BytesIO();im.save(buf,format='PNG');iid=p.add_image(buf.getvalue(),f'synthetic_{index}.png')
        for lid,m in [(1,a),(2,b)]:
            c=p.put_candidate(iid,m,'analytic-fixture');c.update(layer_id=lid,reviewed=False,instance_id=f'film_{lid}')
        p.state['scale'][iid]=dict(nm_per_px=100/120,confirmed=False,bar=[[20+shift,337.5],[140+shift,337.5]],pixel_length=120,length=100,unit='nm',source='synthetic-known')
        im.save(output/f'synthetic_{index}.png')
        records.append(dict(name=f'synthetic_{index}.png',image_id=iid,slope=slope,upper_thickness_px=60/np.sqrt(1+slope*slope),bar_pixels=120,bar_length_nm=100,accuracy_reference=True))
    p.save()
    (output/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    print(json.dumps({'output':str(output.resolve()),'images':len(records),'ui_project':str(p.root)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);args=parser.parse_args();build(args.source,args.output)
