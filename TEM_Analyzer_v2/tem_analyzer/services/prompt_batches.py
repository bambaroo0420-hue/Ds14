"""Persistent, review-gated prompt transfer. Never silently use an old draft."""
import copy
import hashlib
import json
import time
import uuid
from .prompt_transfer import preview_preset
from ..preprocessing import exclusion_mask,model_input


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def transfer_input_hash(project,iid,key):
    preset=project.state.get('prompt_presets',{}).get(key)
    if not preset:raise ValueError('원본 preset이 없거나 삭제되었습니다. 다시 준비하세요.')
    source=project.image(preset['source_image']);target=project.image(iid)
    return digest(dict(preset=preset,source_sha=hashlib.sha256(source.tobytes()).hexdigest(),
                       source_exclude_sha=hashlib.sha256(exclusion_mask(project,preset['source_image']).tobytes()).hexdigest(),
                       target_shape=list(target.shape),target_sha=hashlib.sha256(target.tobytes()).hexdigest(),
                       exclude_sha=hashlib.sha256(exclusion_mask(project,iid).tobytes()).hexdigest(),
                       sam_filter=project.state['preprocessing'][iid].get('sam_filter'),
                       prompt_filter=project.state['preprocessing'][iid].get('prompt_filter')))


def prepare_transfer(project,iid,key,method):
    value=preview_preset(project,iid,key,method)
    value.update(input_hash=transfer_input_hash(project,iid,key),draft_hash=digest(value),
                 review_hash=None,prepared_at=time.time())
    project.state.setdefault('prompt_transfers',{})[iid]=value
    return value


def transfer_signature(value):
    return digest({k:v for k,v in value.items() if k not in ('review_hash','reviewed_at')})


def current_transfer(project,iid,reviewed=False):
    project.require_image(iid);value=project.state.get('prompt_transfers',{}).get(iid)
    if not value:raise ValueError('이미지별 재사용 프롬프트를 먼저 준비하세요.')
    if value.get('superseded_by'):raise ValueError('새 재사용 준비가 실패/취소됐거나 대기 중입니다. 이전 draft로 실행하지 않습니다. 다시 준비하세요.')
    if value['input_hash']!=transfer_input_hash(project,iid,value['preset_id']):raise ValueError('영상·제외 영역·SAM 전처리 또는 preset이 바뀌었습니다. 프롬프트를 다시 준비하고 검토하세요.')
    # Detect accidental/manual JSON edits to a stored draft independently of input changes.
    original={k:v for k,v in value.items() if k not in ('input_hash','draft_hash','review_hash','prepared_at','reviewed_at')}
    if value['draft_hash']!=digest(original):raise ValueError('저장된 재사용 프롬프트가 바뀌었습니다. 다시 준비하세요.')
    if reviewed and value.get('review_hash')!=transfer_signature(value):raise ValueError('이 이미지의 재사용 점·box 미리보기를 검토·확정하세요. SAM은 아직 실행하지 않았습니다.')
    return value


def confirm_transfers(project,entries):
    if not entries or len(entries)>200:raise ValueError('1~200개의 미리보기를 선택하세요.')
    values=[];seen=set()
    for entry in entries:
        iid=entry['image_id']
        if iid in seen:raise ValueError('중복 이미지 선택');
        seen.add(iid);value=current_transfer(project,iid)
        if entry.get('signature')!=transfer_signature(value):raise ValueError('미리보기가 갱신되었습니다. 현재 화면을 다시 확인하세요.')
        values.append(value)
    for value in values:value.update(review_hash=transfer_signature(value),reviewed_at=time.time())
    return {'confirmed':list(seen),'inference_run':False}


def run_transferred(project,model,iid,values):
    """Caller owns model/project locks and rollback. Existing masks are append-only."""
    from ..v2_api import save_prediction
    value=current_transfer(project,iid,reviewed=True);draft=copy.deepcopy(value['draft'])
    image=model_input(project,iid);ex=exclusion_mask(project,iid)
    auto=draft['auto_points'];manual=draft['manual_points'];box=draft['box'];items=[]
    if draft['manual_mode']=='independent':auto=auto+[p[:2] for p in manual];manual=[]
    if auto:items.extend((x,'transferred-auto') for x in model.automatic(image,pred_iou=values[0],stability=values[1],nms=values[2],exclude=ex,prepared_points=auto))
    if manual or box is not None:items.append((model.prompt(image,manual,box),'transferred-manual'))
    from .recipe_groups import infer_groups
    group_items=infer_groups(model,image,draft.get('manual_groups',[]),ex)
    run_id=uuid.uuid4().hex;provenance=dict(preset_id=value['preset_id'],source_image=value['source_image'],method=value['method'],
        matrix=value['matrix'],ecc_score=value['ecc_score'],input_hash=value['input_hash'],review_hash=value['review_hash'])
    for item,source in items:
        candidate=save_prediction(project,iid,item,source,prompts=dict(draft=draft,transfer=provenance));candidate['run_id']=run_id
    for item,group in group_items:
        candidate=save_prediction(project,iid,item,'transferred-group',prompts=dict(group,transfer=provenance));candidate['run_id']=run_id
    project.state.setdefault('prepared_prompts',{})[iid]=dict(draft,source='reviewed-transfer',transfer=provenance)
    project.state['runs'].append(dict(id=run_id,image_id=iid,stage='batch-sam-transferred',model=copy.deepcopy(model.info),
                                     transfer=provenance,filters=dict(pred_iou=values[0],stability=values[1],nms=values[2]),timestamp=time.time()))
    return dict(count=len(items)+len(group_items),status='needs_layer_review',prompt_count=len(auto)+len(manual)+sum(len(g['points']) for _,g in group_items),warnings=value['warnings'],preset_id=value['preset_id'])
