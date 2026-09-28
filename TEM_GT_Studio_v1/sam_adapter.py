"""Optional local-checkpoint SAM/micro-SAM. Never silently falls back to CV."""
from pathlib import Path
import numpy as np

class SamAdapter:
    def __init__(self): self.predictor=None; self.key=None
    def load(self,backend,checkpoint,model_type='vit_b',device='cpu'):
        if not Path(checkpoint).is_file(): raise ValueError('서버 PC의 체크포인트 파일 경로를 확인하세요.')
        if backend=='micro_sam':
            from micro_sam.util import get_sam_model
            self.predictor=get_sam_model(model_type=model_type,checkpoint_path=checkpoint,device=device)
        else:
            from segment_anything import SamPredictor,sam_model_registry
            model=sam_model_registry[model_type](checkpoint=checkpoint).to(device=device)
            self.predictor=SamPredictor(model)
        self.key=None
    def predict(self,image,points,box=None,crop=False,sigma=0,batch=False):
        if self.predictor is None: raise ValueError('SAM을 먼저 로드하세요. 가중치 없이 polygon/superpixel 기능은 사용 가능합니다.')
        from scipy.ndimage import gaussian_filter
        import torch
        rgb=image.copy(); h,w=rgb.shape[:2]; ox=oy=0
        if crop:
            if not box: raise ValueError('Crop SAM에는 ROI가 필요합니다.')
            x0,y0,x1,y1=map(int,box); rgb=rgb[y0:y1,x0:x1]; ox,oy=x0,y0
        if sigma: rgb=gaussian_filter(rgb.astype(float),(sigma,sigma,0)).clip(0,255).astype('uint8')
        # No image resizing here. Predictor performs its own preprocessing.
        with torch.inference_mode():
            self.predictor.set_image(rgb)
            groups=[[p] for p in points if p[2]==1] if batch else [points]
            if not groups or (not points and box is None): raise ValueError('양성점 또는 ROI가 필요합니다.')
            out=np.zeros((h,w),bool)
            for group in groups:
                xy=np.array([[p[0]-ox,p[1]-oy] for p in group],np.float32) if group else None
                labels=np.array([p[2] for p in group],np.int32) if group else None
                localbox=None if crop or box is None else np.array(box)
                masks,scores,_=self.predictor.predict(point_coords=xy,point_labels=labels,box=localbox,multimask_output=True)
                selected=masks[int(np.argmax(scores))]
                out[oy:oy+rgb.shape[0],ox:ox+rgb.shape[1]]|=selected
        return out
