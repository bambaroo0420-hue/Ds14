"""Layer unions, explicit conflict review, shared-boundary proposals and matching."""
import copy
import hashlib
import json
import numpy as np
from scipy import ndimage as ndi
from ..labels import compose, protection, unpack, EXCLUDED
from ..operations import excluded
from ..preprocessing import effective_template, model_input
from ..boundary import refine_all, topology
from ..roi_domains import crop_guard


def fingerprint(project, iid):
    project.require_image(iid)
    payload={k:project.state.get(k,{}).get(iid) for k in ('candidates','annotations','protected')}
    record=project.state.get('preprocessing',{}).get(iid,{})
    payload['preprocessing']={k:record.get(k) for k in ('sam_filter','edge_filter')}
    payload['preprocessing']['effective_regions']=effective_template(project,iid)
    payload['layers']=project.state['layers']
    payload['mask_scopes']={k:v['candidate_ids'] for k,v in project.state.get('mask_scopes',{}).get(iid,{}).items()}
    from ..roi_domains import candidate_domains
    if any(candidate_domains(c) for c in project.state['candidates'][iid]):payload['roi_cut_guard_version']=2
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def active(project,iid,lid=None):
    return [c for c in project.state['candidates'][iid] if not c.get('deleted') and c.get('active',True) and (lid is None or c['layer_id']==lid)]


def unions(project,iid,reviewed=False):
    shape=project.image(iid).shape[:2];out={}
    for c in active(project,iid):
        if c['layer_id'] is None or (reviewed and not c.get('reviewed')):continue
        out.setdefault(c['layer_id'],np.zeros(shape,bool))[:] |= project.mask(iid,c['id'])
    return out


def inspect_conflicts(project,iid,max_gap=4):
    if not 0<=max_gap<=30:raise ValueError('작은 틈 기준은 0~30 px입니다.')
    masks=unions(project,iid);order=[l['id'] for l in project.state['layers']]
    labels,valid,overlap=compose(project,iid);pairs=[]
    for i,a in enumerate(masks):
        for b in list(masks)[i+1:]:
            am,bm=masks[a],masks[b]
            if not am.any() or not bm.any():continue
            both=am&bm&(labels!=EXCLUDED)
            da=ndi.distance_transform_edt(~am);db=ndi.distance_transform_edt(~bm)
            gap=(~am&~bm)&(da+db<=max_gap+1)&(labels==65535)
            adjacent=abs(order.index(a)-order.index(b))==1
            if both.any() or gap.any() or float(da[bm].min())<=2:
                pairs.append(dict(layer_a=a,layer_b=b,adjacent=adjacent,overlap_pixels=int(both.sum()),
                                  small_gap_pixels=int(gap.sum()),requires_review=bool(both.any() or gap.any())))
    return dict(pairs=pairs,conflict_pixels=int(overlap.sum()),unknown_pixels=int((labels==65535).sum()),
                note='미지정은 배경이 아닙니다. 비인접 충돌·큰 틈은 자동으로 채우지 않습니다.')


def propose_boundaries(project,iid,settings=None,region=None):
    cfg=dict(settings or {});radius=float(cfg.get('radius',8));gap=float(cfg.get('max_gap',0))
    if not 1<=radius<=50 or not 0<=gap<=30:raise ValueError('경계 폭 1~50 px, 허용 틈 0~30 px')
    masks=unions(project,iid);result={k:v.copy() for k,v in masks.items()}
    report=inspect_conflicts(project,iid,gap);guard=protection(project,iid)
    labels,_,_=compose(project,iid);guard |= labels==EXCLUDED
    guard |= crop_guard(project,iid,[c for c in active(project,iid) if c['layer_id'] is not None])
    # Explicit user labels override automated correction, including explicit unknown.
    for value in project.state['annotations'].get(iid,{}).values():guard |= unpack(value,guard.shape)
    if region:
        if len(region)!=4 or not (0<=region[0]<region[2]<=1 and 0<=region[1]<region[3]<=1):raise ValueError('부분 보정 box는 0~1 정규화 좌표입니다.')
        h,w=guard.shape;x0,y0,x1,y1=(np.array(region)*[w,h,w,h]).astype(int)
        keep=np.zeros_like(guard);keep[y0:y1,x0:x1]=True;guard |= ~keep
    reports=[];rgb=model_input(project,iid,'edge')
    blocked=set()
    for pair in report['pairs']:
        if not pair['adjacent'] and pair['overlap_pixels']:blocked.update([pair['layer_a'],pair['layer_b']])
    for pair in report['pairs']:
        a,b=pair['layer_a'],pair['layer_b'];entry=dict(pair)
        if not pair['adjacent'] or a in blocked or b in blocked or project.locked(a) or project.locked(b):
            entry.update(status='manual_review',reason='비인접 충돌 또는 잠긴 레이어');reports.append(entry);continue
        am,bm=result[a].copy(),result[b].copy()
        da=ndi.distance_transform_edt(~am);db=ndi.distance_transform_edt(~bm)
        others=np.zeros_like(am)
        for k,m in result.items():
            if k not in (a,b):others|=m
        eligible=~guard&~others&(((am|bm)&(da<=radius+1)&(db<=radius+1)) | ((~am&~bm)&(da+db<=gap+1)))
        # Resolve only a narrow overlap: signed distances retain both layer interiors.
        overlap=am&bm
        if overlap.any() and ndi.distance_transform_edt(overlap).max()>radius:
            entry.update(status='manual_review',reason='겹침이 자동 허용 폭보다 큽니다.');reports.append(entry);continue
        signed_a=ndi.distance_transform_edt(am)-da;signed_b=ndi.distance_transform_edt(bm)-db
        ambiguous=eligible&((am&bm)|(~am&~bm))
        initial=am.copy();initial[ambiguous]=signed_a[ambiguous]>=signed_b[ambiguous]
        init_b=bm.copy();init_b[ambiguous]=~initial[ambiguous]
        if not initial.any() or not init_b.any():
            entry.update(status='manual_review',reason='보정 후 레이어 소실');reports.append(entry);continue
        settings_dp={'inside':radius,'outside':radius,'smooth':float(cfg.get('smooth',.18)),
                     'distance':float(cfg.get('distance',.3)),'jump':int(cfg.get('jump',4)),
                     'polarity':cfg.get('polarity','both'),'weak':float(cfg.get('weak',.15))}
        proposal=refine_all(rgb,initial,~guard,settings_dp)
        new_a=am.copy();new_b=bm.copy()
        new_a[eligible]=proposal['mask'][eligible];new_b[eligible]=~new_a[eligible]
        # Bounds include initial overlap/gap cleanup as well as the gradient movement.
        edge_a=am^ndi.binary_erosion(am);edge_b=bm^ndi.binary_erosion(bm)
        close=(ndi.distance_transform_edt(~edge_a)<=radius+1)&(ndi.distance_transform_edt(~edge_b)<=radius+1)
        new_a[~close]=am[~close];new_b[~close]=bm[~close]
        if topology(new_a)!=topology(am) or topology(new_b)!=topology(bm):
            entry.update(status='manual_review',reason='연결 구조 변화');reports.append(entry);continue
        result[a],result[b]=new_a,new_b
        entry.update(status='proposed',changed_pixels=int(((new_a!=am)|(new_b!=bm)).sum()),
                     flags=[f for loop in proposal['loops'] for f in loop['quality']['flags']])
        reports.append(entry)
    return dict(masks=result,reports=reports,input_hash=fingerprint(project,iid),settings=cfg,
                changed_pixels=sum(int((result[k]!=masks[k]).sum()) for k in masks))


def apply_boundaries(project,iid,proposal):
    if proposal['input_hash']!=fingerprint(project,iid):raise ValueError('입력이 변경되었습니다. 경계를 다시 제안하세요.')
    created=[]
    for lid,new_union in proposal['masks'].items():
        candidates=active(project,iid,lid)
        old_masks=[project.mask(iid,c['id']) for c in candidates]
        if not old_masks or np.array_equal(np.logical_or.reduce(old_masks),new_union):continue
        # Preserve each object's identity, partitioning only new union pixels by nearest old object.
        distances=np.stack([ndi.distance_transform_edt(~m) for m in old_masks])
        owner=np.argmin(distances,axis=0)
        for i,(old,m) in enumerate(zip(candidates,old_masks)):
            project.assert_editable(old);new=new_union&(owner==i)
            c=project.put_candidate(iid,new,'layer-boundary',parent=old['id'],prompts={'settings':proposal['settings']})
            c.update(layer_id=lid,instance_id=old.get('instance_id'),reviewed=False)
            old.update(active=False,reviewed=False);created.append(c)
    return dict(created=created,reports=proposal['reports'],changed_pixels=proposal['changed_pixels'])


def transfer_layers(project,reference,target,threshold=.5):
    if reference==target:raise ValueError('기준 이미지와 대상 이미지는 달라야 합니다.')
    if not 0<=threshold<=1:raise ValueError('대응 허용값은 0~1입니다.')
    from PIL import Image
    ref=unions(project,reference,reviewed=True)
    if not ref:raise ValueError('기준 이미지에서 레이어를 먼저 검수 확정하세요.')
    shape=project.image(target).shape[:2];scaled={k:np.array(Image.fromarray(v).resize((shape[1],shape[0]),Image.Resampling.NEAREST),bool) for k,v in ref.items()}
    proposals=[]
    for c in active(project,target):
        if c['layer_id'] is not None:continue
        m=project.mask(target,c['id']);scores=[]
        for lid,r in scaled.items():
            overlap=int((m&r).sum());score=overlap/max(int(m.sum()),1)
            scores.append((score,lid))
        scores.sort(reverse=True)
        score,lid=scores[0];margin=score-(scores[1][0] if len(scores)>1 else 0)
        assigned=score>=threshold and margin>=.15 and not project.locked(lid)
        c['layer_suggestion']={'layer_id':lid,'score':score,'margin':margin,'reference':reference}
        if assigned:c.update(layer_id=lid,reviewed=False)
        proposals.append(dict(candidate_id=c['id'],layer_id=lid,score=score,status='assigned_unreviewed' if assigned else 'needs_review'))
    return {'proposals':proposals,'method':'normalized spatial overlap; not material classification'}
