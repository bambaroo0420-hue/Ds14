"""SAM models and interchangeable post-SAM refiners. Heavy imports are lazy."""
from pathlib import Path
import hashlib
import numpy as np

class ModelService:
    def __init__(self):
        self.model=None; self.predictor=None; self.refiner=None; self.info=None; self.image_key=None

    def load(self, checkpoint, variant='vit_h', device='auto', decoder_path=None, refiner_path=None):
        import torch
        from segment_anything import sam_model_registry, SamPredictor
        if variant not in ('vit_h','vit_l','vit_b'): raise ValueError('SAM variant는 vit_h/l/b 중 하나입니다.')
        checkpoint=Path(checkpoint).expanduser().resolve()
        if not checkpoint.is_file(): raise ValueError('SAM 체크포인트 경로를 확인하세요.')
        device = ('cuda' if torch.cuda.is_available() else 'cpu') if device=='auto' else device
        if device=='cuda' and not torch.cuda.is_available(): raise ValueError('CUDA를 사용할 수 없습니다.')
        model=sam_model_registry[variant](checkpoint=str(checkpoint))
        if decoder_path:
            state=torch.load(decoder_path,map_location='cpu',weights_only=True)
            if isinstance(state,dict) and 'state_dict' in state: state=state['state_dict']
            model.mask_decoder.load_state_dict(state,strict=True)
        model=model.to(device).eval()
        refiner=None
        if refiner_path:
            # Safe, explicit TorchScript contract: forward(image[N,3,H,W], mask[N,1,H,W])-> logits[N,1,H,W].
            refiner=torch.jit.load(str(refiner_path),map_location=device).eval()
        self.model=model;self.predictor=SamPredictor(model);self.refiner=refiner;self.image_key=None
        self.info=dict(variant=variant,device=device,checkpoint=str(checkpoint),decoder_path=decoder_path,refiner_path=refiner_path)
        return self.info

    def _set_image(self,image):
        digest=hashlib.sha256(image.tobytes()).hexdigest()
        if digest!=self.image_key:
            self.predictor.set_image(image);self.image_key=digest

    def _refine(self,image,mask):
        if self.refiner is None:return mask
        import torch
        from PIL import Image
        h,w=mask.shape
        rgb=np.asarray(Image.fromarray(image).resize((256,256))).astype('float32')/255
        m=np.asarray(Image.fromarray(mask.astype('uint8')).resize((256,256),resample=Image.Resampling.NEAREST)).astype('float32')
        x=torch.from_numpy(rgb.transpose(2,0,1)[None]).to(self.info['device'])
        y=torch.from_numpy(m[None,None]).to(self.info['device'])
        with torch.inference_mode(): logits=self.refiner(x,y)
        if logits.shape!=(1,1,256,256):raise ValueError('refiner 출력은 [1,1,256,256]이어야 합니다.')
        out=(logits[0,0].float().cpu().numpy()>0).astype('uint8')
        return np.asarray(Image.fromarray(out).resize((w,h),resample=Image.Resampling.NEAREST))>0

    def automatic(self,image,grid=16,pred_iou=.90,stability=.92,nms=.8,exclude=None):
        if self.model is None:raise ValueError('먼저 SAM 모델을 로드하세요.')
        from segment_anything import SamAutomaticMaskGenerator
        import torch
        grid=int(grid)
        if not 2<=grid<=32:raise ValueError('grid는 2~32입니다.')
        if exclude is None:exclude=np.zeros(image.shape[:2],bool)
        coords=(np.arange(grid)+.5)/grid
        points=np.array([[x,y] for y in coords for x in coords if not exclude[min(int(y*image.shape[0]),image.shape[0]-1),min(int(x*image.shape[1]),image.shape[1]-1)]],dtype=np.float32)
        if not len(points):return []
        gen=SamAutomaticMaskGenerator(self.model,points_per_side=None,point_grids=[points],points_per_batch=8,crop_n_layers=0,pred_iou_thresh=float(pred_iou),stability_score_thresh=float(stability),box_nms_thresh=float(nms),min_mask_region_area=0)
        with torch.inference_mode(): items=gen.generate(image)
        return [dict(mask=self._refine(image,x['segmentation']),score=float(x['predicted_iou']),stability=float(x['stability_score']),bbox=[int(v) for v in x['bbox']],point=x.get('point_coords')) for x in items]

    def prompt(self,image,points=None,box=None,prior=None):
        if self.model is None:raise ValueError('먼저 SAM 모델을 로드하세요.')
        import torch
        points=points or []
        if not points and box is None:raise ValueError('점 또는 box가 필요합니다.')
        self._set_image(image)
        xy=np.asarray([[p[0],p[1]] for p in points],dtype=np.float32) if points else None
        labels=np.asarray([p[2] for p in points],dtype=np.int32) if points else None
        bbox=np.asarray(box,dtype=np.float32) if box is not None else None
        # A full-resolution edited mask is not a native 256x256 SAM mask_input. Use it only as a saved parent.
        with torch.inference_mode(): masks,scores,_=self.predictor.predict(point_coords=xy,point_labels=labels,box=bbox,multimask_output=True)
        idx=int(np.argmax(scores))
        return dict(mask=self._refine(image,masks[idx]),score=float(scores[idx]))

    def in_roi(self,image,roi,points=None,box=None):
        x0,y0,x1,y1=map(int,roi);h,w=image.shape[:2]
        if not (0<=x0<x1<=w and 0<=y0<y1<=h):raise ValueError('잘못된 ROI')
        crop=image[y0:y1,x0:x1]
        local=[[p[0]-x0,p[1]-y0,p[2]] for p in (points or []) if x0<=p[0]<x1 and y0<=p[1]<y1]
        local_box=[box[0]-x0,box[1]-y0,box[2]-x0,box[3]-y0] if box else None
        item=self.prompt(crop,local,local_box)
        full=np.zeros((h,w),bool);full[y0:y1,x0:x1]=item['mask'];item['mask']=full
        return item
