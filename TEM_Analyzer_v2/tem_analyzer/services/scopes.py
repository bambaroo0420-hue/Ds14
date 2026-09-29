"""Explicit per-image binary target selections, independent of semantic layers."""
import copy
import hashlib
import json
import re
import numpy as np
from ..labels import UNKNOWN, UNCERTAIN, EXCLUDED, unpack
from ..preprocessing import exclusion_mask
from .layers import fingerprint


def scope_key(value):
    value=str(value)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):
        raise ValueError('선택 집합 ID는 영문/숫자/_/- 1~64자입니다.')
    return value


def get_scope(project,iid,key):
    project.require_image(iid);key=scope_key(key)
    scope=project.state.get('mask_scopes',{}).get(iid,{}).get(key)
    if not scope:raise ValueError(f'이 이미지에 선택 집합 {key}가 없습니다. 필요한 마스크를 먼저 저장하세요.')
    items=[project.candidate(iid,cid) for cid in scope['candidate_ids']]
    if not items or any(c is None or not c.get('active',True) for c in items):
        raise ValueError('선택 마스크가 삭제/교체되었습니다. 선택 집합을 다시 저장하세요.')
    return scope,items


def save_scope(project,iid,key,ids,name='분석 대상'):
    project.require_image(iid);key=scope_key(key)
    if not isinstance(ids,list) or any(type(x) is not int for x in ids):raise ValueError('마스크 ID 배열이 필요합니다.')
    ids=list(dict.fromkeys(ids))
    items=[project.candidate(iid,cid) for cid in ids]
    if not items or any(c is None or not c.get('active',True) for c in items):raise ValueError('활성 마스크를 선택하세요.')
    scope=dict(id=key,name=str(name)[:120],candidate_ids=ids,review_hash=None,
               semantics='binary_target_union; unselected pixels unknown; not a material class')
    project.state.setdefault('mask_scopes',{}).setdefault(iid,{})[key]=scope
    return copy.deepcopy(scope)


def scope_hash(project,iid,key):
    scope,_=get_scope(project,iid,key)
    return hashlib.sha256(json.dumps([fingerprint(project,iid),key,scope['candidate_ids']],sort_keys=True).encode()).hexdigest()


def scope_arrays(project,iid,key):
    scope,items=get_scope(project,iid,key)
    mask=np.logical_or.reduce([project.mask(iid,c['id']) for c in items])
    labels=np.full(mask.shape,UNKNOWN,np.uint16);labels[mask]=1
    annotations=project.state['annotations'].get(iid,{})
    # Explicit unknown/uncertain/exclusion override selected masks. Background outside
    # this target is NOT inferred from global layer/background annotations.
    for name,value in [('unknown',UNKNOWN),('uncertain',UNCERTAIN)]:
        labels[unpack(annotations.get(name),mask.shape)]=value
    labels[unpack(annotations.get('background'),mask.shape)&mask]=UNKNOWN
    labels[exclusion_mask(project,iid)|unpack(annotations.get('exclude'),mask.shape)]=EXCLUDED
    valid=labels==1
    return mask,labels,valid,items


def scope_reviewed(project,iid,key):
    scope,_=get_scope(project,iid,key)
    return scope.get('review_hash')==scope_hash(project,iid,key)


def confirm_scope(project,iid,key):
    scope,_=get_scope(project,iid,key);_,labels,valid,_=scope_arrays(project,iid,key)
    if not valid.any():raise ValueError('선택 집합에 유효 픽셀이 없습니다.')
    scope['review_hash']=scope_hash(project,iid,key)
    return dict(scope_id=key,candidate_ids=scope['candidate_ids'],valid_pixels=int(valid.sum()),
                unknown_pixels=int((labels==UNKNOWN).sum()),input_hash=scope['review_hash'],partial=True,
                semantics=scope['semantics'])


def require_scope_review(project,iid,key):
    if not scope_reviewed(project,iid,key):raise ValueError('부분 GT 선택 마스크를 먼저 검수 확정하세요. 입력 변경 후에는 재확정이 필요합니다.')
    return confirm_scope(project,iid,key)
