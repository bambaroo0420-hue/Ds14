"""Independent SAM/edge inputs and per-image immutable settings snapshots."""
from copy import deepcopy
import numpy as np
from scipy import ndimage as ndi
from .operations import excluded,scale_from_points
from .calibration import bar_candidates

DEFAULT_FILTER={'enabled':False,'method':'gaussian','sigma':1.,'range_sigma':.08,'contrast':1.,'median_size':3,'nlm_h':10.}

def filter_support(cfg):
    cfg=DEFAULT_FILTER|dict(cfg or {})
    if not cfg['enabled']:return 0
    if cfg['method']=='median':return int(cfg['median_size'])//2
    if cfg['method']=='nlm':return 13  # 21px search + 7px patch support
    return int(np.ceil((4 if cfg['method']=='gaussian' else 2)*float(cfg['sigma'])))

def exclusion_mask(project,iid):
    from .labels import unpack
    info=project.state['images'][iid];shape=(info['height'],info['width'])
    return excluded(shape,effective_template(project,iid))|unpack(project.state.get('annotations',{}).get(iid,{}).get('exclude'),shape)

def effective_template(project,iid):
    project.require_image(iid)
    record=project.state.get('preprocessing',{}).get(iid,{})
    # OCR regions and legacy fixed-position templates are independent inputs.
    auto=record.get('auto_regions') or {'scale_roi':None,'text_rois':[]}
    if not project.state.get('legacy_templates_enabled',False):return deepcopy(auto)
    legacy=record.get('template') or {}
    result=deepcopy(legacy)
    result['text_rois']=list(result.get('text_rois',[]))+list(auto.get('text_rois',[]))
    if auto.get('scale_roi'):
        if result.get('scale_roi'):result['text_rois'].append(result['scale_roi'])
        result['scale_roi']=auto['scale_roi']
    return result

def filtered(image,cfg):
    cfg=DEFAULT_FILTER|dict(cfg or {});sigma=float(cfg['sigma']);contrast=float(cfg['contrast'])
    if not 0<=sigma<=4 or not .25<=contrast<=3:raise ValueError('sigma 0~4, 대비 0.25~3 범위입니다.')
    if cfg['method'] not in ('gaussian','bilateral','median','nlm'):raise ValueError('필터 종류 오류')
    if cfg['median_size'] not in (3,5,7,9):raise ValueError('Median 크기는 3/5/7/9입니다.')
    if not 1<=float(cfg['nlm_h'])<=40:raise ValueError('NLM 강도는 1~40입니다.')
    if not .01<=float(cfg['range_sigma'])<=1:raise ValueError('밝기 sigma 범위 0.01~1')
    if not cfg['enabled']:return image.copy()
    g=image.astype(np.float32)/255
    if cfg['method']=='median':g=ndi.median_filter(g,size=(int(cfg['median_size']),int(cfg['median_size']),1))
    elif cfg['method']=='nlm':
        from .feature_prompts import _cv
        cv=_cv()
        # Independent channels preserve RGB ordering and work on grayscale TEM RGB too.
        g=np.stack([cv.fastNlMeansDenoising(image[:,:,c],None,float(cfg['nlm_h']),7,21) for c in range(3)],axis=-1).astype(np.float32)/255
    elif sigma:
        if cfg['method']=='gaussian':g=ndi.gaussian_filter(g,(sigma,sigma,0))
        else:
            rs=float(cfg['range_sigma'])
            if not .01<=rs<=1:raise ValueError('밝기 sigma 범위 0.01~1')
            radius=int(np.ceil(2*sigma));pad=np.pad(g,((radius,radius),(radius,radius),(0,0)),mode='reflect');acc=np.zeros_like(g);den=np.zeros(g.shape[:2],np.float32)
            for dy in range(-radius,radius+1):
                for dx in range(-radius,radius+1):
                    q=pad[radius+dy:radius+dy+g.shape[0],radius+dx:radius+dx+g.shape[1]]
                    weight=np.exp(-(dx*dx+dy*dy)/(2*sigma*sigma)-np.mean((q-g)**2,axis=2)/(2*rs*rs))
                    acc+=q*weight[...,None];den+=weight
            g=acc/np.maximum(den[...,None],1e-8)
    return np.uint8(np.clip((g-.5)*contrast+.5,0,1)*255)

def model_input(project,iid,branch='sam'):
    image=project.image(iid);record=project.state.get('preprocessing',{}).get(iid,{})
    ex=exclusion_mask(project,iid)
    if ex.all():raise ValueError('분석할 유효 영역이 없습니다.')
    if ex.any():
        idx=ndi.distance_transform_edt(ex,return_distances=False,return_indices=True)
        image[ex]=image[idx[0][ex],idx[1][ex]]
    return filtered(image,record.get(branch+'_filter',DEFAULT_FILTER))

def restrict_mask(project,iid,mask):
    m=np.asarray(mask,bool).copy();m[exclusion_mask(project,iid)]=False;return m

def apply_one(project,iid,template,regions,scale,length,unit):
    if not project.state.get('legacy_templates_enabled',False):raise ValueError('기존 위치 템플릿이 비활성화되어 있습니다. OCR 자동 검출을 사용하거나 템플릿을 켜세요.')
    image=project.image(iid);record=deepcopy(project.state['preprocessing'].get(iid,{}))
    record.update(reviewed=False,scale_requested=scale,last_error=None)
    if regions:record['template']=deepcopy(template);record['excluded_pixels']=int(excluded(image.shape[:2],template).sum())
    record['regions_applied']=record.get('template') is not None
    if scale:
        bars=bar_candidates(image,template.get('scale_roi'));record.update(scale_status='failed',bar_candidates=bars)
        if bars:
            chosen=bars[0];nm=scale_from_points(*chosen['bar'],length,unit)
            project.state['scale'][iid]=dict(bar=chosen['bar'],nm_per_px=nm,px_per_nm=1/nm,pixel_length=chosen['pixel_length'],length=length,unit=unit,confirmed=False,source='batch-manual-length')
            record['scale_status']='proposed'
        else:record['last_error']='바 검출 실패: 수동 입력하세요. 이전 스케일은 보존했습니다.'
    else:record.update(scale_status='not_requested',bar_candidates=[])
    project.state['preprocessing'][iid]=record
    if regions:project.invalidate(iid,'제외 영역 변경')
    return record
