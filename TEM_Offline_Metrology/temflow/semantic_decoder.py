"""Multi-class GT -> prompted binary masks; custom SAM2.1 decoder-only loop.

Not Meta's official Trainer. Uses its model modules with BCE/Dice/quality losses.
"""
import json, random, time
from pathlib import Path
from collections import OrderedDict
import numpy as np
from PIL import Image
from scipy.ndimage import label, distance_transform_edt
from .core import read_image, digest


def make_samples(root, rows, classes, ignore=255, pad=64, min_area=8):
    samples=[]
    for r in rows:
        a=np.asarray(Image.open(Path(root)/r['gt']))
        if a.ndim!=2: raise ValueError('Normalized integer GT required')
        for cls in classes:
            cc,n=label(a==cls)
            for k in range(1,n+1):
                yy,xx=np.where(cc==k)
                if len(xx)<min_area: continue
                x0=max(0,int(xx.min())-pad); x1=min(a.shape[1],int(xx.max())+pad+1)
                y0=max(0,int(yy.min())-pad); y1=min(a.shape[0],int(yy.max())+pad+1)
                target=cc[y0:y1,x0:x1]==k
                if target.shape[0]<2 or target.shape[1]<2: continue
                samples.append(dict(row=r,cls=int(cls),crop=[x0,y0,x1,y1],target=target,
                                    valid=a[y0:y1,x0:x1]!=ignore))
    return samples


def prompt(sample, rng, mode='box_points', jitter=False):
    t=sample['target']; valid=sample['valid']; h,w=t.shape
    yy,xx=np.where(t); b=np.array([xx.min(),yy.min(),xx.max(),yy.max()],float)
    if jitter: b+=rng.integers(-2,3,4)
    b=np.clip(b,[0,0,0,0],[w-1,h-1,w-1,h-1])
    b[2]=min(w-1,max(b[0]+1,b[2]));b[0]=min(b[0],b[2]-1)
    b[3]=min(h-1,max(b[1]+1,b[3]));b[1]=min(b[1],b[3]-1)
    pts=[]; labs=[]
    if mode!='box':
        if jitter:
            ids=rng.choice(len(xx),size=int(rng.choice([1,3])),replace=True)
            pts=[[float(xx[i]),float(yy[i])] for i in ids]
        else:
            y,x=np.unravel_index(distance_transform_edt(t).argmax(),t.shape)
            pts=[[float(x),float(y)]]
        labs=[1]*len(pts)
        # Deterministic negatives during validation; sample only valid non-target pixels.
        near=(~t)&valid&(distance_transform_edt(~t)<=12)
        ny,nx=np.where(near)
        if len(nx):
            ids=rng.choice(len(nx),size=min(3,len(nx)),replace=False) if jitter else np.linspace(0,len(nx)-1,min(3,len(nx)),dtype=int)
            pts.extend([[float(nx[i]),float(ny[i])] for i in ids]);labs.extend([0]*len(ids))
    return np.array(pts,float).reshape(-1,2),np.array(labs,int),None if mode=='points' else b


def train_semantic(models,root,rows,classes,out,steps=200,lr=1e-5,pad=64,
                   min_area=8,ignore=255,seed=42,validate_every=20,
                   modes=('box_points','points','box'),quality_weight=.1):
    import torch
    import torch.nn.functional as F
    root=Path(root);out=Path(out)
    if (out/'metadata.json').exists(): raise ValueError('Use a new run output directory')
    classes=sorted(set(map(int,classes)))
    if not classes or 0 in classes or ignore in classes: raise ValueError('Choose foreground IDs')
    if steps<0 or validate_every<1 or lr<=0: raise ValueError('Invalid training settings')
    if not modes or set(modes)-{'box_points','points','box'}: raise ValueError('Invalid prompt modes')
    splits={s:{r['group'] for r in rows if r['split']==s} for s in ('train','val','test')}
    if any(splits[a]&splits[b] for a,b in [('train','val'),('train','test'),('val','test')]):
        raise ValueError('Group leakage across splits')
    hashes={}
    for r in rows:
        if r['split'] not in splits: raise ValueError('Unknown split')
        if digest(root/r['image'])!=r['image_sha256'] or digest(root/r['gt'])!=r['gt_sha256']:
            raise ValueError('Data changed after preparation')
        ph=r.get('pixel_sha256',r['image_sha256'])
        if ph in hashes and hashes[ph]!=r['split']: raise ValueError('Duplicate image across splits')
        hashes[ph]=r['split']
    sets={s:make_samples(root,[r for r in rows if r['split']==s],classes,ignore,pad,min_area) for s in splits}
    for s in ('train','val'):
        missing=set(classes)-{v['cls'] for v in sets[s]}
        if missing: raise ValueError(f'{s} missing classes: {missing}')
    out.mkdir(parents=True,exist_ok=True)
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);rng=np.random.default_rng(seed)
    model=models.sam.model;model.eval();device=models.device
    for p in model.parameters():p.requires_grad_(False)
    # Single-mask path plus quality head. Other output MLPs/object head unused.
    for n,p in model.sam_mask_decoder.named_parameters():
        if n.startswith('pred_obj_score_head'):continue
        if n.startswith('output_hypernetworks_mlps.') and not n.startswith('output_hypernetworks_mlps.0.'):continue
        p.requires_grad_(True)
    named={n:p for n,p in model.named_parameters() if p.requires_grad}
    assert named and all(n.startswith('sam_mask_decoder.') for n in named)
    initial={n:p.detach().cpu().clone() for n,p in named.items()}
    dynamic=model.sam_mask_decoder.dynamic_multimask_via_stability
    model.sam_mask_decoder.dynamic_multimask_via_stability=False
    opt=torch.optim.AdamW(named.values(),lr=lr,weight_decay=.01)
    cache=OrderedDict(); timing=dict(feature_seconds=0.,train_seconds=0.,eval_seconds=0.)
    def sync():
        if str(device).startswith('cuda'):torch.cuda.synchronize()
    def forward(s,mode,jitter):
        r=s['row'];x0,y0,x1,y1=s['crop'];key=(r['id'],x0,y0,x1,y1)
        if key not in cache:
            sync();t0=time.perf_counter()
            with torch.no_grad(),models.amp():models.sam.set_image(read_image(root/r['image'])[y0:y1,x0:x1])
            cache[key]={k:[v.detach().float().cpu() for v in a] if isinstance(a,list) else a.detach().float().cpu() for k,a in models.sam._features.items()}
            if len(cache)>4:cache.popitem(last=False)
            sync();timing['feature_seconds']+=time.perf_counter()-t0
        cache.move_to_end(key)
        f={k:[v.to(device) for v in a] if isinstance(a,list) else a.to(device) for k,a in cache[key].items()}
        pts,labs,b=prompt(s,rng,mode,jitter);h,w=s['target'].shape
        if b is not None:pts=np.concatenate([b.reshape(2,2),pts]);labs=np.r_[2,3,labs]
        coords=pts/[w,h]*model.image_size
        with torch.no_grad():
            sparse,dense=model.sam_prompt_encoder(points=(torch.tensor(coords,dtype=torch.float32,device=device)[None],torch.tensor(labs,dtype=torch.int,device=device)[None]),boxes=None,masks=None)
        low,quality,_,_=model.sam_mask_decoder(image_embeddings=f['image_embed'],image_pe=model.sam_prompt_encoder.get_dense_pe(),sparse_prompt_embeddings=sparse,dense_prompt_embeddings=dense,multimask_output=False,repeat_image=False,high_res_features=f['high_res_feats'])
        log=F.interpolate(low,size=(h,w),mode='bilinear',align_corners=False)
        target=torch.tensor(s['target'],dtype=torch.float32,device=device)[None,None]
        valid=torch.tensor(s['valid'],dtype=torch.float32,device=device)[None,None]
        return log,quality,target,valid
    def iou(log,t,v):
        m=log>0;truth=t>0;ok=v>0
        return ((m&truth)&ok).sum().float()/((m|truth)&ok).sum().clamp(min=1)
    def evaluate(samples,save=None):
        sync();ts=time.perf_counter();items=[]
        with torch.no_grad():
            for i,s in enumerate(samples):
                for mode in modes:
                    log,q,t,v=forward(s,mode,False)
                    items.append(dict(id=s['row']['id'],class_id=s['cls'],mode=mode,iou=float(iou(log,t,v))))
                    if save and mode==modes[0]:
                        np.savez_compressed(out/f'{save}_{i:04d}.npz',mask=(log[0,0]>0).cpu().numpy(),target=s['target'],valid=s['valid'],crop=s['crop'],image=s['row']['image'],class_id=s['cls'])
        # Equal weight per class, then per original image, then per prompt/component.
        scores={}
        for cls in classes:
            ids=sorted({r['id'] for r in items if r['class_id']==cls})
            if ids:scores[str(cls)]=float(np.mean([np.mean([r['iou'] for r in items if r['class_id']==cls and r['id']==id]) for id in ids]))
        sync();timing['eval_seconds']+=time.perf_counter()-ts
        return dict(macro_iou=float(np.mean(list(scores.values()))) if scores else None,per_class=scores,items=items)
    history=[];start=time.perf_counter();beststate=initial;beststep=0
    try:
        baseline=evaluate(sets['val']);best=baseline['macro_iou']
        test_before=evaluate(sets['test'],'test_before') if sets['test'] else None
        history.append(dict(step=0,val=baseline))
        pools={c:[s for s in sets['train'] if s['cls']==c] for c in classes}
        print('Trainable parameters:',sum(p.numel() for p in named.values()),flush=True)
        for step in range(1,steps+1):
            sync();ts=time.perf_counter()
            s=random.choice(pools[random.choice(classes)])
            log,q,t,v=forward(s,random.choice(modes),True);prob=log.sigmoid()
            bce=(F.binary_cross_entropy_with_logits(log,t,reduction='none')*v).sum()/v.sum().clamp(min=1)
            dice=1-(2*(prob*t*v).sum()+1)/((prob*v).sum()+(t*v).sum()+1)
            quality=F.mse_loss(q.reshape(-1),iou(log.detach(),t,v).detach().expand(q.numel()))
            loss=bce+dice+quality_weight*quality
            if not torch.isfinite(loss):raise RuntimeError('Non-finite loss')
            opt.zero_grad(set_to_none=True);loss.backward()
            assert all(p.grad is None for n,p in model.named_parameters() if n not in named)
            torch.nn.utils.clip_grad_norm_(list(named.values()),1.);opt.step()
            sync();timing['train_seconds']+=time.perf_counter()-ts
            if step%validate_every==0 or step==steps:
                ev=evaluate(sets['val']);history.append(dict(step=step,loss=float(loss.detach()),val=ev))
                print(step,'loss',float(loss.detach()),'val IoU',ev['macro_iou'],flush=True)
                if ev['macro_iou']>best:
                    best=ev['macro_iou'];beststep=step;beststate={n:p.detach().cpu().clone() for n,p in named.items()}
                (out/'history.json').write_text(json.dumps(history,indent=2))
        with torch.no_grad():
            for n,p in named.items():p.copy_(beststate[n].to(device))
        val_after=evaluate(sets['val'],'val_after')
        test_after=evaluate(sets['test'],'test_after') if sets['test'] else None
        metadata=dict(base='sam2.1_hiera_large',base_sha256=digest(models.root/'weights/sam2.1_hiera_large.pt'),class_ids=classes,
            class_id='multi_class_prompted_binary',context_pad_px=pad,steps=steps,best_step=beststep,lr=lr,seed=seed,
            ignore=ignore,min_area=min_area,prompt_modes=list(modes),quality_weight=quality_weight,
            trained='decoder single-mask path and IoU head; other modules frozen',trainable_names=list(named),
            trainable_parameters=sum(p.numel() for p in named.values()),baseline_val=baseline,after_val=val_after,
            test_before=test_before,test_after=test_after,data_manifest=rows,timing=timing,
            elapsed_seconds=time.perf_counter()-start,timing_note='train/eval include feature time; do not sum feature time again',
            torch_version=str(torch.__version__),device=str(device),gpu=torch.cuda.get_device_name() if str(device).startswith('cuda') else None,
            implementation='custom loop using official SAM modules, not official Trainer',
            limitation='No independent test evaluation' if not sets['test'] else 'Test split must remain independent; fixed GT-derived prompts')
        (out/'history.json').write_text(json.dumps(history,indent=2),encoding='utf8')
        torch.save(dict(parameters=beststate,metadata=metadata),out/'best_decoder.pt')
        (out/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
        return metadata
    finally:
        with torch.no_grad():
            for n,p in named.items():p.copy_(initial[n].to(device))
        for p in model.parameters():p.requires_grad_(False)
        model.sam_mask_decoder.dynamic_multimask_via_stability=dynamic
