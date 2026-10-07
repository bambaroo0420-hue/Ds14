"""Canonical semantic result: active candidates + explicit annotation validity."""
import base64
import numpy as np
from .preprocessing import effective_template
from .operations import excluded
UNKNOWN,UNCERTAIN,EXCLUDED=65535,65534,65533

def pack(a):return {'shape':list(a.shape),'data':base64.b64encode(np.packbits(a.ravel()).tobytes()).decode()}
def unpack(a,shape):
    if not a:return np.zeros(shape,bool)
    if a['shape']!=list(shape):raise ValueError('저장 영역 크기 불일치')
    return np.unpackbits(np.frombuffer(base64.b64decode(a['data']),np.uint8),count=int(np.prod(shape))).reshape(shape).astype(bool)

def compose(project,iid,reviewed_only=False):
    info=project.state['images'][iid];shape=(info['height'],info['width']);labels=np.full(shape,UNKNOWN,np.uint16);conflict=np.zeros(shape,bool)
    included=[]
    for c in project.state['candidates'][iid]:
        if c.get('deleted') or not c.get('active',True) or c['layer_id'] is None:continue
        if reviewed_only and not c.get('reviewed'):continue
        included.append(c)
        m=project.mask(iid,c['id']);lid=c['layer_id']
        conflict|=m&(labels!=UNKNOWN)&(labels!=lid);labels[m]=lid
    annotations=project.state['annotations'].get(iid,{})
    for name,value in [('background',0),('unknown',UNKNOWN),('uncertain',UNCERTAIN),('exclude',EXCLUDED)]:
        m=unpack(annotations.get(name),shape);labels[m]=value;conflict[m]=False
    ex=excluded(shape,effective_template(project,iid))|unpack(annotations.get('exclude'),shape)
    labels[ex]=EXCLUDED;conflict[ex]=False
    labels[conflict]=UNCERTAIN
    from .roi_domains import crop_guard
    cut=crop_guard(project,iid,included);labels[cut&~ex]=UNKNOWN;conflict[cut]=False
    valid=(labels<EXCLUDED)&~conflict
    return labels,valid,conflict

def protection(project,iid):
    info=project.state['images'][iid];shape=(info['height'],info['width']);m=unpack(project.state['protected'].get(iid),shape)
    for c in project.state['candidates'][iid]:
        if c.get('active',True) and not c.get('deleted') and project.locked(c['layer_id']):m|=project.mask(iid,c['id'])
    return m
