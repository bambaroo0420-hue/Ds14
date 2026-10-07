"""Review gates, alignment provenance and exportable physical measurements."""
import copy
import hashlib
import json
import numpy as np
from ..labels import compose
from ..algorithms.metrology import edge_points, robust_line, rotation_transform, measure
from .layers import active, unions, fingerprint
from .scopes import scope_arrays, scope_reviewed
from ..roi_domains import crop_guard


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
    cropped=crop_guard(project,iid,candidates)
    if cropped.any():warnings.append('ROI 절단 경계 주변은 회전 기준/계측에서 제외합니다. 후보는 ROI 밖으로 연장되지 않습니다.')
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
        if not fit['reliable_proposal']:
            warnings.append('방향 교차검증 불일치/분산이 큽니다. 이 각도를 자동 수평 정답으로 사용하지 말고 다른 ROI·경계·직접 기준점을 검토하세요.')
    elif mode=='points':
        points=np.asarray(config.get('points',[]),float)
        h,w=mask.shape
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all() or (points<0).any() or (points>=[w,h]).any():raise ValueError('기준점은 원본 영상 안의 (x,y) 좌표여야 합니다.')
        fit=robust_line(points)
    elif mode in ('edge','objects'):
        from scipy import ndimage as ndi
        from ..preprocessing import exclusion_mask
        h,w=mask.shape;guard=ndi.binary_dilation(exclusion_mask(project,iid),iterations=3)|cropped
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
    if len(fit.get('points',[]))==2:warnings.append('두 점은 항상 직선을 정의하므로 잔차 0은 정확도 증거가 아닙니다. 세 개 이상 대응점 또는 긴 경계 구간으로 교차 검토하세요.')
    target=float(config.get('target_angle',0))
    if not np.isfinite(target) or not -90<=target<=90:raise ValueError('목표 방향은 -90~90도입니다.')
    angle=(target-fit['angle_deg']+90)%180-90
    residual_limit=float(config.get('max_residual',3))
    if not np.isfinite(residual_limit) or not 0<residual_limit<=100:raise ValueError('직선 잔차 기준은 0 초과~100 px입니다.')
    return dict(transform=rotation_transform(mask.shape,angle),fit=fit,config=copy.deepcopy(config),
                input_hash=fingerprint(project,iid),confirmed=False,
                resolved_mode=mode,used_edge=used_edge,warnings=warnings,used_roi=region,mask_reviewed=reviewed,
                needs_review=bool(warnings) or not reviewed or (fit['residual_px'] is not None and fit['residual_px']>residual_limit) or (fit['anisotropy'] is not None and fit['anisotropy']<10),
                note='원본은 보존하며 회전+이동만 적용합니다. 기준 구간의 굽음은 펼치지 않습니다.')


def alignment_current(project,iid):
    value=project.state.get('alignments',{}).get(iid)
    if not value or value['input_hash']!=fingerprint(project,iid):raise ValueError('회전 결과가 없거나 입력 변경으로 만료되었습니다.')
    return value


def compare_alignment(project,iid,config):
    """Non-mutating alternatives. Agreement/low residual is NOT material GT."""
    _,_,items,_=target_masks(project,iid,config)
    plans=[('현재 설정',copy.deepcopy(config))]
    for edge in ('top','bottom'):
        plans.append(('자동 '+('위쪽' if edge=='top' else '아래쪽'),dict(config,mode='auto',edge=edge,points=[])))
    plans.append(('영상 주 방향 (실험)',dict(config,mode='image_direction',points=[])))
    if len(items)==1:
        points=[p[:2] for p in (items[0].get('prompts') or {}).get('points',[]) if len(p)==3 and p[2]==1]
        if len(points)>=2:
            plans.append(('저장 SAM 양성점 방향 (경계 정답 아님)',dict(config,mode='points',points=points,roi=None)))
    if config.get('mode')!='points' and len(config.get('points') or [])>=2:
        plans.append(('입력한 대응점',dict(config,mode='points')))
    rows=[];seen=set()
    for name,cfg in plans:
        key=json.dumps(cfg,sort_keys=True)
        if key in seen:continue
        seen.add(key)
        try:
            value=alignment(project,iid,cfg);fit=value['fit'];warnings=list(value['warnings'])
            if cfg.get('mode')=='points':warnings.append('점 방향은 사용자가 지정한 기준입니다. 두 점의 잔차 0이나 SAM 양성점 방향 일치는 물질 경계 정확도를 증명하지 않습니다.')
            rows.append(dict(name=name,status='proposed',config=cfg,angle_deg=value['transform']['angle_deg'],
                             residual_px=fit['residual_px'],point_count=None if value['resolved_mode']=='image_direction' else len(fit.get('points',[])),anisotropy=fit['anisotropy'],
                             needs_review=True,warnings=warnings))
        except ValueError as exc:rows.append(dict(name=name,status='failed',config=cfg,error=str(exc)))
    angles=[r['angle_deg'] for r in rows if r['status']=='proposed']
    gap=max((abs((a-b+90)%180-90) for a in angles for b in angles),default=0.)
    return dict(image_id=iid,input_hash=fingerprint(project,iid),rows=rows,max_angle_gap_deg=float(gap),
                note='비교는 기존 회전/계측/GT를 변경하지 않습니다. 작은 잔차나 방식 간 일치만으로 자동 정답을 고르지 않습니다. 선택 후 원본·회전 영상을 확인하세요.')


def measurement_hash(project,iid):
    reviews={k:v.get('review_hash') for k,v in project.state.get('mask_scopes',{}).get(iid,{}).items()}
    data=['contour_validity_v3',fingerprint(project,iid),project.state.get('alignments',{}).get(iid),project.state['scale'].get(iid),reviews]
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def stored_measurements(project,iid):
    """Latest result per axis, with a read-only fallback for pre-v2.2.8 projects."""
    values=dict(project.state.get('measurements_by_axis',{}).get(iid,{}))
    latest=project.state.get('measurements',{}).get(iid)
    if latest:values[latest['axis']]=latest
    return values


def save_measurement(project,iid,value):
    values=stored_measurements(project,iid);values[value['axis']]=copy.deepcopy(value)
    project.state.setdefault('measurements_by_axis',{})[iid]=values
    project.state['measurements'][iid]=value
    return value


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
    result=measure(m,valid&~all_conflicts,rot['transform'],axis,float(cfg.get('start',0)),end,float(cfg.get('step',10)),float(scale['nm_per_px']),cfg.get('sampling'))
    cropped=crop_guard(project,iid,items)
    result['roi_cut_guard_pixels']=int(cropped.sum())
    if cropped.any():result['warnings'].append('추론 ROI 가장자리 2 px 이내의 절단 의심 영역을 2 px 확장해 미지정 처리합니다. 이를 통과하는 계측은 invalid_region이며 원시 길이만 보존합니다.')
    result.update(image_id=iid,layer_id=lid,scope_id=config.get('scope_id'),candidate_ids=[c['id'] for c in items],config=cfg,input_hash=measurement_hash(project,iid),
                  review_status='reviewed_masks' if reviewed else 'provisional_unreviewed_masks',
                  transform=copy.deepcopy(rot['transform']),scale=copy.deepcopy(scale),revision=project.state['revision'])
    return result
