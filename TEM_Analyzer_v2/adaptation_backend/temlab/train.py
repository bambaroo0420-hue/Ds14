from pathlib import Path
import csv, gc, json, random, time
import numpy as np
import torch
from torch.nn import functional as F
from .data import read_manifest,load_image,load_mask,targets,sample_prompt,dump_json,audit
from .models import Engine
from .losses import ABL,segmentation_loss
from .metrics import overlap,boundary_metrics

EXPERIMENTS={'decoder_noabl':('decoder',False),'decoder_abl':('decoder',True),
             'refiner_noabl':('refiner',False),'refiner_abl':('refiner',True)}


def seed_all(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark=False


def target_tensors(logits,region,valid,cfg):
    # Loss at native resolution up to loss_side. Nearest-neighbor only for GT.
    h,w=region.shape; scale=min(1.,cfg['loss_side']/max(h,w))
    size=(max(8,round(h*scale)),max(8,round(w*scale)))
    z=F.interpolate(logits.float(),size=size,mode='bilinear',align_corners=False)
    t=torch.as_tensor(region.copy(),device=z.device)[None,None].float()
    v=torch.as_tensor(valid.copy(),device=z.device)[None,None].float()
    t=F.interpolate(t,size=size,mode='nearest')[:,0]
    v=F.interpolate(v,size=size,mode='nearest')[:,0].bool()
    if region.any() and not (t.bool()&v).any():
        raise ValueError('A target disappeared at loss resolution. Increase loss_side or use consistently cropped data.')
    return z,t,v


@torch.no_grad()
def validate(engine,rows,cfg):
    """GT-derived center-point diagnostic. NOT grid / end-to-end automatic accuracy."""
    engine.trainable.eval(); scores=[]; image_scores=[]
    for r in rows:
        image=load_image(r['image'],cfg['preprocessing']); gt=load_mask(r['mask'],cfg)
        valid=gt!=cfg['ignore_label']; encoded=engine.encode(image); local=[]
        for cls,region in targets(gt,cfg):
            prompt=sample_prompt(region,np.random.default_rng(0),'center')
            logits,_=engine.predict_logits(image,encoded,prompt)
            p=logits.sigmoid()[0,0].cpu().numpy()>=cfg['mask_threshold']
            s=overlap(p,region,valid); s.update(boundary_metrics(p,region,valid,cfg['boundary_tolerance_px']))
            s.update(image_id=r['image_id'],class_id=int(cls)); scores.append(s); local.append(s['dice'])
        if local:image_scores.append(float(np.mean(local)))
    if not image_scores: raise ValueError('No validation targets: check GT mappings/min_gt_area')
    return float(np.mean(image_scores)),scores


def train_experiment(cfg,name):
    if name not in EXPERIMENTS: raise ValueError(name)
    method,use_abl=EXPERIMENTS[name]; seed_all(cfg['seed'])
    rows=read_manifest(cfg['manifest']); report=audit(rows,cfg)
    out=Path(cfg['output_dir'])/name
    if out.exists() and any(out.iterdir()): raise FileExistsError(f'{out} exists; use a new output_dir to preserve experiments.')
    out.mkdir(parents=True,exist_ok=True)
    dump_json(out/'config.json',cfg); dump_json(out/'data_audit.json',report)
    # Snapshot actual split and paths to make evaluation provenance reviewable.
    dump_json(out/'manifest_snapshot.json',rows)
    training=[r for r in rows if r['split']=='train']; val=[r for r in rows if r['split']=='val']
    provenance=dict(train_groups=sorted({r['group'] for r in training}),val_groups=sorted({r['group'] for r in val}),
                    train_pixel_hashes=[r['pixel_sha256'] for r in report if r['split']=='train'],
                    val_pixel_hashes=[r['pixel_sha256'] for r in report if r['split']=='val'])
    engine=Engine(cfg,method)
    optimizer=torch.optim.AdamW([p for p in engine.trainable.parameters() if p.requires_grad],
                               lr=cfg['decoder_lr'] if method=='decoder' else cfg['refiner_lr'],weight_decay=cfg['weight_decay'])
    abl=ABL(label_smoothing=.2) if use_abl else None
    rng=np.random.default_rng(cfg['seed']); history=[]; best=-1.; stale=0
    for epoch in range(cfg['epochs']):
        engine.trainable.train(); order=rng.permutation(len(training)); losses=[]; start=time.perf_counter()
        weight=cfg['abl_weight'] if use_abl and epoch>=cfg['abl_warmup_epochs'] else 0.
        for ri in order:
            r=training[ri]; image=load_image(r['image'],cfg['preprocessing']); gt=load_mask(r['mask'],cfg)
            valid=gt!=cfg['ignore_label']; encoded=engine.encode(image)
            items=targets(gt,cfg)
            if not items: raise ValueError(f'No targets in training image {r["image_id"]}')
            samples=[]
            for _,region in items:
                for _ in range(cfg['prompts_per_region']):
                    kind=rng.choice(['point','point_negative','box'],p=cfg['prompt_probabilities'])
                    samples.append((region,sample_prompt(region,rng,kind,valid=valid)))
            # Teach rejection for grid points on labelled background. Positive point describes
            # a query; in the task-specific setting there is no target region at that location.
            if cfg.get('background_samples_per_image',0):
                yy,xx=np.where((gt==cfg['background_label'])&valid)
                for _ in range(cfg['background_samples_per_image'] if len(xx) else 0):
                    k=rng.integers(len(xx)); samples.append((np.zeros_like(valid),{'points':[[float(xx[k]),float(yy[k])]],'labels':[1]}))
            rng.shuffle(samples)
            for region,prompt in samples:
                optimizer.zero_grad(set_to_none=True)
                logits,_=engine.predict_logits(image,encoded,prompt,train=True)
                z,t,v=target_tensors(logits,region,valid,cfg)
                loss,parts=segmentation_loss(z,t,v,abl,weight)
                if not torch.isfinite(loss): raise FloatingPointError(f'Nonfinite loss: {r["image_id"]}')
                loss.backward(); torch.nn.utils.clip_grad_norm_(engine.trainable.parameters(),cfg['grad_clip'])
                optimizer.step(); losses.append(parts)
        value,details=validate(engine,val,cfg)
        row=dict(epoch=epoch+1,val_center_prompt_dice=value,abl_weight=weight,seconds=time.perf_counter()-start,
                 **{k:float(np.mean([p[k] for p in losses])) for k in losses[0]})
        history.append(row);dump_json(out/'history.json',history)
        # Do not select an ABL checkpoint from before ABL has actually been enabled.
        eligible=not use_abl or epoch>=cfg['abl_warmup_epochs']
        if eligible and value>best:
            best=value; stale=0
            engine.save(out/'best.pt',dict(**provenance,experiment=name,epoch=epoch+1,val_center_prompt_dice=value,
                abl_enabled=use_abl,selection_protocol='GT-derived center point on validation only'))
            dump_json(out/'best_validation.json',details)
        elif eligible: stale+=1
        print(f'{name} epoch {epoch+1}/{cfg["epochs"]}: loss={row["total"]:.4f}, val center Dice={value:.4f}, ABL weight={weight:g}',flush=True)
        if eligible and stale>=cfg['patience']: break
    if not (out/'best.pt').exists(): raise ValueError('No eligible checkpoint: epochs must exceed abl_warmup_epochs')
    engine.save(out/'last.pt',dict(**provenance,experiment=name,epoch=epoch+1,abl_enabled=use_abl))
    del engine,optimizer;gc.collect()
    if torch.cuda.is_available():torch.cuda.empty_cache()
    return str(out/'best.pt')


def train_all(cfg,names=None):
    return {name:train_experiment(cfg,name) for name in (names or list(EXPERIMENTS))}
