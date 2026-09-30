"""Conservative two-layer gap proposals in native pixels, never hole filling.

Each supported scan intersects exactly one interval in each layer. An open DP
path selects ONE interface inside their gap; both masks share that interface.
Axis scans support approximately layered structures, not arbitrary junctions.
"""
from collections import Counter
import numpy as np
from scipy import ndimage as ndi
from scipy.signal import find_peaks
from ..geometry import gray
from ..boundary import topology


def _bounds(mask):
    present=mask.any(axis=0)
    starts=(mask & ~np.vstack([np.zeros((1,mask.shape[1]),bool),mask[:-1]])).sum(axis=0)
    first=mask.argmax(axis=0)
    last=mask.shape[0]-1-mask[::-1].argmax(axis=0)
    return first,last,present & (starts==1)


def _dp(cost,centers,jump,smooth):
    """Open path; penalize changes in image coordinates, not relative offsets."""
    n,k=cost.shape; dest=np.arange(k);prev=cost[0].copy();parents=np.zeros((n,k),np.int32)
    for i in range(1,n):
        choices=np.full((2*jump+1,k),np.inf)
        shift=int(centers[i]-centers[i-1])
        for j,delta in enumerate(range(-jump,jump+1)):
            src=dest+shift+delta;ok=(src>=0)&(src<k)
            choices[j,ok]=prev[src[ok]]+smooth*abs(delta)
        ix=choices.argmin(axis=0);prev=cost[i]+choices[ix,dest]
        parents[i]=dest+shift+ix-jump
    if not np.isfinite(prev).any():return None
    path=np.empty(n,int);path[-1]=int(prev.argmin())
    for i in range(n-1,0,-1):path[i-1]=parents[i,path[i]]
    return path


def bridge(rgb,mask_a,mask_b,blocked,settings=None):
    cfg=dict(settings or {})
    max_gap=cfg.get('max_gap',30);jump=cfg.get('jump',4)
    if type(max_gap) is not int or not 1<=max_gap<=200:raise ValueError('빈틈 최대 폭은 정수 1~200 px입니다.')
    if type(jump) is not int or not 1<=jump<=20:raise ValueError('점간 이동은 정수 1~20 px입니다.')
    smooth=float(cfg.get('smooth',.12));distance=float(cfg.get('distance',.05));weak=float(cfg.get('min_gradient',.015))
    if not all(np.isfinite(x) for x in (smooth,distance,weak)) or not 0<=smooth<=10 or not 0<=distance<=10 or not 0<weak<=1:raise ValueError('DP/gradient 설정 범위 오류')
    axis=cfg.get('axis','auto');multi=cfg.get('allow_multiple_edges',False)
    if axis not in ('auto','vertical','horizontal') or type(multi) is not bool:raise ValueError('빈틈 탐색 설정 오류')
    a=np.asarray(mask_a,bool);b=np.asarray(mask_b,bool);guard=np.asarray(blocked,bool)
    if a.shape!=b.shape or a.shape!=guard.shape or rgb.shape[:2]!=a.shape:raise ValueError('영상/마스크 크기 불일치')
    if (a&b).any():raise ValueError('선택 두 레이어가 겹칩니다. 겹침을 먼저 해결하거나 해당 부분을 분리하세요.')
    if not a.any() or not b.any():raise ValueError('두 레이어에 활성 마스크가 필요합니다.')
    # Do not let invalid annotation boundaries leak into the gradient samples.
    safe=~ndi.binary_dilation(guard,iterations=3)
    candidates=[]
    for ax in ('vertical','horizontal') if axis=='auto' else (axis,):
        aa=a if ax=='vertical' else a.T;bb=b if ax=='vertical' else b.T
        af,al,av=_bounds(aa);bf,bl,bv=_bounds(bb)
        for reverse in (False,True):
            lo,hi=(bl,af) if reverse else (al,bf)
            good=av&bv&(hi-lo>1)&(hi-lo-1<=max_gap)
            candidates.append((int(good.sum()),ax,reverse,lo,hi,good))
    _,axis,reverse,lo,hi,good=max(candidates,key=lambda x:x[0])
    aa=(b if reverse else a).copy();bb=(a if reverse else b).copy()
    if axis=='horizontal':aa=aa.T;bb=bb.T
    protected=safe if axis=='vertical' else safe.T
    f=gray(rgb);f=ndi.gaussian_filter(f,1.,mode='nearest')
    if axis=='horizontal':f=f.T
    response=abs(np.diff(f,axis=0));reasons=Counter();costs={};centers={};responses={}
    offsets=np.arange(-max_gap,max_gap+1)
    # Both sides of each scan must be known material; internal holes and multiple
    # objects along a scan are intentionally not treated as an inter-layer gap.
    for x in range(aa.shape[1]):
        if not good[x]:reasons['unsupported_or_too_wide']+=1;continue
        left,right=int(lo[x]),int(hi[x])
        if not protected[left:right+1,x].all():reasons['protected_excluded_or_other_layer']+=1;continue
        r=response[left:right,x]
        if not len(r) or float(r.max())<weak:reasons['weak_gradient']+=1;continue
        peaks,_=find_peaks(np.pad(r,(1,1)),height=max(weak,float(r.max())*.5),
                           prominence=max(weak*.5,float(r.max())*.25),distance=3)
        if len(peaks)>1 and not multi:reasons['multiple_edges_possible_third_layer']+=1;continue
        center=(left+right-1)//2;ys=center+offsets
        allowed=(ys>=left)&(ys<right)
        row=np.full(len(offsets),np.inf)
        sampled=response[np.clip(ys,0,response.shape[0]-1),x]
        row[allowed]=-sampled[allowed]/max(float(r.max()),weak)+distance*abs(offsets[allowed])/max_gap
        costs[x]=row;centers[x]=center;responses[x]=sampled
    traces=[];changed=np.zeros_like(aa);supported=np.array(sorted(costs),int)
    groups=np.split(supported,np.flatnonzero(np.diff(supported)>1)+1) if len(supported) else []
    for group in groups:
        if len(group)<3:reasons['short_run']+=len(group);continue
        cs=np.array([centers[int(x)] for x in group]);path=_dp(np.stack([costs[int(x)] for x in group]),cs,jump,smooth)
        if path is None:reasons['discontinuous_path']+=len(group);continue
        chosen=cs+offsets[path]
        if any(responses[int(x)][k]<weak for x,k in zip(group,path)):
            reasons['weak_selected_path']+=len(group);continue
        # Refuse any run that would merge objects or remove an existing hole.
        na=aa.copy();nb=bb.copy()
        for x,y in zip(group,chosen):
            na[lo[x]+1:y+1,x]=True;nb[y+1:hi[x],x]=True
        if topology(na)!=topology(aa) or topology(nb)!=topology(bb):
            reasons['topology_change']+=len(group);continue
        changed|=(na!=aa)|(nb!=bb);aa,bb=na,nb
        xy=lambda x,y:[int(x),float(y)] if axis=='vertical' else [float(y),int(x)]
        middle=int(len(group)//2);gx=int(group[middle]);gy=int(chosen[middle])
        traces.append(dict(path=[xy(x,y+.5) for x,y in zip(group,chosen)],
            edge_a=[xy(x,lo[x]+.5) for x in group],edge_b=[xy(x,hi[x]-.5) for x in group],
            profile={'scan':gx,'coordinate':list(range(int(lo[gx]),int(hi[gx]))),
                     'gradient':response[lo[gx]:hi[gx],gx].tolist(),'chosen':gy,
                     'axis':axis}))
    if axis=='horizontal':aa=aa.T;bb=bb.T;changed=changed.T
    na,nb=(bb,aa) if reverse else (aa,bb)
    assert not (na&nb).any()
    assert not changed[guard].any()
    return dict(mask_a=na,mask_b=nb,changed=changed,traces=traces,axis=axis,
                reversed=reverse,skipped=dict(reasons),filled_pixels=int(changed.sum()),
                holes_preserved=True,settings=cfg,
                note='축 방향의 단일 구간 층만 지원. 강한 gradient는 물질 경계의 정답 보장이 아님. 내부 구멍은 보존.')
