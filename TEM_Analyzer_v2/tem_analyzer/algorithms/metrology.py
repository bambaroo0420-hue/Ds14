"""Rigid pixel-centre transforms and subpixel contour intersections.

Points are (x,y), arrays are [y,x]. Angle is clockwise in image coordinates.
Pixel cells occupy [x-.5,x+.5); alignment never changes physical pixel size.
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
                anisotropy=float(vals[-1]/max(vals[0],1e-9)), points=p.tolist())


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


def measure(mask, valid, transform, axis, start, stop, step, nm_per_px):
    if axis not in ('thickness','cd'):raise ValueError('측정 방향은 thickness/cd입니다.')
    numbers = [start,stop,step,nm_per_px]
    if not np.isfinite(numbers).all() or step<=0 or stop<start or nm_per_px<=0:
        raise ValueError('측정 구간·간격·축척을 확인하세요.')
    bound = transform['width'] if axis=='thickness' else transform['height']
    if start<0 or stop>bound-1 or (stop-start)/step>10000:raise ValueError('회전 영상 범위 안에서 최대 10,001개 위치를 지정하세요.')
    if not mask.any():raise ValueError('측정할 마스크가 없습니다.')
    loops=[transform_points(c,transform['matrix']) for c in mask_contours(mask)]
    rows=[];h,w=mask.shape
    for position in np.arange(start,stop+step*1e-6,step):
        intervals=line_intervals(loops,float(position),axis)
        if not intervals:
            rows.append(dict(position_px=float(position),status='no_intersection',length_nm=None));continue
        for part,(lo,hi) in enumerate(intervals):
            a=[position,lo] if axis=='thickness' else [lo,position]
            b=[position,hi] if axis=='thickness' else [hi,position]
            # Test the interior only: contour endpoints lie on pixel-cell boundaries.
            ts=np.linspace(1e-4,1-1e-4,max(3,int(np.ceil((hi-lo)*2))+1))
            original=transform_points(np.array(a)[None,:]+ts[:,None]*(np.array(b)-a),transform['inverse'])
            indices=np.floor(original+.5).astype(int)
            inside=(indices[:,0]>=0)&(indices[:,0]<w)&(indices[:,1]>=0)&(indices[:,1]<h)
            ok=bool(inside.all() and valid[indices[:,1],indices[:,0]].all()) if inside.all() else False
            rows.append(dict(position_px=float(position),segment=part,status='ok' if ok else 'invalid_region',
                             length_px=float(hi-lo),length_nm=float((hi-lo)*nm_per_px) if ok else None,
                             aligned_endpoints=[list(map(float,a)),list(map(float,b))],
                             original_endpoints=transform_points([a,b],transform['inverse']).tolist()))
    values=[r['length_nm'] for r in rows if r['status']=='ok']
    return dict(rows=rows,axis=axis,unit='nm',summary=dict(count=len(values),mean=float(np.mean(values)) if values else None,
                median=float(np.median(values)) if values else None,std=float(np.std(values)) if values else None),
                method='rigid-transformed mask contour intersections; disconnected intervals measured separately')
