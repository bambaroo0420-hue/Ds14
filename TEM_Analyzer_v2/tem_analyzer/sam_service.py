"""Official SAM, single-mask trained decoder, and native logit residual refiner."""
from pathlib import Path
import hashlib,sys,json
import numpy as np

VENDOR=Path(__file__).resolve().parents[1]/'adaptation_backend'/'vendor'/'segment-anything'
if str(VENDOR) not in sys.path:sys.path.insert(0,str(VENDOR))

def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def image_hash(image):return hashlib.sha256(str(image.shape).encode()+image.tobytes()).hexdigest()

class ModelService:
    def __init__(self):self.model=None;self.predictor=None;self.refiner=None;self.info=None;self.image_key=None;self.refiner_kind=None;self.cfg={}
    def load(self,checkpoint,variant='vit_h',device='auto',decoder_path=None,refiner_path=None,adaptation_path=None):
        import torch
        from segment_anything import sam_model_registry,SamPredictor
        if variant not in ('vit_h','vit_l','vit_b'):raise ValueError('SAM 모델 종류 오류')
        checkpoint=Path(checkpoint).expanduser().resolve()
        if not checkpoint.is_file():raise ValueError('SAM 체크포인트 경로를 확인하세요.')
        if adaptation_path and (decoder_path or refiner_path):raise ValueError('학습 bundle과 개별 decoder/refiner는 함께 지정하지 마세요.')
        device=('cuda' if torch.cuda.is_available() else 'cpu') if device=='auto' else device
        if device not in ('cuda','cpu'):raise ValueError('장치는 auto/cpu/cuda입니다.')
        if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA를 사용할 수 없습니다.')
        base_sha=file_hash(checkpoint);cfg={};kind=None;refiner=None;learned=False
        pack=None
        if adaptation_path:
            pack=torch.load(adaptation_path,map_location='cpu',weights_only=True)
            if pack.get('schema')!=1 or pack.get('method') not in ('decoder','refiner'):raise ValueError('지원하지 않는 adaptation 형식')
            cfg=pack['config']
            if pack['base_sha256']!=base_sha or cfg['model_type']!=variant:raise ValueError('학습에 사용한 기본 SAM 가중치/variant와 다릅니다.')
            if cfg.get('preprocessing','uint8')!='uint8':raise ValueError('이 UI는 uint8 학습 전처리만 지원합니다. 원본 변환을 맞추세요.')
        model=sam_model_registry[variant](checkpoint=str(checkpoint))
        if decoder_path:
            state=torch.load(decoder_path,map_location='cpu',weights_only=True)
            if isinstance(state,dict) and 'state_dict' in state:state=state['state_dict']
            if isinstance(state,dict) and 'state' in state:
                if state.get('method')!='decoder':raise ValueError('refiner bundle은 adaptation 경로에 지정하세요.')
                if state.get('base_sha256')!=base_sha:raise ValueError('기본 SAM 가중치 불일치')
                cfg=state['config']
                if cfg.get('model_type')!=variant or cfg.get('preprocessing','uint8')!='uint8':raise ValueError('학습 decoder의 variant/전처리가 현재 입력과 다릅니다.')
                state=state['state']
            model.mask_decoder.load_state_dict(state,strict=True);learned=True
        if pack:
            if pack['method']=='decoder':model.mask_decoder.load_state_dict(pack['state'],strict=True);learned=True
            else:
                root=Path(__file__).resolve().parents[1]/'adaptation_backend'
                if str(root) not in sys.path:sys.path.insert(0,str(root))
                from temlab.models import ResidualRefiner
                refiner=ResidualRefiner(cfg['refiner_width']);refiner.load_state_dict(pack['state'],strict=True);refiner=refiner.to(device).eval();kind='residual-logits'
        if refiner_path:
            raise ValueError('기존 256px 이진마스크 TorchScript는 v2 정밀보정 계약과 다릅니다. Lab adaptation.pt를 사용하세요.')
        model=model.to(device).eval()
        self.model=model;self.predictor=SamPredictor(model);self.refiner=refiner;self.refiner_kind=kind;self.cfg=cfg;self.image_key=None
        self.info=dict(variant=variant,device=device,checkpoint=str(checkpoint),checkpoint_sha256=base_sha,decoder_path=decoder_path,adaptation_path=adaptation_path,adaptation_sha256=file_hash(adaptation_path or decoder_path) if (adaptation_path or decoder_path) else None,refiner=kind,single_mask=bool(learned or pack),adapted=bool(learned or pack),score_calibrated=False if (learned or pack) else None)
        return self.info
    def context(self,image):
        return dict(image_sha256=image_hash(image),model_sha256=self.info.get('checkpoint_sha256'),adaptation_sha256=self.info.get('adaptation_sha256'),shape=list(image.shape))
    def _set_image(self,image):
        digest=image_hash(image);cached=digest==self.image_key
        if not cached:self.predictor.set_image(image);self.image_key=digest
        return cached
    def prompt(self,image,points=None,box=None,prior=None,mask_choice=-1):
        if self.model is None:raise ValueError('먼저 SAM 모델을 로드하세요.')
        import torch
        import torch.nn.functional as F
        h,w=image.shape[:2];points=points or [];prior=prior or {};seed=None;origin='none'
        if type(mask_choice) is not int or mask_choice not in (-1,0,1,2):raise ValueError('SAM 후보 선택은 자동(-1) 또는 0/1/2입니다.')
        if any(len(p)!=3 or not np.isfinite(p).all() or p[2] not in (0,1) or not(0<=p[0]<w and 0<=p[1]<h) for p in points):raise ValueError('점 좌표/라벨 오류')
        if box is not None and (len(box)!=4 or not np.isfinite(box).all() or not(0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h)):raise ValueError('box 좌표 오류')
        cached=self._set_image(image);ctx=self.context(image)
        if prior.get('context')==ctx and isinstance(prior.get('logits'),np.ndarray) and prior['logits'].shape==(1,256,256):seed=prior['logits'];origin='sam_logits'
        elif prior.get('mask') is not None:
            m=np.asarray(prior['mask'],np.float32)
            if m.shape!=(h,w):raise ValueError('이전 mask 크기 불일치')
            x=torch.from_numpy(m)[None,None]*8-4;size=self.predictor.input_size;s=self.model.image_encoder.img_size
            x=F.interpolate(x,size=size,mode='bilinear',align_corners=False);x=F.pad(x,(0,s-size[1],0,s-size[0]),value=-4)
            seed=F.interpolate(x,size=(256,256),mode='bilinear',align_corners=False)[0].numpy();origin='binary_mask_seed'
        if not points and box is None and seed is None:raise ValueError('점 또는 box가 필요합니다.')
        xy=np.asarray([p[:2] for p in points],np.float32) if points else None;labels=np.asarray([p[2] for p in points],np.int32) if points else None
        with torch.inference_mode():
            full,scores,low=self.predictor.predict(point_coords=xy,point_labels=labels,box=np.asarray(box,np.float32) if box else None,mask_input=seed,multimask_output=not bool(self.info.get('single_mask') or seed is not None),return_logits=True)
            if mask_choice>=len(scores):raise ValueError('이 SAM 경로는 해당 후보 번호를 지원하지 않습니다. 학습/이전 mask 입력 경로는 단일 후보입니다.')
            i=int(np.argmax(scores)) if mask_choice<0 else mask_choice;native=low[i:i+1].copy();z=full[i]
            if self.refiner is not None:
                scale=min(1.,self.cfg['refine_side']/max(h,w));size=(max(8,round(h*scale)),max(8,round(w*scale)))
                rgb=torch.as_tensor(image.copy(),device=self.info['device']).permute(2,0,1)[None].float()/255
                logits=torch.as_tensor(z.copy(),device=self.info['device'])[None,None]
                rgb=F.interpolate(rgb,size=size,mode='bilinear',align_corners=False);logits=F.interpolate(logits,size=size,mode='bilinear',align_corners=False)
                z=F.interpolate(self.refiner(rgb,logits),size=(h,w),mode='bilinear',align_corners=False)[0,0].cpu().numpy()
        prob=1/(1+np.exp(-np.clip(z,-50,50)));threshold=self.cfg.get('mask_threshold',.5)
        violations=[index for index,(x,y,label) in enumerate(points) if bool(prob[min(h-1,int(np.floor(y+.5))),min(w-1,int(np.floor(x+.5)))]>=threshold)!=bool(label)]
        return dict(mask=prob>=threshold,score=float(scores[i]),logits=native,context=ctx,prior_source=origin,embedding_reused=cached,probability=prob,
                    mask_choice=i,multimask_scores=[float(s) for s in scores],prompt_violations=violations)
    def in_roi(self,image,roi,points=None,box=None,prior=None,mask_choice=-1):
        if len(roi)!=4 or not np.isfinite(roi).all():raise ValueError('ROI 오류')
        if any(float(v)!=int(v) for v in roi):raise ValueError('추론 ROI는 정수 픽셀 경계로 지정하세요.')
        x0,y0,x1,y1=map(int,roi);h,w=image.shape[:2]
        if not(0<=x0<x1<=w and 0<=y0<y1<=h):raise ValueError('ROI 오류')
        if any(len(p)!=3 or not(x0<=p[0]<x1 and y0<=p[1]<y1) for p in (points or [])):raise ValueError('모든 점은 ROI 안에 있어야 합니다.')
        if box is not None and (len(box)!=4 or not np.isfinite(box).all() or not(x0<=box[0]<box[2]<=x1 and y0<=box[1]<box[3]<=y1)):raise ValueError('box는 ROI 안에 있어야 합니다.')
        local=[[p[0]-x0,p[1]-y0,p[2]] for p in (points or [])];lb=[box[0]-x0,box[1]-y0,box[2]-x0,box[3]-y0] if box else None
        pr=None
        if prior and prior.get('mask') is not None:pr={'mask':prior['mask'][y0:y1,x0:x1]}
        kwargs={'mask_choice':mask_choice} if mask_choice!=-1 else {}
        item=self.prompt(image[y0:y1,x0:x1],local,lb,pr,**kwargs) if pr else self.prompt(image[y0:y1,x0:x1],local,lb,**kwargs)
        full=np.zeros((h,w),bool);full[y0:y1,x0:x1]=item['mask'];item['mask']=full;item['inference_domains']=[[x0,y0,x1,y1]]
        item.pop('logits',None);item.pop('context',None);item.pop('probability',None);return item
    def automatic(self,image,grid=16,pred_iou=.90,stability=.92,nms=.8,exclude=None,prepared_points=None):
        if self.model is None:raise ValueError('먼저 SAM 모델을 로드하세요.')
        from .prompts import grid_points,validate_points
        if exclude is None:exclude=np.zeros(image.shape[:2],bool)
        points=validate_points(prepared_points,image.shape[1],image.shape[0]) if prepared_points is not None else grid_points(image.shape[:2],grid,exclude)
        points=[p for p in points if not exclude[int(p[1]),int(p[0])]]
        if not points:return []
        if self.info.get('single_mask'):
            # Same single-mask output path used for training; IoU head is uncalibrated.
            kept=[];delta=self.cfg.get('stability_delta',.05);threshold=self.cfg.get('mask_threshold',.5)
            for p in points:
                x=self.prompt(image,[p+[1]]);prob=x.pop('probability');mask=x['mask'];s=float((prob>=min(1,threshold+delta)).sum()/max(1,(prob>=max(0,threshold-delta)).sum()))
                if not mask.any() or s<stability or (not self.info.get('adapted') and x['score']<pred_iou):continue
                x.update(stability=s,bbox=[],point=[p]);kept.append(x)
            kept.sort(key=lambda x:x['stability'] if self.info.get('adapted') else x['score'],reverse=True)
            selected=[]
            for x in kept:
                mask=x['mask']
                if any((mask&k['mask']).sum()/max(1,(mask|k['mask']).sum())>nms for k in selected):continue
                selected.append(x)
            return selected
        import torch
        from segment_anything import SamAutomaticMaskGenerator
        pts=np.asarray(points,np.float32)/[image.shape[1],image.shape[0]]
        gen=SamAutomaticMaskGenerator(self.model,points_per_side=None,point_grids=[pts],points_per_batch=8,crop_n_layers=0,pred_iou_thresh=pred_iou,stability_score_thresh=stability,box_nms_thresh=nms)
        with torch.inference_mode():items=gen.generate(image)
        return [dict(mask=x['segmentation'],score=float(x['predicted_iou']),stability=float(x['stability_score']),bbox=x['bbox'],point=x.get('point_coords')) for x in items]
