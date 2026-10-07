"""Actual SAM/OCR audit of the attached diagonal W/TaOx/TiON/TiN example."""
import argparse
import io
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.storage import Project
from tem_analyzer.sam_service import ModelService
from tem_analyzer.ocr import read_words
from tem_analyzer.algorithms.annotations import propose_annotations
from tem_analyzer.preprocessing import model_input,exclusion_mask
from tem_analyzer.calibration import bar_candidates
from tem_analyzer.services.measurement import alignment
from tem_analyzer.algorithms.metrology import warp,transform_points


def main(a):
    import torch
    torch.set_num_threads(4)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    image=np.asarray(Image.open(a.image).convert('RGB'));h,w=image.shape[:2]
    project=Project(out/'project');iid=project.add_image(Path(a.image).read_bytes(),'attached_45deg.png')
    project.state.setdefault('alignments',{});project.state.setdefault('annotation_proposals',{})
    proposal=propose_annotations(image,read_words(image,a.ocr_dir,'en',enhanced=True))
    project.state['preprocessing'][iid]['auto_regions']=proposal['template']
    project.state['annotation_proposals'][iid]=proposal
    preview=Image.fromarray(image);d=ImageDraw.Draw(preview)
    for i,r in enumerate(proposal['regions']):d.rectangle(r['box'],outline='red',width=2);d.text(r['box'][:2],str(i),fill='yellow')
    preview.save(out/'ocr_boxes.png')
    cleaned=model_input(project,iid,'prompt');Image.fromarray(cleaned).save(out/'analysis_input.png')
    model=ModelService();model.load(a.checkpoint,'vit_b','cpu')
    # Human-selected semantic object, NOT an automatic material classifier.
    points=[[100*w/600,100*h/596,1],[175*w/600,145*h/596,1],[350*w/600,350*h/596,0]]
    item=model.prompt(cleaned,points)
    mask=item['mask']&~exclusion_mask(project,iid)
    c=project.put_candidate(iid,mask,'real-SAM-assisted-W',score=float(item['score']),prompts={'points':points})
    c.update(layer_id=1,reviewed=False,name='W reference (human-selected SAM prompts)')
    rgb=image.copy();rgb[mask]=(.6*rgb[mask]+.4*np.array([20,240,130])).astype('uint8');Image.fromarray(rgb).save(out/'sam_W_overlay.png')
    results=[]
    configs=[('default_auto',{'layer_id':1,'mode':'auto','edge':'top'}),
             ('bottom_edge',{'layer_id':1,'mode':'edge','edge':'bottom'}),
             ('bottom_edge_roi',{'layer_id':1,'mode':'edge','edge':'bottom','roi':[.08,.2,.56,.72]}),
             ('manual_two_points',{'layer_id':1,'mode':'points','points':[[80*w/600,357*h/596],[300*w/600,140*h/596]]})]
    for name,cfg in configs:
        try:
            rot=alignment(project,iid,cfg)
            Image.fromarray(warp(image,rot['transform'],1)).save(out/(name+'_aligned.png'))
            Image.fromarray(warp(cleaned,rot['transform'],1)).save(out/(name+'_analysis_aligned.png'))
            residual=transform_points(rot['fit']['points'],rot['transform']['matrix'])
            results.append(dict(name=name,rotation=rot,aligned_point_y_std=float(residual[:,1].std())))
        except Exception as exc:results.append(dict(name=name,error=str(exc)))
    # Second explicitly assisted trial: denser point prompts on untouched image.
    dense=[[80,80,1],[80,240,1],[140,260,1],[200,160,1],[350,350,0],[280,290,0],[420,200,0]]
    dense=[[x*w/600,y*h/596,label] for x,y,label in dense]
    trial=model.prompt(image,dense)
    m=trial['mask']&~exclusion_mask(project,iid)
    c['active']=False
    other=project.put_candidate(iid,m,'real-SAM-assisted-W-original',score=float(trial['score']),prompts={'points':dense})
    other.update(layer_id=1,reviewed=False,name='W assisted dense points, original image')
    rgb=image.copy();rgb[m]=(.6*rgb[m]+.4*np.array([20,240,130])).astype('uint8');Image.fromarray(rgb).save(out/'sam_W_dense_overlay.png')
    for name,cfg in [('dense_original_bottom',{'layer_id':1,'mode':'edge','edge':'bottom','roi':[.08,.2,.56,.72]})]:
        try:
            rot=alignment(project,iid,cfg)
            Image.fromarray(warp(image,rot['transform'],1)).save(out/(name+'_aligned.png'))
            results.append(dict(name=name,rotation=rot,manual_SAM_prompts=dense))
        except Exception as exc:results.append(dict(name=name,error=str(exc)))
    project.save()
    report=dict(image_id=iid,ocr=proposal,bar_candidates=bar_candidates(image,[0,.8,.4,1]),
        excluded_fraction=float(exclusion_mask(project,iid).mean()),manual_SAM_prompts=points,
        mask_pixels=int(mask.sum()),rotations=results,
        warning='No GT and no automatic material naming; manual two points are an assisted fallback, not automatic success.')
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(scale=proposal['scale'].get('nm_per_px'),regions=len(proposal['regions']),excluded=report['excluded_fraction'],
        rotations=[{'name':r['name'],'angle':r.get('rotation',{}).get('transform',{}).get('angle_deg'),'residual':r.get('rotation',{}).get('fit',{}).get('residual_px'),'error':r.get('error')} for r in results]),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--output',required=True)
    p.add_argument('--checkpoint',required=True);p.add_argument('--ocr-dir',required=True);main(p.parse_args())
