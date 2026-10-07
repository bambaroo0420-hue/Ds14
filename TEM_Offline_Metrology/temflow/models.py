import os, sys
from pathlib import Path
from contextlib import nullcontext
import numpy as np
from .core import bounds, validate_prompt, iou


class Models:
    def __init__(self, root, device='cuda'):
        import torch
        root=Path(root).resolve();self.root=root;self.device=device;self.torch=torch
        if device=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable: select the company GPU kernel, or explicitly use device="cpu" for diagnostics')
        os.environ['XFORMERS_DISABLED']='1'
        sys.path.insert(0,str(root/'vendor'))
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        self.sam=SAM2ImagePredictor(build_sam2('configs/sam2.1/sam2.1_hiera_l.yaml',str(root/'weights/sam2.1_hiera_large.pt'),device=device,apply_postprocessing=False))
        self.dino=None
        self.adapted=False
        self.dtype=torch.bfloat16 if device=='cuda' and torch.cuda.is_bf16_supported() else torch.float16

    def amp(self): return self.torch.autocast('cuda',dtype=self.dtype) if self.device=='cuda' else nullcontext()

    def load_layer_decoder(self,path):
        from .core import digest
        checkpoint=self.torch.load(path,map_location='cpu',weights_only=True)
        metadata=checkpoint.get('metadata',{})
        if metadata.get('base_sha256')!=digest(self.root/'weights/sam2.1_hiera_large.pt'):
            raise ValueError('Decoder base checkpoint hash mismatch; experimental partial weights are not a company-trained checkpoint')
        state=dict(self.sam.model.named_parameters())
        for name,value in checkpoint['parameters'].items():
            if name not in state or state[name].shape!=value.shape:raise ValueError('Incompatible decoder parameter '+name)
        with self.torch.no_grad():
            for name,value in checkpoint['parameters'].items():state[name].copy_(value.to(state[name].device))
        self.sam.model.sam_mask_decoder.dynamic_multimask_via_stability=False
        self.adapted=True
        return metadata

    def load_dino(self):
        if self.dino is not None:return
        torch=self.torch
        repo=next((self.root/'vendor').glob('dinov2-*'))
        # pretrained=False is essential: torch.hub must never fetch weights at inference time.
        self.dino=torch.hub.load(str(repo),'dinov2_vitb14_reg',source='local',pretrained=False).to(self.device).eval()
        self.dino.load_state_dict(torch.load(self.root/'weights/dinov2_vitb14_reg4_pretrain.pth',map_location='cpu',weights_only=True),strict=True)

    def segment(self,image,prompt,pad=24,template=None,choose=None,input_bounds=None):
        torch=self.torch;h,w=image.shape[:2]
        # Crop keeps surrounding context; the box is passed separately, never a hard mask cut.
        p=np.asarray(prompt['points'],float).reshape(-1,2);lab=np.asarray(prompt['labels'],int)
        bx=prompt.get('box')
        if input_bounds is not None:
            x0,y0,x1,y1=map(int,input_bounds)
            if not (0<=x0<x1<=w and 0<=y0<y1<=h):raise ValueError('Invalid fixed input crop')
            if len(p) and not ((p[:,0]>=x0)&(p[:,0]<x1)&(p[:,1]>=y0)&(p[:,1]<y1)).all():
                raise ValueError('Point outside fixed device crop; move point or increase device padding')
            if bx is not None and not (x0<=bx[0]<bx[2]<x1 and y0<=bx[1]<bx[3]<y1):
                raise ValueError('Box outside fixed device crop; move box or increase device padding')
        elif bx is None:
            x0,y0,x1,y1=0,0,w,h
        else:
            x0=max(0,int(np.floor(bx[0]))-pad);y0=max(0,int(np.floor(bx[1]))-pad)
            x1=min(w,int(np.ceil(bx[2]))+pad+1);y1=min(h,int(np.ceil(bx[3]))+pad+1)
            if len(p):
                x0=max(0,min(x0,int(np.floor(p[:,0].min()))-4));y0=max(0,min(y0,int(np.floor(p[:,1].min()))-4))
                x1=min(w,max(x1,int(np.ceil(p[:,0].max()))+5));y1=min(h,max(y1,int(np.ceil(p[:,1].max()))+5))
        if x1<=x0 or y1<=y0:raise ValueError('Prompt crop outside image')
        keep=(p[:,0]>=x0)&(p[:,0]<x1)&(p[:,1]>=y0)&(p[:,1]<y1)
        p=p[keep]-[x0,y0];lab=lab[keep]
        box=None if bx is None else np.clip(np.asarray(bx)-[x0,y0,x0,y0],[0,0,0,0],[x1-x0-1,y1-y0-1]*2)
        if len(p)==0 and box is None:raise ValueError('No usable prompt after clipping')
        with torch.inference_mode(),self.amp():
            self.sam.set_image(image[y0:y1,x0:x1])
            masks,scores,_=self.sam.predict(point_coords=p.astype('float32') if len(p) else None,
                   point_labels=lab if len(p) else None,box=box,multimask_output=not self.adapted)
        masks=np.asarray(masks)>0
        utilities=[]
        for m,s in zip(masks,scores):
            pi=np.rint(p).astype(int)
            if len(pi): pi=np.clip(pi,[0,0],[m.shape[1]-1,m.shape[0]-1])
            coverage=float(np.mean(m[pi[lab==1,1],pi[lab==1,0]])) if (lab==1).any() else 0
            leakage=float(np.mean(m[pi[lab==0,1],pi[lab==0,0]])) if (lab==0).any() else 0
            agreement=iou(m,template[y0:y1,x0:x1]) if template is not None else 0
            utilities.append(float(s)+.6*coverage-.8*leakage+agreement)
        selected=int(np.argmax(utilities)) if choose is None else int(choose)
        if not 0<=selected<len(masks):raise ValueError('Candidate index must be 0, 1, or 2')
        full=np.zeros((h,w),bool);full[y0:y1,x0:x1]=masks[selected]
        meta=dict(crop=[x0,y0,x1,y1],prompt=prompt,local_points=p.tolist(),local_labels=lab.tolist(),
                  local_box=None if box is None else box.tolist(),scores=[float(s) for s in scores],
                  utilities=utilities,selected=selected,clipped=bool(not keep.all()))
        return full,meta,masks

    def features(self,image,max_side=840):
        import torch.nn.functional as F
        self.load_dino();torch=self.torch;h,w=image.shape[:2]
        s=max_side/max(h,w);hh=max(14,round(h*s/14)*14);ww=max(14,round(w*s/14)*14)
        a=torch.from_numpy(image.copy()).permute(2,0,1)[None].to(self.device).float()/255
        a=F.interpolate(a,(hh,ww),mode='bicubic',align_corners=False,antialias=True).clamp(0,1)
        a=(a-a.new_tensor([.485,.456,.406])[None,:,None,None])/a.new_tensor([.229,.224,.225])[None,:,None,None]
        with torch.inference_mode(),self.amp():f=self.dino.forward_features(a)['x_norm_patchtokens']
        if not torch.isfinite(f).all():raise RuntimeError('Nonfinite DINO features; use float32 or smaller image')
        return F.normalize(f.float(),dim=-1).reshape(1,hh//14,ww//14,-1).permute(0,3,1,2)

    def search(self,image,reference_mask,roi=None,max_side=840,threshold=.45,nms_px=None,limit=30):
        import torch.nn.functional as F
        from scipy.ndimage import maximum_filter
        torch=self.torch;h,w=image.shape[:2];f=self.features(image,max_side);gh,gw=f.shape[-2:]
        rx0,ry0,rx1,ry1=bounds(reference_mask)
        cx=int(np.clip(round((rx0+rx1)/2/w*gw-.5),0,gw-1));cy=int(np.clip(round((ry0+ry1)/2/h*gh-.5),0,gh-1))
        hx=max(1,int(np.ceil((rx1-rx0)/w*gw/2)));hy=max(1,int(np.ceil((ry1-ry0)/h*gh/2)))
        if cx-hx<0 or cy-hy<0 or cx+hx>=gw or cy+hy>=gh:raise ValueError('Choose a complete reference away from the image edge')
        weights=F.interpolate(torch.as_tensor(reference_mask.astype('float32'),device=self.device)[None,None],(gh,gw),mode='area')
        template=f[:,:,cy-hy:cy+hy+1,cx-hx:cx+hx+1];wt=weights[:,:,cy-hy:cy+hy+1,cx-hx:cx+hx+1]
        score=F.conv2d(f,template*wt,padding=(hy,hx))/wt.sum().clamp(min=1e-6)
        heat=F.interpolate(score,(h,w),mode='bilinear',align_corners=False)[0,0].cpu().numpy()
        valid=np.zeros((h,w),bool)
        a,b,c,d=[0,0,w,h] if roi is None else map(int,roi);valid[b:d,a:c]=True
        nms_px=int(nms_px or max(rx1-rx0,ry1-ry0)*.75)
        ys,xs=np.where((heat==maximum_filter(heat,size=max(3,nms_px//2)))&(heat>=threshold)&valid)
        anchor=np.array([(cx+.5)*w/gw,(cy+.5)*h/gh]);candidates=[]
        for k in np.argsort(heat[ys,xs])[::-1]:
            x,y=int(xs[k]),int(ys[k])
            if any(np.linalg.norm(np.array([x,y])-r['center'])<nms_px for r in candidates):continue
            candidates.append(dict(center=[x,y],offset=(np.array([x,y])-anchor).tolist(),dino_score=float(heat[y,x])))
            if len(candidates)>=limit:break
        return candidates,heat,dict(grid=[gw,gh],reference_anchor=anchor.tolist(),max_side=max_side,threshold=threshold)

    def crop_similarity(self,image,reference_mask,offset):
        import torch.nn.functional as F
        from PIL import Image
        from .core import shifted_mask
        x0,y0,x1,y1=bounds(reference_mask,pad=8);dx,dy=np.rint(offset).astype(int)
        if x0+dx<0 or y0+dy<0 or x1+dx>image.shape[1] or y1+dy>image.shape[0]:return None
        ref=np.array(Image.fromarray(image[y0:y1,x0:x1]).resize((224,224)))
        cur=np.array(Image.fromarray(image[y0+dy:y1+dy,x0+dx:x1+dx]).resize((224,224)))
        a=self.features(ref,224);b=self.features(cur,224)
        wt=F.interpolate(self.torch.tensor(reference_mask[y0:y1,x0:x1].astype('float32'),device=self.device)[None,None],a.shape[-2:],mode='area')
        return float(((a*b).sum(1,keepdim=True)*wt).sum()/wt.sum().clamp(min=1e-6))
