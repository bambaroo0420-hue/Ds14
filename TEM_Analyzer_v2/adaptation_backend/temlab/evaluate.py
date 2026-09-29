from pathlib import Path
import csv, gc, json, time, hashlib
import numpy as np
from PIL import Image,ImageDraw
import torch
from .data import read_manifest,load_image,load_mask,targets,grid_prompts,dump_json,sample_prompt,center_point
from .models import Engine,safe_load
from .metrics import filter_candidates,candidate_metrics,overlap,boundary_metrics


def sync(engine):
    if engine.device.type=='cuda': torch.cuda.synchronize(engine.device)


def overlay(image,masks,prompts=None,gt=None):
    im=image.astype(np.float32).copy(); rng=np.random.default_rng(123)
    from scipy import ndimage as ndi
    for m in masks:
        color=rng.integers(40,245,3); im[m]=im[m]*.65+color*.35
        edge=m&~ndi.binary_erosion(m); im[edge]=color
    if gt is not None:
        for g in gt:im[g&~ndi.binary_erosion(g)]=[255,255,255]
    out=Image.fromarray(np.clip(im,0,255).astype(np.uint8)); draw=ImageDraw.Draw(out)
    for p in prompts or []:
        for (x,y),label in zip(p.get('points',[]),p.get('labels',[])):
            draw.ellipse((x-3,y-3,x+3,y+3),fill='lime' if label else 'red',outline='black')
    return out


def save_csv(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def predict_grid(engine,image,cfg):
    sync(engine);start=time.perf_counter();encoded=engine.encode(image);sync(engine)
    encode_seconds=time.perf_counter()-start
    prompts=grid_prompts(*image.shape[:2],cfg['grid_points_per_side'])
    sync(engine);start=time.perf_counter()
    def probabilities():
        for p in prompts:
            with torch.no_grad():z,_=engine.predict_logits(image,encoded,p)
            yield z.sigmoid()[0,0].cpu().numpy()
    # No GT used to construct or select prompts/candidates.
    candidates=filter_candidates(probabilities(),cfg)
    sync(engine)
    return candidates,prompts,encoded,encode_seconds,time.perf_counter()-start


def evaluate(cfg,checkpoint=None,split='test',tag='baseline',diagnostic=True):
    """Test is explicit; training never calls this on test. Lock cfg on validation first."""
    rows=[r for r in read_manifest(cfg['manifest']) if r['split']==split]
    if split not in ('val','test'):raise ValueError('Evaluation split must be val or test')
    if not rows:
        raise ValueError(f'No labelled {split} rows in manifest. For images without GT use 03_predict_test_images.ipynb.')
    method='baseline'
    excluded_groups=set();excluded_hashes=set()
    if checkpoint:
        pack=safe_load(checkpoint);method=pack['method']
        excluded_groups.update(pack['extra'].get('train_groups',[]))
        excluded_hashes.update(pack['extra'].get('train_pixel_hashes',[]))
        if split=='test':
            excluded_groups.update(pack['extra'].get('val_groups',[]))
            excluded_hashes.update(pack['extra'].get('val_pixel_hashes',[]))
        for key in ['model_type','preprocessing','refiner_width','refine_side']:
            if cfg[key]!=pack['config'][key]:raise ValueError(f'Inference config differs from checkpoint: {key}')
    engine=Engine(cfg,method)
    if checkpoint:engine.load_weights(checkpoint)
    engine.trainable.eval()
    out=Path(cfg['output_dir'])/'evaluation'/split/tag
    if out.exists() and any(out.iterdir()):raise FileExistsError(f'{out} exists. Rename tag to retain the previous evaluation.')
    out.mkdir(parents=True,exist_ok=True);dump_json(out/'evaluation_config.json',cfg)
    all_summary=[];all_details=[];all_diag=[]
    for r in rows:
        image=load_image(r['image'],cfg['preprocessing'])
        if r['group'] in excluded_groups or hashlib.sha256(image.tobytes()).hexdigest() in excluded_hashes:
            raise ValueError('Evaluation data overlaps checkpoint training/selection data. Restore the original split.')
        candidates,prompts,encoded,encode_seconds,grid_seconds=predict_grid(engine,image,cfg)
        # GT is loaded only after the operational predictions have been generated.
        gt=load_mask(r['mask'],cfg);valid=gt!=cfg['ignore_label'];truth=targets(gt,cfg)
        scored=[c for c in candidates if (c['mask']&valid).any()]
        summary,details=candidate_metrics(scored,truth,valid,cfg)
        summary.update(image_id=r['image_id'],group=r['group'],model=tag,encode_or_cache_seconds=encode_seconds,
                       grid_seconds=grid_seconds,prompt_count=len(prompts),displayed_candidates=len(candidates))
        all_summary.append(summary)
        all_details.extend([dict(image_id=r['image_id'],model=tag,**x) for x in details])
        image_out=out/r['image_id'];image_out.mkdir(exist_ok=True)
        overlay(image,[c['mask'] for c in candidates],prompts).save(image_out/'grid_predictions.png')
        overlay(image,[g for _,g in truth]).save(image_out/'gt_regions.png')
        packed=np.stack([np.packbits(c['mask'].ravel()) for c in candidates]) if candidates else np.empty((0,(gt.size+7)//8),np.uint8)
        np.savez_compressed(image_out/'grid_candidates.npz',packed_masks=packed,shape=np.array(gt.shape),
                            prompt_index=np.array([c['prompt_index'] for c in candidates]),stability=np.array([c['stability'] for c in candidates]))
        dump_json(image_out/'grid_prompts.json',prompts)
        if diagnostic:
            for j,(cls,region) in enumerate(truth):
                p=sample_prompt(region,np.random.default_rng(0),'center')
                with torch.no_grad():z,_=engine.predict_logits(image,encoded,p)
                pred=z.sigmoid()[0,0].cpu().numpy()>=cfg['mask_threshold']
                s=overlap(pred,region,valid);s.update(boundary_metrics(pred,region,valid,cfg['boundary_tolerance_px']))
                s.update(image_id=r['image_id'],class_id=int(cls),gt_index=j,model=tag,protocol='GT-derived center point: diagnostic only')
                all_diag.append(s)
                overlay(image,[pred],[p],gt=[region]).save(image_out/f'diagnostic_region_{j:03d}_whiteGT.png')
        print(f'{tag} {r["image_id"]}: recall={summary["region_recall"]}, candidates={len(candidates)}',flush=True)
    save_csv(out/'grid_per_image.csv',all_summary);save_csv(out/'grid_per_gt.csv',all_details)
    save_csv(out/'diagnostic_center_prompt.csv',all_diag)
    tp=sum(r['tp'] for r in all_summary);fp=sum(r['fp'] for r in all_summary);fn=sum(r['fn'] for r in all_summary)
    aggregate=dict(model=tag,protocol='fixed grid; class-agnostic connected-region matching',
                   images=len(rows),tp=tp,fp=fp,fn=fn,
                   region_precision=tp/(tp+fp) if tp+fp else None,
                   region_recall=tp/(tp+fn) if tp+fn else None,
                   region_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)
    for key in ['mean_best_iou','boundary_f1_all_gt','grid_seconds','small_region_recall']:
        values=[r[key] for r in all_summary if r[key] is not None]
        aggregate[f'image_mean_{key}']=float(np.mean(values)) if values else None
    if all_diag: aggregate['diagnostic_region_mean_dice']=float(np.mean([r['dice'] for r in all_diag]))
    dump_json(out/'summary.json',aggregate)
    save_csv(out/'manual_correction_time_template.csv',[dict(image_id=r['image_id'],model=tag,
        correction_seconds='',extra_clicks='',completed='',notes='') for r in rows])
    del engine;gc.collect()
    if torch.cuda.is_available():torch.cuda.empty_cache()
    return aggregate


def compare_all(cfg,checkpoints,split='test',diagnostic=True):
    results=[evaluate(cfg,None,split,'baseline',diagnostic)]
    for name,path in checkpoints.items():results.append(evaluate(cfg,path,split,name,diagnostic))
    root=Path(cfg['output_dir'])/'evaluation'/split
    save_csv(root/'comparison.csv',results);dump_json(root/'comparison.json',results)
    return results
