from contextlib import nullcontext
from pathlib import Path
import hashlib, json, sys
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from .data import sha256

VENDOR = Path(__file__).resolve().parents[1]/'vendor'/'segment-anything'
# Use the bundled official SAM source to avoid git/pip downloads in the company network.
if str(VENDOR) not in sys.path: sys.path.insert(0,str(VENDOR))
from segment_anything import sam_model_registry
from segment_anything.utils.transforms import ResizeLongestSide


def safe_load(path, map_location='cpu'):
    return torch.load(path,map_location=map_location,weights_only=True)


class Block(nn.Sequential):
    def __init__(self, a,b):
        super().__init__(nn.Conv2d(a,b,3,padding=1),nn.GroupNorm(4,b),nn.GELU(),
                         nn.Conv2d(b,b,3,padding=1),nn.GroupNorm(4,b),nn.GELU())


class ResidualRefiner(nn.Module):
    """4 channels = RGB [0,1] plus frozen SAM foreground probability.
    Predict a residual in logit space. Zero head initializes to the frozen SAM result.
    """
    def __init__(self, width=16):
        super().__init__()
        self.e1=Block(4,width); self.e2=Block(width,width*2); self.mid=Block(width*2,width*4)
        self.d2=Block(width*6,width*2); self.d1=Block(width*3,width)
        self.head=nn.Conv2d(width,1,1)
        nn.init.zeros_(self.head.weight); nn.init.zeros_(self.head.bias)

    def forward(self, image, sam_logits):
        e1=self.e1(torch.cat([image,torch.sigmoid(sam_logits)],1))
        e2=self.e2(F.avg_pool2d(e1,2)); b=self.mid(F.avg_pool2d(e2,2))
        d2=self.d2(torch.cat([F.interpolate(b,size=e2.shape[-2:],mode='bilinear',align_corners=False),e2],1))
        d1=self.d1(torch.cat([F.interpolate(d2,size=e1.shape[-2:],mode='bilinear',align_corners=False),e1],1))
        return sam_logits+self.head(d1)


class Engine:
    def __init__(self,cfg,method='baseline'):
        self.cfg=dict(cfg); self.method=method; self.device=torch.device(cfg['device'])
        if self.device.type=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA not available: install matching CUDA PyTorch/kernel.')
        self.base_hash=sha256(cfg['sam_checkpoint'])
        self.sam=sam_model_registry[cfg['model_type']](checkpoint=cfg['sam_checkpoint']).to(self.device).eval()
        for p in self.sam.parameters(): p.requires_grad_(False)
        self.refiner=None
        if method=='decoder':
            for p in self.sam.mask_decoder.parameters(): p.requires_grad_(True)
            # No IoU-head loss in this experiment; do not imply its score was calibrated.
            for p in self.sam.mask_decoder.iou_prediction_head.parameters(): p.requires_grad_(False)
        elif method=='refiner':
            self.refiner=ResidualRefiner(cfg['refiner_width']).to(self.device)
        elif method!='baseline': raise ValueError(method)
        self.transform=ResizeLongestSide(self.sam.image_encoder.img_size)
        self.cache_dir=Path(cfg['cache_dir']); self.cache_dir.mkdir(parents=True,exist_ok=True)

    @property
    def trainable(self):
        return self.refiner if self.method=='refiner' else self.sam.mask_decoder

    def encode(self,image):
        image=np.ascontiguousarray(image)
        meta=dict(base=self.base_hash, model=self.cfg['model_type'],prep=self.cfg['preprocessing'],shape=list(image.shape))
        key=hashlib.sha256(image.tobytes()+json.dumps(meta,sort_keys=True).encode()).hexdigest()
        path=self.cache_dir/f'{key}.pt'
        if path.exists():
            d=safe_load(path); return dict(features=d['features'].to(self.device).float(),input_size=tuple(d['input_size']),original_size=tuple(d['original_size']))
        resized=self.transform.apply_image(image)
        t=torch.as_tensor(resized,device=self.device).permute(2,0,1)[None]
        amp=self.device.type=='cuda' and self.cfg.get('encoder_amp',True)
        ctx=torch.autocast(device_type='cuda',dtype=torch.float16) if amp else nullcontext()
        with torch.no_grad(),ctx: feat=self.sam.image_encoder(self.sam.preprocess(t))
        d=dict(features=feat.float().cpu(),input_size=list(resized.shape[:2]),original_size=list(image.shape[:2]))
        tmp=path.with_suffix('.tmp'); torch.save(d,tmp); tmp.replace(path)
        return dict(features=feat.float(),input_size=tuple(d['input_size']),original_size=tuple(d['original_size']))

    def decode_base(self,encoded,prompt,train=False):
        points=boxes=None
        size=encoded['original_size']
        if prompt.get('points') is not None:
            xy=np.asarray(prompt['points'],dtype=np.float32)
            xy=self.transform.apply_coords(xy,size)
            points=(torch.as_tensor(xy,device=self.device)[None],torch.as_tensor(prompt['labels'],device=self.device)[None])
        if prompt.get('box') is not None:
            box=self.transform.apply_boxes(np.asarray(prompt['box'],dtype=np.float32)[None],size)
            boxes=torch.as_tensor(box,device=self.device)
        if points is None and boxes is None: raise ValueError('A point or box prompt is required')
        with torch.no_grad(): sparse,dense=self.sam.prompt_encoder(points=points,boxes=boxes,masks=None)
        ctx=nullcontext() if train and self.method=='decoder' else torch.no_grad()
        with ctx:
            low,score=self.sam.mask_decoder(image_embeddings=encoded['features'],
                image_pe=self.sam.prompt_encoder.get_dense_pe(),sparse_prompt_embeddings=sparse,
                dense_prompt_embeddings=dense,multimask_output=False)
            full=self.sam.postprocess_masks(low,encoded['input_size'],size)
        return full,score

    def predict_logits(self,image,encoded,prompt,train=False):
        full,score=self.decode_base(encoded,prompt,train)
        if self.method=='refiner':
            h,w=image.shape[:2]; scale=min(1.,self.cfg['refine_side']/max(h,w))
            size=(max(8,round(h*scale)),max(8,round(w*scale)))
            im=torch.as_tensor(image.copy(),device=self.device).permute(2,0,1)[None].float()/255
            im=F.interpolate(im,size=size,mode='bilinear',align_corners=False)
            low=F.interpolate(full.detach(),size=size,mode='bilinear',align_corners=False)
            ctx=nullcontext() if train else torch.no_grad()
            with ctx:
                full=F.interpolate(self.refiner(im,low),size=(h,w),mode='bilinear',align_corners=False)
        return full,score

    def save(self,path,extra=None):
        state={k:v.detach().cpu() for k,v in self.trainable.state_dict().items()}
        torch.save(dict(schema=1,method=self.method,base_sha256=self.base_hash,config=self.cfg,
                        state=state,extra=extra or {}),path)

    def load_weights(self,path):
        pack=safe_load(path)
        if pack['schema']!=1 or pack['method']!=self.method: raise ValueError('Checkpoint architecture mismatch')
        if pack['base_sha256']!=self.base_hash: raise ValueError('Base SAM checkpoint hash mismatch')
        self.trainable.load_state_dict(pack['state'],strict=True)
        self.trainable.eval()
        return pack


class Predictor:
    """Web UI adapter. Constructor once per model; set_image once per image.
    Coordinates are native image xy, boxes xyxy. Returns class-agnostic masks.
    """
    def __init__(self,base_checkpoint,adaptation_checkpoint,device='cuda',cache_dir='cache/ui'):
        pack=safe_load(adaptation_checkpoint)
        cfg=dict(pack['config']); cfg.update(sam_checkpoint=str(base_checkpoint),device=device,cache_dir=str(cache_dir))
        self.engine=Engine(cfg,pack['method']); self.engine.load_weights(adaptation_checkpoint)
        self.image=self.encoded=None

    def set_image(self,rgb_uint8):
        if rgb_uint8.dtype!=np.uint8 or rgb_uint8.ndim!=3 or rgb_uint8.shape[-1]!=3:
            raise ValueError('Use temlab.data.load_image(path, saved preprocessing); RGB uint8 required')
        self.image=np.ascontiguousarray(rgb_uint8); self.encoded=self.engine.encode(self.image)

    def predict(self,points=None,labels=None,box=None):
        if self.image is None: raise RuntimeError('Call set_image first')
        prompt={}
        if points is not None: prompt.update(points=np.asarray(points).tolist(),labels=list(labels if labels is not None else np.ones(len(points),dtype=int)))
        if box is not None: prompt['box']=list(box)
        with torch.no_grad(): logits,_=self.engine.predict_logits(self.image,self.encoded,prompt)
        p=logits.sigmoid()[0,0].cpu().numpy()
        return dict(probability=p,mask=p>=self.engine.cfg['mask_threshold'])
