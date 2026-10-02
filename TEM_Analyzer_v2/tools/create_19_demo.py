"""Actual SAM → layer → rotation test; no boundary refinement or GT step.

The repeated-cell montage is a test fixture, NOT a new TEM acquisition or GT.
Input source and generated images stay local. Angles are geometric test truth;
added labels/bar are simulated acquisition metadata, not material metrology truth.
"""
import argparse
import io
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.ocr import read_words
from tem_analyzer.algorithms.annotations import propose_annotations
from tem_analyzer.algorithms.metrology import rotation_transform,warp,transform_points
from tem_analyzer.services.measurement import alignment,run_measurement
from tem_analyzer.services.layers import fingerprint
from tem_analyzer.preprocessing import exclusion_mask


def build(args):
    import torch
    torch.set_num_threads(4)
    output=Path(args.output)
    if (output/'project'/'project.json').exists():raise ValueError('Use a new output directory; existing projects are preserved.')
    output.mkdir(parents=True,exist_ok=True)
    source=Image.open(args.source).convert('RGB')
    if source.size!=(828,828):raise ValueError('This fixture expects the supplied 828×828 19.jpg.')
    crop_box=[135,24,691,744]
    tile=source.crop(crop_box).resize((278,360),Image.Resampling.LANCZOS)
    fontpath=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(fontpath),22) if fontpath.exists() else ImageFont.load_default(size=22)
    model=ModelService();model.load(args.checkpoint,'vit_b','cpu')
    p=Project(output/'project');p.state['layers']=[dict(id=1,name='19 upper cells',color='#28dc82',locked=False)]
    for k in ('alignments','measurements','annotation_proposals','gt_reviews'):p.state.setdefault(k,{})
    report=[]
    for index,(count,angle) in enumerate([(1,0),(1,7),(3,0),(3,7),(3,-8)]):
        im=Image.new('RGB',(count*278+100,460),(220,220,220))
        centers=[];boxes=[]
        for i in range(count):
            x=50+i*278;y=50;im.paste(tile,(x,y))
            centers.append([x+(415-135)*.5,y+(190-24)*.5])
            boxes.append([[x+(182-135)*.5,y+(57-24)*.5],[x+(653-135)*.5,y+(350-24)*.5]])
        transform=rotation_transform(np.array(im).shape[:2],angle)
        rotated=warp(np.array(im),transform,1,220)
        # Rotate then crop away an outer strip: exercises changed origins as requested.
        trim=20;rotated=rotated[trim:-trim,trim:-trim]
        adjusted=np.asarray(transform['matrix']);adjusted[:2,2]-=trim
        centers=transform_points(centers,adjusted)
        im=Image.fromarray(rotated);w,h=im.size
        # Synthetic, explicitly labelled footer. Metadata remains horizontal after acquisition.
        frame=Image.new('RGB',(w,h+90),(24,24,24));frame.paste(im,(0,0));draw=ImageDraw.Draw(frame)
        draw.rectangle([4,2,83,33],fill=(24,24,24));draw.text((9,4),'120 k',font=font,fill='white')
        draw.text((22,h+2),'100 nm',font=font,fill='white');draw.rectangle([20,h+34,100,h+38],fill='white')
        draw.text((12,h+57),'TEST 19 CROP' if count==1 else 'TEST 19 CROP REPEAT | SYNTHETIC MONTAGE',font=font,fill='white')
        name=f'19_crop_{count}cell_{angle:+03d}deg.png';frame.save(output/name)
        buf=io.BytesIO();frame.save(buf,format='PNG');iid=p.add_image(buf.getvalue(),name)
        image=np.array(frame);proposal=propose_annotations(image,read_words(image,args.ocr_dir,'en'))
        p.state['preprocessing'][iid].update(auto_regions=proposal['template'],regions_applied=True,scale_status='proposed')
        p.state['preprocessing'][iid]['excluded_pixels']=int(exclusion_mask(p,iid).sum())
        if not proposal['scale'].get('nm_per_px') or abs(proposal['scale']['nm_per_px']-100/81)>.03:raise AssertionError('OCR scale failure: '+name)
        # Real OCR is validated against this known simulated bar, then explicitly confirmed for this test.
        p.state['scale'][iid]=dict(proposal['scale'],confirmed=True)
        masks=[]
        for i,(center,box) in enumerate(zip(centers,boxes)):
            lo,hi=np.array(box);corners=[[lo[0],lo[1]],[hi[0],lo[1]],hi,[lo[0],hi[1]]]
            pts=transform_points(corners,adjusted);bb=[*pts.min(axis=0),*pts.max(axis=0)]
            item=model.prompt(image,[[*center,1]],list(map(float,bb)))
            m=item['mask'];c=p.put_candidate(iid,m,'real-SAM-19-crop',score=float(item['score']),prompts={'points':[[*center,1]],'box':bb})
            c.update(layer_id=1,instance_id=f'cell_{i+1}',reviewed=False,name=f'SAM cell {i+1}')
            masks.append(m)
        cfg={'layer_id':1,'mode':'objects' if count>1 else 'edge','edge':'top'}
        if count==1:
            yy,xx=np.nonzero(masks[0]);x0,x1=np.quantile(xx,[.15,.85])
            cfg['roi']=[float(x0/image.shape[1]),0,float(x1/image.shape[1]),1]
        rot=alignment(p,iid,cfg);rot['confirmed']=True;p.state['alignments'][iid]=rot
        proposal['input_hash']=fingerprint(p,iid);p.state['annotation_proposals'][iid]=proposal
        aligned=warp(image,rot['transform'],1);Image.fromarray(aligned).save(output/(Path(name).stem+'_aligned.png'))
        measurement=run_measurement(p,iid,{'layer_id':1,'axis':'thickness','start':0,'stop':rot['transform']['width']-1,'step':10})
        p.state['measurements'][iid]=measurement
        baseline=next((r['estimated_correction_deg'] for r in report if r['cells']==count and r['injected_angle_deg']==0),rot['transform']['angle_deg'])
        error=(rot['transform']['angle_deg']-baseline)+angle
        row=dict(image=name,image_id=iid,cells=count,injected_angle_deg=angle,estimated_correction_deg=rot['transform']['angle_deg'],
                 relative_angle_error_deg=error,fit_residual_px=rot['fit']['residual_px'],rotation_config=cfg,
                 masks=len(masks),gt_created=False,boundary_refined=False,measurement_review=measurement['review_status'],
                 measurements=measurement['summary'],ocr_regions=proposal['regions'])
        report.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        if abs(error)>1:raise AssertionError('Relative rotation error >1°: '+name)
        if measurement['summary']['count']==0:raise AssertionError('No usable measurements: '+name)
    p.save()
    (output/'validation.json').write_text(json.dumps(dict(source_crop=crop_box,resize_factor=.5,source='user-provided 19.jpg',
        disclaimer='Repeated copies, simulated acquisition overlays; not independent samples or material ground truth.',
        pipeline='actual local SAM -> assigned unreviewed layer -> rotation -> provisional measurements; NO boundary or GT',
        images=report),ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS: 5 real-SAM crop/rotation images. Project:',p.root,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--checkpoint',required=True)
    parser.add_argument('--ocr-dir',required=True);parser.add_argument('--output',required=True);build(parser.parse_args())
