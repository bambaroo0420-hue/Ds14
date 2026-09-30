"""Versioned manual objects. Coordinates are original-image pixels; ROI is normalized.

Groups are independent SAM objects, not alternative masks from one SAM request.
Transferred parent IDs are provenance only, never target-image candidate IDs.
"""
import copy
import numpy as np
from ..prompts import validate_points


def validate_groups(groups,w,h):
    if not isinstance(groups,list) or len(groups)>32:raise ValueError('Manual 그룹은 최대 32개입니다.')
    result=[];names=set();total=0
    for raw in groups:
        group=copy.deepcopy(raw);name=str(group.get('name','')).strip()
        if not name or len(name)>80 or name in names:raise ValueError('Manual 그룹 이름은 1~80자로 서로 달라야 합니다.')
        names.add(name);ps=group.get('points',[]);validate_points(ps,w,h);total+=len(ps)
        if any(len(p)!=3 or p[2] not in (0,1) for p in ps):raise ValueError('그룹 점은 [x,y,0 또는 1]입니다.')
        box=group.get('box');roi=group.get('roi')
        if box is not None and (len(box)!=4 or not np.isfinite(box).all() or not(0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h)):raise ValueError('그룹 box 범위 오류')
        if roi is not None and (len(roi)!=4 or not np.isfinite(roi).all() or not(0<=roi[0]<roi[2]<=1 and 0<=roi[1]<roi[3]<=1)):raise ValueError('그룹 ROI는 0~1 정규화 좌표입니다.')
        if roi is not None:
            x0,y0,x1,y1=np.array(roi)*[w,h,w,h]
            if any(not(x0<=p[0]<x1 and y0<=p[1]<y1) for p in ps):raise ValueError('Manual 점이 지정 ROI 밖입니다.')
            if box and not(x0<=box[0]<box[2]<=x1 and y0<=box[1]<box[3]<=y1):raise ValueError('Manual box가 ROI 밖입니다.')
        if not box and not any(p[2] for p in ps):raise ValueError('그룹마다 양성점 또는 box가 필요합니다.')
        result.append(dict(group,name=name,points=ps,box=box,roi=roi,locked=bool(group.get('locked',False))))
    if total>2048:raise ValueError('그룹 수동점은 최대 2048개입니다.')
    return result


def infer_groups(model,image,groups,exclude):
    # Validate every group before ANY inference; negative points are not silently dropped.
    groups=validate_groups(groups,image.shape[1],image.shape[0])
    if any(exclude[int(p[1]),int(p[0])] for g in groups for p in g['points']):raise ValueError('그룹 점이 제외 영역에 있습니다. 위치를 수정하세요.')
    result=[]
    for g in groups:
        roi=(np.array(g['roi'])*[image.shape[1],image.shape[0],image.shape[1],image.shape[0]]).tolist() if g['roi'] else None
        if roi:roi=[int(np.floor(roi[0]+1e-8)),int(np.floor(roi[1]+1e-8)),int(np.ceil(roi[2]-1e-8)),int(np.ceil(roi[3]-1e-8))]
        item=model.in_roi(image,roi,g['points'],g['box']) if roi else model.prompt(image,g['points'],g['box'])
        result.append((item,g))
    return result
