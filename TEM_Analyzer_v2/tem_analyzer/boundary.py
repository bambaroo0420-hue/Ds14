"""Closed contour normal-gradient refinement in original pixel coordinates."""
import numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw
from .geometry import mask_contours, resample, gray
from .preprocessing import filtered as filter_image
def sanitized(rgb,valid):
    a=rgb.copy()
    if not valid.any():raise ValueError("유효 영역이 없습니다.")
    ix=ndi.distance_transform_edt(~valid,return_distances=False,return_indices=True);a[~valid]=a[ix[0][~valid],ix[1][~valid]]
    return a

DEFAULTS=dict(inside=25,outside=25,polarity='both',smooth=.18,distance=.15,jump=4,weak=.12)

def crossing(p):
    a=np.asarray(p);b=np.roll(a,-1,axis=0);v=b-a
    cross=lambda x,y:x[...,0]*y[...,1]-x[...,1]*y[...,0]
    for i in range(len(a)-2):
        ids=np.arange(i+2,len(a));ids=ids[ids!=len(a)-1] if i==0 else ids
        q=a[ids]-a[i];den=cross(v[i],v[ids]);ok=abs(den)>1e-9
        t=np.zeros(len(ids));u=t.copy();t[ok]=cross(q[ok],v[ids][ok])/den[ok];u[ok]=cross(q[ok],v[i])/den[ok]
        if np.any(ok&(t>1e-6)&(t<1-1e-6)&(u>1e-6)&(u<1-1e-6)):return True
    return False

def topology(mask):
    return (ndi.label(mask)[1],ndi.label(ndi.binary_fill_holes(mask)&~mask)[1])

def raster(loops,shape):
    out=np.zeros(shape,bool)
    for line in loops:
        im=Image.new('1',(shape[1],shape[0]));ImageDraw.Draw(im).polygon([tuple(p) for p in line],fill=1);out^=np.array(im,bool)
    return out

def cyclic_path(cost,jump,smooth):
    N,K=cost.shape
    # Restricted start-state search; each candidate path includes the closing seam penalty.
    seam=int(np.argmax(np.partition(np.where(np.isfinite(cost),cost,1e5),min(1,K-1),axis=1)[:,min(1,K-1)]-np.min(cost,axis=1)))
    c=np.roll(cost,-seam,axis=0);starts=np.argsort(c[0])[:min(5,K)];best=None
    dest=np.arange(K)
    for start in starts:
        if not np.isfinite(c[0,start]):continue
        prev=np.full(K,np.inf);prev[start]=c[0,start];parent=np.zeros((N,K),np.int16)
        for i in range(1,N):
            choices=np.full((2*jump+1,K),np.inf)
            for j,delta in enumerate(range(-jump,jump+1)):
                src=dest+delta;ok=(src>=0)&(src<K);choices[j,ok]=prev[src[ok]]+smooth*abs(delta)
            ix=np.argmin(choices,axis=0);prev=c[i]+choices[ix,dest];parent[i]=dest+ix-jump
        prev+=smooth*abs(dest-start);prev[abs(dest-start)>jump]=np.inf
        if not np.isfinite(prev).any():continue
        end=int(np.argmin(prev));score=float(prev[end])
        if best is None or score<best[0]:
            path=np.empty(N,int);path[-1]=end
            for i in range(N-1,0,-1):path[i-1]=parent[i,path[i]]
            best=(score,np.roll(path,seam))
    return None if best is None else best[1]

def refine_all(rgb,mask,valid,settings=None,filter_cfg=None,overrides=None,pins=None):
    cfg=DEFAULTS|dict(settings or {})
    for key in ('inside','outside'):
        if not np.isfinite(cfg[key]) or not 0<=cfg[key]<=200:raise ValueError('탐색 폭은 안쪽/바깥쪽 각각 0~200 px입니다.')
    if cfg['inside']+cfg['outside']<2:raise ValueError('탐색 폭 합계는 2 px 이상이어야 합니다.')
    if not 1<=int(cfg['jump'])<=20 or not 0<=cfg['smooth']<=10 or not 0<=cfg['distance']<=10 or not 0<=cfg['weak']<=1:raise ValueError('연속성 설정 범위 오류')
    if cfg['polarity'] not in ('both','positive','negative'):raise ValueError('극성 오류')
    fc=filter_cfg or {};guard=3
    if fc.get('enabled'):
        guard+=int(np.ceil(4*float(fc.get('sigma',1.2)))) if fc.get('method','gaussian')=='gaussian' else int(np.ceil(3*float(fc.get('sigma_space',2.))))
    safe=ndi.binary_erosion(valid,iterations=guard,border_value=0)
    f=gray(filter_image(sanitized(rgb,valid),filter_cfg));gy,gx=np.gradient(f)
    signed=ndi.distance_transform_edt(mask)-ndi.distance_transform_edt(~mask)
    contours=mask_contours(mask);loops=[]
    for loop_index,contour in enumerate(contours):
        p=resample(contour,2.)[:-1];N=len(p)
        sm=ndi.gaussian_filter1d(p,1.3,axis=0,mode='wrap');t=np.roll(sm,-1,axis=0)-np.roll(sm,1,axis=0);t/=np.maximum(np.linalg.norm(t,axis=1)[:,None],1e-9);n=np.c_[-t[:,1],t[:,0]]
        sample=lambda field,xy,order=1:ndi.map_coordinates(field,[xy[...,1],xy[...,0]],order=order,mode='constant',cval=0)
        orient=sample(signed,p+n*2)-sample(signed,p-n*2);n[orient>0]*=-1
        inside=np.full(N,cfg['inside'],float);outside=np.full(N,cfg['outside'],float);polar=np.full(N,cfg['polarity'],object)
        for override in overrides or []:
            if int(override['loop'])!=loop_index:continue
            ids=[int(np.argmin(np.linalg.norm(p-np.array(ep),axis=1))) for ep in override['endpoints']];a,b=sorted(ids);sel=np.zeros(N,bool);sel[a:b+1]=True
            if b-a>N/2:sel=~sel;sel[ids]=True
            for key,arr in [('inside',inside),('outside',outside)]:
                value=float(override.get(key,cfg[key]));
                if not 0<=value<=200:raise ValueError('부분 탐색 폭은 0~200 px입니다.')
                arr[sel]=value
            pol=override.get('polarity',cfg['polarity'])
            if pol not in ('both','positive','negative'):raise ValueError('부분 극성 오류')
            polar[sel]=pol
        d=np.arange(-int(np.ceil(inside.max())),int(np.ceil(outside.max()))+1,dtype=float);zero=int(np.argmin(abs(d)))
        xy=p[:,None,:]+n[:,None,:]*d[None,:,None];allowed=sample(safe.astype(float),xy,0)>.5
        allowed&=(d[None,:]>=-inside[:,None])&(d[None,:]<=outside[:,None])
        grad=sample(gx,xy)*n[:,0,None]+sample(gy,xy)*n[:,1,None]
        response=np.abs(grad);response[polar=='positive']=np.maximum(grad[polar=='positive'],0);response[polar=='negative']=np.maximum(-grad[polar=='negative'],0)
        scale=float(np.percentile(response[allowed],95)) if allowed.any() else 0
        strength=np.clip(response/max(scale,1e-7),0,3);best=np.max(np.where(allowed,strength,0),axis=1)
        corner=np.sum(np.roll(t,3,axis=0)*np.roll(t,-3,axis=0),axis=1)<.45
        frozen=(sample(safe.astype(float),p,0)<.5)|corner|(best<cfg['weak'])|(scale<1e-7)
        cost=-strength+cfg['distance']*abs(d)[None,:]/max(abs(d).max(),1);cost[~allowed]=np.inf
        cost[frozen]=np.inf;cost[frozen,zero]=0
        for pin in pins or []:
            if int(pin['loop'])!=loop_index:continue
            q=np.asarray(pin['point'],float);i=int(np.argmin(np.linalg.norm(p-q,axis=1)));delta=float((q-p[i])@n[i]);k=int(np.argmin(abs(d-delta)))
            if frozen[i] or not allowed[i,k] or abs(delta-d[k])>1:raise ValueError('고정점이 유효 탐색 범위를 벗어납니다.')
            cost[i,abs(np.arange(len(d))-k)>1]=np.inf
        peak_path=np.argmin(cost,axis=1);peak=p+n*d[peak_path,None]
        path=cyclic_path(cost,int(cfg['jump']),float(cfg['smooth']));flags=[]
        if path is None:path=np.full(N,zero);frozen[:]=True;flags.append('연속 폐곡선 경로 실패: 원래 경계 유지')
        chosen=strength[np.arange(N),path];hit=(path==0)|(path==len(d)-1)
        uncertain=frozen|(chosen<cfg['weak'])|hit
        # Re-solve with uncertain points fixed; do not introduce discontinuities after path selection.
        newfreeze=uncertain&~frozen
        if newfreeze.any():
            cost[newfreeze]=np.inf;cost[newfreeze,zero]=0
            second=cyclic_path(cost,int(cfg['jump']),float(cfg['smooth']))
            if second is None:
                path=np.full(N,zero);uncertain[:]=True;flags.append('불확실 지점 고정 후 경로 실패: 원래 경계 유지')
            else:path=second
        offset=d[path].copy();refined=p+n*offset[:,None]
        if crossing(refined):refined=p.copy();offset[:]=0;uncertain[:]=True;flags.append('자기 교차 발생: 이 경계 보정 취소')
        if hit.mean()>.05:flags.append('탐색 폭 끝 도달 >5%: 폭/극성 확인')
        if uncertain.mean()>.2:flags.append('불확실/미보정 지점 >20%')
        loops.append(dict(initial=p.tolist(),peak=peak.tolist(),refined=refined.tolist(),normal=n.tolist(),offset_px=offset.tolist(),offset_grid=d.tolist(),response=strength.tolist(),uncertain=uncertain.tolist(),quality=dict(flags=flags,uncertain_fraction=float(uncertain.mean()),median_shift_px=float(np.median(abs(offset))))))
    original_raster=raster([e['initial'] for e in loops],mask.shape)&valid
    corrected=raster([e['refined'] for e in loops],mask.shape)&valid
    # Compare against the same contour rasterizer to avoid half-pixel fill convention differences.
    if topology(corrected)!=topology(mask) or topology(original_raster)!=topology(mask):
        for e in loops:e['refined']=e['initial'];e['offset_px']=[0.]*len(e['initial']);e['uncertain']=[True]*len(e['initial']);e['quality']['uncertain_fraction']=1.;e['quality']['median_shift_px']=0.;e['quality']['flags'].append('연결 구조 변화: 전체 보정 취소')
        corrected=mask.copy()
    return dict(loops=loops,mask=corrected,settings=cfg,filter=dict(filter_cfg or {}))
