"""Rigid pixel-centre transforms and subpixel contour intersections.

Points are (x,y), arrays are [y,x]. Angle is clockwise in image coordinates.
Image extent is [-.5,w-.5] x [-.5,h-.5]; mask geometry is the interpolated
0.5 contour, not the union of square pixel cells. Alignment preserves scale.
"""
import math
import numpy as np
from scipy import ndimage as ndi
from ..geometry import mask_contours


def transform_points(points, matrix):
    p = np.asarray(points, dtype=float)
    return p @ np.asarray(matrix, float)[:2, :2].T + np.asarray(matrix, float)[:2, 2]


def rotation_transform(shape, angle_deg):
    h, w = shape[:2]
    if not np.isfinite(angle_deg) or abs(angle_deg) > 180:
        raise ValueError('회전각은 -180~180도입니다.')
    t = math.radians(angle_deg); c, s = math.cos(t), math.sin(t)
    matrix = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    corners = transform_points([[-.5,-.5],[w-.5,-.5],[w-.5,h-.5],[-.5,h-.5]], matrix)
    lo, hi = corners.min(axis=0), corners.max(axis=0)
    matrix[:2, 2] = -.5 - lo
    size = np.ceil(np.maximum(hi-lo-1e-9, 1)).astype(int)
    if int(size[0])*int(size[1])>64_000_000:
        raise ValueError('확장 회전 영상이 64 MP를 초과합니다. 입력 크기/각도를 줄이세요.')
    return dict(matrix=matrix.tolist(), inverse=np.linalg.inv(matrix).tolist(),
                width=int(size[0]), height=int(size[1]), angle_deg=float(angle_deg))


def warp(array, transform, order=0, fill=0):
    inv = np.asarray(transform['inverse']); xy = inv[:2,:2]
    yx = xy[[1,0]][:,[1,0]]; offset = inv[:2,2][[1,0]]
    shape = (transform['height'], transform['width'])
    def channel(a):
        return ndi.affine_transform(a, yx, offset, output_shape=shape, order=order, mode='constant', cval=fill, prefilter=False)
    return np.stack([channel(array[...,k]) for k in range(array.shape[2])], axis=-1) if array.ndim==3 else channel(array)


def robust_line(points):
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 2 or len(p)<2 or not np.isfinite(p).all():
        raise ValueError('유효한 기준점이 두 개 이상 필요합니다.')
    weights = np.ones(len(p))
    for _ in range(12):
        center = np.average(p, axis=0, weights=weights)
        q = p-center
        cov = (q*weights[:,None]).T @ q / weights.sum()
        vals, vecs = np.linalg.eigh(cov); direction = vecs[:,-1]
        normal = np.array([-direction[1],direction[0]])
        residual = abs(q @ normal)
        sigma = max(.25, 1.4826*np.median(abs(residual-np.median(residual))))
        weights = np.minimum(1., 1.5*sigma/np.maximum(residual, 1e-9))
    if np.ptp(q @ direction)<4:
        raise ValueError('회전 기준 구간은 4 px 이상이어야 합니다.')
    angle = math.degrees(math.atan2(direction[1],direction[0]))
    angle = (angle+90)%180-90
    return dict(angle_deg=angle, residual_px=float(np.sqrt(np.average(residual**2,weights=weights))),
                anisotropy=float(vals[-1]/max(vals[0],1e-9)), points=p.tolist(),
                center=center.tolist(),direction=direction.tolist(),weights=weights.tolist(),residuals=residual.tolist())


def edge_points(mask, edge='top', roi=None):
    if edge not in ('top','bottom','left','right'):
        raise ValueError('경계는 top/bottom/left/right 중 선택하세요.')
    h,w = mask.shape
    valid = mask.copy()
    if roi:
        if len(roi)!=4 or not (0<=roi[0]<roi[2]<=1 and 0<=roi[1]<roi[3]<=1):
            raise ValueError('경계 구간은 0~1 정규화 box입니다.')
        window = np.zeros_like(mask);x0,y0,x1,y1 = np.array(roi)*[w,h,w,h]
        window[int(y0):int(y1),int(x0):int(x1)] = True
        # Extract the ORIGINAL boundary first, then keep points inside the selected ROI.
    vertical = edge in ('left','right'); a = mask.T if vertical else mask
    points = []
    for x in range(a.shape[1]):
        ys = np.flatnonzero(a[:,x])
        if not len(ys):continue
        y = float(ys[0]-.5 if edge in ('top','left') else ys[-1]+.5)
        p = [y,float(x)] if vertical else [float(x),y]
        if roi and not (x0<=p[0]<=x1 and y0<=p[1]<=y1):continue
        points.append(p)
    return points


def line_intervals(loops, coordinate, axis):
    # Half-open vertex crossing counts each vertex once. Even-odd preserves holes.
    crossings = []
    fixed = 0 if axis=='thickness' else 1; varying=1-fixed
    for loop in loops:
        a = np.asarray(loop,float); b = np.roll(a,-1,axis=0)
        hit = ((a[:,fixed]<=coordinate)&(b[:,fixed]>coordinate)) | ((b[:,fixed]<=coordinate)&(a[:,fixed]>coordinate))
        aa,bb=a[hit],b[hit]
        if len(aa):crossings.extend((aa[:,varying]+(coordinate-aa[:,fixed])*(bb[:,varying]-aa[:,varying])/(bb[:,fixed]-aa[:,fixed])).tolist())
    crossings.sort()
    if len(crossings)%2:raise ValueError('경계 교차 수가 홀수입니다. 마스크를 검토하세요.')
    return [(crossings[i],crossings[i+1]) for i in range(0,len(crossings),2) if crossings[i+1]-crossings[i]>1e-6]


def interval_coverage(lo,hi,valid_spans):
    """Coverage in the SAME interpolated-contour geometry as the measurement.

    Nearest-pixel validity is a different geometry at concave/diagonal corners.
    Never dilate validity or skip its unknown/excluded interior holes to fix it.
    """
    covered=sum(max(0.,min(hi,b)-max(lo,a)) for a,b in valid_spans)
    return max(0.,min(hi-lo,covered))


def measure(mask, valid, transform, axis, start, stop, step, nm_per_px, sampling=None):
    mask=np.asarray(mask,bool);valid=np.asarray(valid,bool)
    if mask.ndim!=2 or valid.shape!=mask.shape:raise ValueError('마스크와 유효 영역은 동일한 2차원 크기여야 합니다.')
    if axis not in ('thickness','cd'):raise ValueError('측정 방향은 thickness/cd입니다.')
    numbers = [start,stop,step,nm_per_px]
    if not np.isfinite(numbers).all() or step<=0 or stop<start or nm_per_px<=0:
        raise ValueError('측정 구간·간격·축척을 확인하세요.')
    bound = transform['width'] if axis=='thickness' else transform['height']
    if start<0 or stop>bound-1 or (stop-start)/step>10000:raise ValueError('회전 영상 범위 안에서 최대 10,001개 위치를 지정하세요.')
    if not mask.any():raise ValueError('측정할 마스크가 없습니다.')
    policy=dict(sampling or {})
    mode=policy.get('mode','all');fraction=float(policy.get('center_fraction',.6))
    minimum=float(policy.get('min_length_px',0))
    single=policy.get('single_interval_only',False);reject_frame=policy.get('reject_frame_endpoints',False)
    if mode not in ('all','component_center') or not np.isfinite([fraction,minimum]).all() or not 0<fraction<=1 or not 0<=minimum<=100000:
        raise ValueError('계측 표본 방식/중앙 비율(0 초과~1)/최소 길이(0~100000 px)를 확인하세요.')
    if not isinstance(single,bool) or not isinstance(reject_frame,bool):raise ValueError('계측 제외 옵션은 true/false여야 합니다.')
    policy=dict(mode=mode,center_fraction=fraction,min_length_px=minimum,single_interval_only=single,reject_frame_endpoints=reject_frame)
    # Geometric components are NOT material classes or original SAM candidate IDs.
    labels,count=ndi.label(mask)
    if count>512:raise ValueError('분리 객체가 512개를 넘습니다. 작은 잡음 마스크를 검토하거나 분석 대상을 나누세요.')
    components=[];fixed=0 if axis=='thickness' else 1
    for cid,sl in enumerate(ndi.find_objects(labels),1):
        local=labels[sl]==cid;offset=np.array([sl[1].start,sl[0].start])
        loops=[transform_points(c+offset,transform['matrix']) for c in mask_contours(local)]
        good=local&valid[sl]
        all_valid=bool(valid[sl][local].all())
        valid_loops=loops if all_valid else [transform_points(c+offset,transform['matrix']) for c in mask_contours(good)] if good.any() else []
        coordinates=np.concatenate(loops)[:,fixed];lo,hi=float(coordinates.min()),float(coordinates.max())
        trim=(hi-lo)*(1-fraction)/2
        components.append(dict(component_id=cid,loops=loops,valid_loops=valid_loops,all_valid=all_valid,bounds=[lo,hi],window=[lo+trim,hi-trim],area_px=int(local.sum())))
    rows=[];h,w=mask.shape
    for position in np.arange(start,stop+step*1e-6,step):
        intervals=[]
        for comp in components:
            if not comp['bounds'][0]<=position<=comp['bounds'][1]:continue
            spans=line_intervals(comp['loops'],float(position),axis)
            valid_spans=spans if comp['all_valid'] else line_intervals(comp['valid_loops'],float(position),axis)
            intervals.extend((lo,hi,comp,len(spans),interval_coverage(lo,hi,valid_spans)) for lo,hi in spans)
        intervals.sort(key=lambda x:x[0])
        if not intervals:
            rows.append(dict(position_px=float(position),status='no_intersection',length_nm=None));continue
        for part,(lo,hi,comp,span_count,covered) in enumerate(intervals):
            a=[position,lo] if axis=='thickness' else [lo,position]
            b=[position,hi] if axis=='thickness' else [hi,position]
            # Require full continuous interval coverage by valid target contours;
            # sampling can both falsely reject corners and miss tiny invalid cuts.
            invalid=max(0.,hi-lo-covered);ok=invalid<=1e-7
            endpoints=transform_points([a,b],transform['inverse'])
            frame=bool((endpoints<=0).any() or (endpoints[:,0]>=w-1).any() or (endpoints[:,1]>=h-1).any())
            outside=not comp['window'][0]<=position<=comp['window'][1]
            flags=[];reasons=[]
            if not ok:reasons.append('invalid_region')
            if mode=='component_center' and outside:flags.append('outside_component_window');reasons.append('outside_component_window')
            if span_count>1:
                flags.append('multiple_intervals')
                if single:reasons.append('multiple_intervals')
            if frame:
                flags.append('frame_endpoint')
                if reject_frame:reasons.append('frame_endpoint')
            if hi-lo<minimum:flags.append('below_min_length');reasons.append('below_min_length')
            status=reasons[0] if reasons else 'ok'
            rows.append(dict(position_px=float(position),segment=part,component_id=comp['component_id'],status=status,
                             quality_flags=flags,exclusion_reasons=reasons,
                             length_px=float(hi-lo),raw_length_nm=float((hi-lo)*nm_per_px),length_nm=float((hi-lo)*nm_per_px) if status=='ok' else None,
                             valid_coverage_px=float(covered),invalid_coverage_px=float(invalid),
                             aligned_endpoints=[list(map(float,a)),list(map(float,b))],
                             original_endpoints=endpoints.tolist()))
    values=[r['length_nm'] for r in rows if r['status']=='ok']
    counts={status:sum(r['status']==status for r in rows) for status in sorted({r['status'] for r in rows})}
    warnings=[]
    if any('multiple_intervals' in r.get('quality_flags',[]) for r in rows):warnings.append('동일 연결 객체에 다중 교차가 있습니다. 구멍/분기 구간을 전체 층 두께로 해석하지 마세요.')
    if any('frame_endpoint' in r.get('quality_flags',[]) for r in rows):warnings.append('영상 프레임에 닿는 끝점이 있습니다. 잘린 폭/두께일 수 있습니다.')
    if len(values)<5:warnings.append('유효 표본이 5개 미만입니다. 구간·간격·마스크를 검토하세요.')
    if values and len(values)>=5 and abs(float(np.mean(values)-np.median(values)))>max(1e-9,abs(float(np.median(values)))*.1):
        warnings.append('평균과 중앙값이 10% 이상 다릅니다. 끝부분·다중 교차·실제 두께 변화를 검토하세요. 자동 이상값 삭제는 하지 않았습니다.')
    for comp in components:
        del comp['loops'];del comp['valid_loops'];del comp['all_valid']
        comp['accepted_count']=sum(r.get('component_id')==comp['component_id'] and r['status']=='ok' for r in rows)
    return dict(rows=rows,axis=axis,unit='nm',summary=dict(count=len(values),mean=float(np.mean(values)) if values else None,
                median=float(np.median(values)) if values else None,std=float(np.std(values)) if values else None,
                min=float(np.min(values)) if values else None,max=float(np.max(values)) if values else None,status_counts=counts),
                sampling=policy,components=components,warnings=warnings,
                validity_method='full interval coverage by equally interpolated valid-target contours; tolerance 1e-7 px; no validity dilation',
                method='rigid-transformed mask contour intersections; contour-consistent validity; geometric components and disconnected intervals measured separately; explicit sampling exclusions retained as rows')
