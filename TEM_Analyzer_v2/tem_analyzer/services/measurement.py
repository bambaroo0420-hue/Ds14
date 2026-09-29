"""Review gates, alignment provenance and exportable physical measurements."""
import copy
import hashlib
import json
import numpy as np
from ..labels import compose
from ..algorithms.metrology import edge_points, robust_line, rotation_transform, measure
from .layers import active, unions, fingerprint


def alignment(project,iid,config):
    lid=int(config['layer_id']);masks=unions(project,iid)
    candidates=active(project,iid,lid)
    if lid not in masks or not candidates or not masks[lid].any():
        raise ValueError('회전 기준 레이어에 마스크를 배정하세요. 경계 보정·GT 확정은 필요하지 않습니다.')
    reviewed=all(c.get('reviewed') for c in candidates)
    edge=config.get('edge','top');mode=config.get('mode','auto');region=config.get('roi')
    if mode=='auto':
        mode='objects' if len(candidates)>1 else 'edge'
        if mode=='edge' and not region:
            yy,xx=np.nonzero(masks[lid]);h,w=masks[lid].shape
            if edge in ('top','bottom'):
                a,b=np.quantile(xx,[.15,.85]);region=[float(a/w),0,float(b/w),1] if b>a else None
            else:
                a,b=np.quantile(yy,[.15,.85]);region=[0,float(a/h),1,float(b/h)] if b>a else None
    if mode=='points':
        points=np.asarray(config.get('points',[]),float)
        h,w=masks[lid].shape
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all() or (points<0).any() or (points>=[w,h]).any():raise ValueError('기준점은 원본 영상 안의 (x,y) 좌표여야 합니다.')
        fit=robust_line(points)
    elif mode in ('edge','objects'):
        if mode=='objects':
            points=[]
            for c in candidates:
                ps=edge_points(project.mask(iid,c['id']),edge,region)
                if ps:points.append(np.median(ps,axis=0).tolist())
        else:points=edge_points(masks[lid],edge,region)
        fit=robust_line(points)
    else:raise ValueError('회전 방식은 auto/edge/objects/points입니다.')
    target=float(config.get('target_angle',0))
    if not np.isfinite(target) or not -90<=target<=90:raise ValueError('목표 방향은 -90~90도입니다.')
    angle=(target-fit['angle_deg']+90)%180-90
    residual_limit=float(config.get('max_residual',3))
    if not np.isfinite(residual_limit) or not 0<residual_limit<=100:raise ValueError('직선 잔차 기준은 0 초과~100 px입니다.')
    return dict(transform=rotation_transform(masks[lid].shape,angle),fit=fit,config=copy.deepcopy(config),
                input_hash=fingerprint(project,iid),confirmed=False,
                resolved_mode=mode,used_roi=region,mask_reviewed=reviewed,needs_review=not reviewed or fit['residual_px']>residual_limit or fit['anisotropy']<10,
                note='원본은 보존하며 회전+이동만 적용합니다. 기준 구간의 굽음은 펼치지 않습니다.')


def alignment_current(project,iid):
    value=project.state.get('alignments',{}).get(iid)
    if not value or value['input_hash']!=fingerprint(project,iid):raise ValueError('회전 결과가 없거나 입력 변경으로 만료되었습니다.')
    return value


def measurement_hash(project,iid):
    data=[fingerprint(project,iid),project.state.get('alignments',{}).get(iid),project.state['scale'].get(iid)]
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def run_measurement(project,iid,config):
    rot=alignment_current(project,iid)
    if not rot.get('confirmed'):raise ValueError('회전 결과를 먼저 확인·확정하세요.')
    scale=project.state['scale'].get(iid,{})
    if not scale.get('confirmed') or not scale.get('nm_per_px'):raise ValueError('이미지별 nm/pixel을 먼저 확인·확정하세요.')
    if project.state['preprocessing'].get(iid,{}).get('scale_status') in ('failed','error'):raise ValueError('최근 스케일 검출 실패를 수동으로 해결하세요.')
    lid=int(config['layer_id']);items=active(project,iid,lid)
    if not items:raise ValueError('측정 레이어에 마스크를 배정하세요.')
    labels,valid,conflict=compose(project,iid)
    # Include unreviewed conflicts in validity, so another candidate cannot disappear from QC.
    _,_,all_conflicts=compose(project,iid)
    m=unions(project,iid)[lid]
    if config.get('instance_id'):
        selected=[project.mask(iid,c['id']) for c in items if c.get('instance_id')==config['instance_id']]
        if not selected:raise ValueError('해당 instance가 없습니다.')
        m=np.logical_or.reduce(selected)
    cfg=dict(config);axis=cfg.get('axis','thickness')
    maximum=rot['transform']['width' if axis=='thickness' else 'height']-1
    end=cfg.get('stop');end=maximum if end is None else float(end)
    result=measure(m,valid&~all_conflicts,rot['transform'],axis,float(cfg.get('start',0)),end,float(cfg.get('step',10)),float(scale['nm_per_px']))
    result.update(image_id=iid,layer_id=lid,config=cfg,input_hash=measurement_hash(project,iid),
                  review_status='reviewed_masks' if all(c.get('reviewed') for c in items) else 'provisional_unreviewed_masks',
                  transform=copy.deepcopy(rot['transform']),scale=copy.deepcopy(scale),revision=project.state['revision'])
    return result
