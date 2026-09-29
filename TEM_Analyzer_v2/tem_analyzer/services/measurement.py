"""Review gates, alignment provenance and exportable physical measurements."""
import copy
import hashlib
import json
import numpy as np
from ..labels import compose
from ..algorithms.metrology import edge_points, robust_line, rotation_transform, measure
from .layers import active, unions, fingerprint
from .scopes import scope_arrays, scope_reviewed


def target_masks(project,iid,config):
    if config.get('scope_id'):
        mask,_,_,items=scope_arrays(project,iid,config['scope_id'])
        return None,mask,items,scope_reviewed(project,iid,config['scope_id'])
    lid=int(config['layer_id']);items=active(project,iid,lid);masks=unions(project,iid)
    if not items or lid not in masks or not masks[lid].any():
        raise ValueError('대상 레이어에 마스크를 배정하거나 저장한 선택 마스크 집합을 사용하세요. GT는 필요하지 않습니다.')
    return lid,masks[lid],items,all(c.get('reviewed') for c in items)


def alignment(project,iid,config):
    lid,mask,candidates,reviewed=target_masks(project,iid,config)
    edge=config.get('edge','top');mode=config.get('mode','auto');region=config.get('roi')
    requested_mode=mode;used_edge=edge;warnings=[]
    if mode=='auto':
        mode='objects' if len(candidates)>1 else 'edge'
        if mode=='edge' and not region:
            yy,xx=np.nonzero(mask);h,w=mask.shape
            if edge in ('top','bottom'):
                a,b=np.quantile(xx,[.15,.85]);region=[float(a/w),0,float(b/w),1] if b>a else None
            else:
                a,b=np.quantile(yy,[.15,.85]);region=[0,float(a/h),1,float(b/h)] if b>a else None
    if mode=='image_direction':
        from ..algorithms.orientation import image_direction
        from ..preprocessing import exclusion_mask
        fit=image_direction(project.image(iid),exclusion_mask(project,iid),region)
        warnings.append(fit['note'])
    elif mode=='points':
        points=np.asarray(config.get('points',[]),float)
        h,w=mask.shape
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all() or (points<0).any() or (points>=[w,h]).any():raise ValueError('기준점은 원본 영상 안의 (x,y) 좌표여야 합니다.')
        fit=robust_line(points)
    elif mode in ('edge','objects'):
        from scipy import ndimage as ndi
        from ..preprocessing import exclusion_mask
        h,w=mask.shape;guard=ndi.binary_dilation(exclusion_mask(project,iid),iterations=3)
        margin=max(1.,min(h,w)*.005)
        def usable(m,which):
            pts=edge_points(m,which,region)
            return [p for p in pts if margin<p[0]<w-1-margin and margin<p[1]<h-1-margin and not guard[int(round(p[1])),int(round(p[0]))]]
        if mode=='objects':
            points=[]
            for c in candidates:
                ps=usable(project.mask(iid,c['id']),edge)
                if ps:points.append(np.median(ps,axis=0).tolist())
        else:
            points=usable(mask,edge)
            if len(points)<2 and requested_mode=='auto':
                alternatives=('bottom','top') if edge in ('top','bottom') else ('right','left')
                for other in alternatives:
                    alternative=usable(mask,other)
                    if len(alternative)>=2:
                        points=alternative;used_edge=other;warnings.append('지정 경계가 프레임/제외 영역과 겹쳐 반대 경계를 사용했습니다. 검토가 필요합니다.');break
        if len(points)<2:raise ValueError('프레임/제외 영역을 제외한 유효 경계가 부족합니다. 다른 경계·ROI·직접 기준점을 선택하세요.')
        fit=robust_line(points)
    else:raise ValueError('회전 방식은 auto/edge/objects/points/image_direction입니다.')
    target=float(config.get('target_angle',0))
    if not np.isfinite(target) or not -90<=target<=90:raise ValueError('목표 방향은 -90~90도입니다.')
    angle=(target-fit['angle_deg']+90)%180-90
    residual_limit=float(config.get('max_residual',3))
    if not np.isfinite(residual_limit) or not 0<residual_limit<=100:raise ValueError('직선 잔차 기준은 0 초과~100 px입니다.')
    return dict(transform=rotation_transform(mask.shape,angle),fit=fit,config=copy.deepcopy(config),
                input_hash=fingerprint(project,iid),confirmed=False,
                resolved_mode=mode,used_edge=used_edge,warnings=warnings,used_roi=region,mask_reviewed=reviewed,needs_review=bool(warnings) or not reviewed or fit['residual_px']>residual_limit or fit['anisotropy']<10,
                note='원본은 보존하며 회전+이동만 적용합니다. 기준 구간의 굽음은 펼치지 않습니다.')


def alignment_current(project,iid):
    value=project.state.get('alignments',{}).get(iid)
    if not value or value['input_hash']!=fingerprint(project,iid):raise ValueError('회전 결과가 없거나 입력 변경으로 만료되었습니다.')
    return value


def measurement_hash(project,iid):
    reviews={k:v.get('review_hash') for k,v in project.state.get('mask_scopes',{}).get(iid,{}).items()}
    data=[fingerprint(project,iid),project.state.get('alignments',{}).get(iid),project.state['scale'].get(iid),reviews]
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def run_measurement(project,iid,config):
    rot=alignment_current(project,iid)
    if not rot.get('confirmed'):raise ValueError('회전 결과를 먼저 확인·확정하세요.')
    scale=project.state['scale'].get(iid,{})
    if not scale.get('confirmed') or not scale.get('nm_per_px'):raise ValueError('이미지별 nm/pixel을 먼저 확인·확정하세요.')
    if project.state['preprocessing'].get(iid,{}).get('scale_status') in ('failed','error'):raise ValueError('최근 스케일 검출 실패를 수동으로 해결하세요.')
    lid,m,items,reviewed=target_masks(project,iid,config)
    if config.get('scope_id'):
        _,_,valid,_=scope_arrays(project,iid,config['scope_id']);all_conflicts=np.zeros_like(valid)
    else:
        _,valid,all_conflicts=compose(project,iid)
    if config.get('instance_id'):
        selected=[project.mask(iid,c['id']) for c in items if c.get('instance_id')==config['instance_id']]
        if not selected:raise ValueError('해당 instance가 없습니다.')
        m=np.logical_or.reduce(selected)
    cfg=dict(config);axis=cfg.get('axis','thickness')
    maximum=rot['transform']['width' if axis=='thickness' else 'height']-1
    end=cfg.get('stop');end=maximum if end is None else float(end)
    result=measure(m,valid&~all_conflicts,rot['transform'],axis,float(cfg.get('start',0)),end,float(cfg.get('step',10)),float(scale['nm_per_px']))
    result.update(image_id=iid,layer_id=lid,scope_id=config.get('scope_id'),candidate_ids=[c['id'] for c in items],config=cfg,input_hash=measurement_hash(project,iid),
                  review_status='reviewed_masks' if reviewed else 'provisional_unreviewed_masks',
                  transform=copy.deepcopy(rot['transform']),scale=copy.deepcopy(scale),revision=project.state['revision'])
    return result
