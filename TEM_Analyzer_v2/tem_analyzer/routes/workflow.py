"""TEM v2.1 layer workflow, alignment, measurement and batch API."""
import copy
import csv
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
import numpy as np
from fastapi import HTTPException
from fastapi.responses import Response
from ..algorithms.annotations import propose_annotations
from ..algorithms.metrology import warp
from ..services.layers import active, unions, fingerprint, inspect_conflicts, propose_boundaries, apply_boundaries, transfer_layers
from ..services.measurement import alignment, alignment_current, run_measurement, measurement_hash
from ..services.scopes import save_scope, confirm_scope, require_scope_review, scope_arrays
from ..services.prompt_transfer import save_preset, preview_preset
from ..services.prompt_batches import prepare_transfer,run_transferred
from ..labels import compose, EXCLUDED
from ..preprocessing import model_input, restrict_mask, exclusion_mask
from ..jobs.manager import JobManager


def install(app,project,model,model_lock,gate):
    from ..v2_api import image_bytes,export_bytes,save_prediction
    proposals={}
    for key in ('alignments','measurements','annotation_proposals','gt_reviews'):
        project.state.setdefault(key,{})
    # Migrate previews applied by early v2.1 builds without enabling old fixed boxes.
    for iid,record in project.state['preprocessing'].items():
        old=project.state['annotation_proposals'].get(iid,{})
        if old.get('template') and record.get('template')==old['template'] and 'auto_regions' not in record:
            record['auto_regions']=copy.deepcopy(old['template'])
            record['template']={'scale_roi':None,'text_rois':[]}

    def detect(iid,settings):
        from ..ocr import read_words
        image=project.image(iid)
        words=read_words(image,settings.get('ocr_dir','models/easyocr'),settings.get('language','en'),enhanced=bool(settings.get('enhanced_ocr',True)))
        proposal=propose_annotations(image,words)
        proposal['input_hash']=fingerprint(project,iid)
        project.state['annotation_proposals'][iid]=proposal
        return proposal

    def apply_annotations(iid,proposal):
        if proposal.get('input_hash')!=fingerprint(project,iid):raise ValueError('검출 후 입력이 바뀌었습니다. 다시 검출하세요.')
        project.state['preprocessing'][iid].update(auto_regions=copy.deepcopy(proposal['template']),regions_applied=True,
            reviewed=False,scale_requested=True,scale_status='proposed' if proposal['scale'].get('nm_per_px') else 'failed')
        # Failed detection must not leave an old confirmed calibration usable.
        project.state['scale'][iid]=copy.deepcopy(proposal['scale'])
        project.state['preprocessing'][iid]['excluded_pixels']=int(exclusion_mask(project,iid).sum())
        project.invalidate(iid,'자동 제외 영역 적용')
        return {'regions':len(proposal['regions']),'scale':project.state['scale'][iid]}

    def require_gt(iid,scope_id=None):
        if scope_id:return require_scope_review(project,iid,scope_id)
        assigned=[c for c in active(project,iid) if c['layer_id'] is not None]
        if not assigned or any(not c.get('reviewed') for c in assigned):raise ValueError('배정된 모든 활성 마스크를 검수 확정하세요. 미지정 후보는 유지할 수 있습니다.')
        labels,valid,conflict=compose(project,iid)
        if conflict.any():raise ValueError('겹침을 먼저 해결하세요. 불확실·제외 상태로 명시할 수도 있습니다.')
        return dict(valid_pixels=int(valid.sum()),unknown_pixels=int((labels==65535).sum()),input_hash=fingerprint(project,iid))

    def execute(iid,stage,settings):
        if stage=='prompt_transfer':
            cfg=settings.get('prompt_transfer',{});value=prepare_transfer(project,iid,cfg.get('preset_id',''),cfg.get('method','normalized'))
            return dict(status='needs_prompt_review',preset_id=value['preset_id'],ecc_score=value['ecc_score'],inference_run=False,
                        prompt_count=len(value['draft']['auto_points'])+len(value['draft']['manual_points']),warnings=value['warnings'])
        if stage=='annotations':
            proposal=detect(iid,settings)
            if settings.get('apply_annotations'):apply_annotations(iid,proposal)
            return {'regions':len(proposal['regions']),'status':'needs_review','nm_per_px':proposal['scale'].get('nm_per_px')}
        if stage=='sam':
            if not model_lock.acquire(blocking=False):raise ValueError('모델 작업 중입니다.')
            try:
                image=model_input(project,iid);cfg=settings.get('sam',{})
                grid=int(cfg.get('grid',8))
                if not 2<=grid<=32:raise ValueError('Grid 범위 2~32')
                values=[float(cfg.get('pred_iou',.9)),float(cfg.get('stability',.92)),float(cfg.get('nms',.8))]
                if not all(np.isfinite(v) and 0<=v<=1 for v in values):raise ValueError('SAM 필터 값은 0~1입니다.')
                source=cfg.get('prompt_source','grid');prepared=None;proposal=None
                if source=='transferred':return run_transferred(project,model,iid,values)
                if source not in ('grid','features','grid_features'):raise ValueError('일괄 프롬프트 방식 오류')
                if source!='grid':
                    from ..prompts import grid_points
                    from ..feature_prompts import propose
                    ex=exclusion_mask(project,iid)
                    prepared=grid_points(image.shape[:2],grid,ex) if source=='grid_features' else []
                    proposal=propose(model_input(project,iid,'prompt'),ex,prepared,cfg.get('features'))
                    prepared+=proposal['points']
                    if not prepared:raise ValueError('생성된 프롬프트가 없습니다. 임계값/간격을 조정하세요.')
                items=model.automatic(image,grid,*values,exclusion_mask(project,iid),**({'prepared_points':prepared} if prepared is not None else {}))
                run_id=uuid.uuid4().hex
                project.state['runs'].append(dict(id=run_id,image_id=iid,stage='batch-sam',model=copy.deepcopy(model.info),settings=cfg,timestamp=time.time()))
                for item in items:
                    c=save_prediction(project,iid,item,'batch-sam');c['run_id']=run_id
                if proposal:project.state.setdefault('prepared_prompts',{})[iid]={'auto_points':prepared,'settings':proposal['settings'],'source':'batch-features'}
                return {'count':len(items),'status':'needs_layer_review','prompt_count':len(prepared) if prepared is not None else None,'warnings':proposal['warnings'] if proposal else []}
            finally:model_lock.release()
        if stage=='match':return transfer_layers(project,settings.get('reference_image'),iid,float(settings.get('match_threshold',.5)))
        if stage=='boundary':
            p=propose_boundaries(project,iid,settings.get('boundary'),settings.get('boundary_roi'))
            result=apply_boundaries(project,iid,p)
            return {'changed_pixels':result['changed_pixels'],'reports':result['reports'],'status':'needs_review'}
        if stage=='rotation':
            value=alignment(project,iid,settings.get('rotation',{}));project.state['alignments'][iid]=value
            return {'angle_deg':value['transform']['angle_deg'],'needs_review':True}
        if stage=='measurement':
            value=run_measurement(project,iid,settings.get('measurement',{}));project.state['measurements'][iid]=value
            return value['summary']
        if stage=='gt':
            review=require_gt(iid,settings.get('scope_id'));project.state['gt_reviews'][iid]=review
            return review
        raise ValueError('지원하지 않는 작업')

    manager=JobManager(project,gate,execute)
    app.state.workflow_jobs=manager

    @app.get('/api/workflow/status/{iid}')
    def status(iid:str):
        project.require_image(iid);rot=project.state['alignments'].get(iid);met=project.state['measurements'].get(iid)
        return dict(rotation=rot,measurement=met,rotation_stale=bool(rot and rot['input_hash']!=fingerprint(project,iid)),
                    measurement_stale=bool(met and met['input_hash']!=measurement_hash(project,iid)),conflicts=inspect_conflicts(project,iid))

    @app.post('/api/workflow/annotations/detect')
    def annotations_detect(body:dict):return detect(body['image_id'],body)

    @app.post('/api/workflow/templates/enabled')
    def templates_enabled(body:dict):
        enabled=body.get('enabled')
        if not isinstance(enabled,bool):raise ValueError('enabled는 true/false입니다.')
        if project.state.get('legacy_templates_enabled',False)!=enabled:
            project.state['legacy_templates_enabled']=enabled
            for iid in project.state['images']:project.invalidate(iid,'기존 위치 템플릿 활성 상태 변경')
        return {'enabled':enabled}

    @app.post('/api/workflow/annotations/apply')
    def annotations_apply(body:dict):
        iid=body['image_id'];p=project.state['annotation_proposals'].get(iid)
        if not p:raise ValueError('자동 검출을 먼저 실행하세요.')
        if 'region_indices' in body:
            indices=body['region_indices']
            if any(not isinstance(i,int) or not 0<=i<len(p['regions']) for i in indices):raise ValueError('제외 박스 선택 오류')
            p=copy.deepcopy(p);selected=[p['regions'][i] for i in sorted(set(indices))]
            p['template']={'scale_roi':next((r['roi'] for r in selected if r['kind']=='scale'),None),'text_rois':[r['roi'] for r in selected if r['kind']!='scale']}
            p['regions']=selected
        return apply_annotations(iid,p)

    @app.get('/api/workflow/annotations/{iid}.png')
    def annotations_preview(iid:str):
        from PIL import Image,ImageDraw
        proposal=project.state['annotation_proposals'].get(iid)
        if not proposal:raise ValueError('자동 검출을 먼저 실행하세요.')
        im=Image.fromarray(project.image(iid));draw=ImageDraw.Draw(im)
        for i,r in enumerate(proposal['regions']):
            draw.rectangle(r['box'],outline='#ff5577',width=2);draw.text((r['box'][0],r['box'][1]),str(i+1),fill='yellow')
        return Response(image_bytes(np.array(im)),media_type='image/png')

    @app.post('/api/workflow/masks/bulk')
    def masks_bulk(body:dict):
        iid=body['image_id'];project.require_image(iid);ids=list(dict.fromkeys(map(int,body.get('candidate_ids',[]))))
        if not ids:raise ValueError('마스크를 선택하세요.')
        items=[project.candidate(iid,cid) for cid in ids]
        if any(c is None or not c.get('active',True) for c in items):raise ValueError('선택한 활성 마스크를 찾을 수 없습니다.')
        for c in items:project.assert_editable(c)
        action=body['action']
        if action=='assign':
            lid=int(body['layer_id'])
            if lid not in [l['id'] for l in project.state['layers']] or project.locked(lid):raise ValueError('대상 레이어가 없거나 잠겨 있습니다.')
            for c in items:c.update(layer_id=lid,reviewed=False)
        elif action=='unassign':
            for c in items:c.update(layer_id=None,reviewed=False)
        elif action=='delete':
            for c in items:c.update(deleted=True,active=False,reviewed=False)
        elif action=='review':
            if any(c['layer_id'] is None for c in items):raise ValueError('레이어에 배정된 마스크만 검수 확정할 수 있습니다.')
            _,_,conflict=compose(project,iid)
            if any((project.mask(iid,c['id'])&conflict).any() for c in items):raise ValueError('선택 마스크에 겹침이 있습니다. 먼저 해결하세요.')
            for c in items:c.update(reviewed=True)
        else:raise ValueError('지원하지 않는 일괄 편집')
        return {'count':len(items),'action':action}

    @app.post('/api/workflow/scopes/save')
    def scopes_save(body:dict):
        return save_scope(project,body['image_id'],body.get('scope_id','target'),body.get('candidate_ids',[]),body.get('name','분석 대상'))

    @app.post('/api/workflow/prompt-presets/save')
    def preset_save(body:dict):
        return save_preset(project,body['image_id'],body['preset_id'],body['draft'])

    @app.post('/api/workflow/prompt-presets/preview')
    def preset_preview(body:dict):
        return preview_preset(project,body['image_id'],body['preset_id'],body.get('method','normalized'))

    @app.post('/api/workflow/scopes/confirm')
    def scopes_confirm(body:dict):
        return confirm_scope(project,body['image_id'],body.get('scope_id','target'))

    @app.get('/api/workflow/scopes/{iid}/{key}.png')
    def scopes_preview(iid:str,key:str):
        _,_,valid,_=scope_arrays(project,iid,key);rgb=project.image(iid).astype(float)
        rgb[valid]=rgb[valid]*.5+np.array([30,230,150])*.5
        return Response(image_bytes(rgb.astype('uint8')),media_type='image/png')

    @app.post('/api/workflow/layers/order')
    def layer_order(body:dict):
        ids=body['layer_ids'];existing={l['id']:l for l in project.state['layers']}
        if len(ids)!=len(set(ids)) or set(ids)!=set(existing):raise ValueError('모든 레이어 ID를 순서대로 지정하세요.')
        project.state['layers']=[existing[i] for i in ids]
        return {'layer_ids':ids}

    @app.post('/api/workflow/layers/match')
    def match(body:dict):return transfer_layers(project,body['reference_image'],body['image_id'],float(body.get('threshold',.5)))

    @app.get('/api/workflow/conflicts/{iid}')
    def conflicts(iid:str,max_gap:float=4):return inspect_conflicts(project,iid,max_gap)

    @app.post('/api/workflow/boundary/preview')
    def boundary_preview(body:dict):
        iid=body['image_id'];p=propose_boundaries(project,iid,body.get('settings'),body.get('roi'));token=uuid.uuid4().hex
        proposals.clear();proposals[token]=(iid,p)
        return dict(token=token,reports=p['reports'],changed_pixels=p['changed_pixels'])

    @app.get('/api/workflow/boundary/{token}.png')
    def boundary_image(token:str):
        if token not in proposals:raise ValueError('미리보기가 만료되었습니다.')
        iid,p=proposals[token];rgb=project.image(iid).astype(float)
        for layer in project.state['layers']:
            if layer['id'] in p['masks']:
                mask=p['masks'][layer['id']];color=np.array(list(bytes.fromhex(layer['color'][1:])))
                rgb[mask]=rgb[mask]*.5+color*.5
        return Response(image_bytes(rgb.astype('uint8')),media_type='image/png')

    @app.post('/api/workflow/boundary/apply')
    def boundary_apply(body:dict):
        if body['token'] not in proposals:raise ValueError('미리보기가 만료되었습니다.')
        iid,p=proposals[body['token']];value=apply_boundaries(project,iid,p);proposals.clear();return value

    @app.post('/api/workflow/rotation/preview')
    def rotation_preview(body:dict):
        iid=body['image_id'];value=alignment(project,iid,body['config']);project.state['alignments'][iid]=value
        return value

    @app.post('/api/workflow/rotation/confirm')
    def rotation_confirm(body:dict):
        value=alignment_current(project,body['image_id']);value['confirmed']=True;return value

    @app.post('/api/workflow/confirm-many')
    def confirm_many(body:dict):
        ids=list(dict.fromkeys(body['image_ids']));kind=body['kind'];values=[]
        if not ids:raise ValueError('이미지를 선택하세요.')
        for iid in ids:
            project.require_image(iid)
            if kind=='rotation':values.append(alignment_current(project,iid))
            elif kind=='scale':
                s=project.state['scale'].get(iid,{})
                if not s.get('nm_per_px') or project.state['preprocessing'][iid].get('scale_status') in ('failed','error'):raise ValueError('검출 실패가 포함되어 있습니다. 실패 항목을 제외하세요.')
                values.append(s)
            else:raise ValueError('확정 종류는 scale/rotation입니다.')
        for v in values:v['confirmed']=True
        return {'confirmed':ids,'kind':kind}

    @app.get('/api/workflow/rotation/{iid}.png')
    def aligned_image(iid:str):
        value=alignment_current(project,iid)
        image=warp(project.image(iid),value['transform'],1)
        return Response(image_bytes(image),media_type='image/png')

    @app.post('/api/workflow/measurement')
    def measurement(body:dict):
        iid=body['image_id'];value=run_measurement(project,iid,body['config']);project.state['measurements'][iid]=value;return value

    @app.post('/api/workflow/gt/confirm')
    def gt_confirm(body:dict):
        iid=body['image_id'];review=require_gt(iid,body.get('scope_id'));project.state['gt_reviews'][iid]=review;return review

    def result_zip(ids,include_gt=False,scope_id=None):
        output=io.BytesIO();csvbuf=io.StringIO();writer=csv.writer(csvbuf)
        writer.writerow(['image_id','image_name','layer_id','scope_id','axis','position_px','segment','status','length_px','length_nm','review_status','component_id','raw_length_nm','quality_flags','exclusion_reasons','valid_coverage_px','invalid_coverage_px'])
        # Validate every item before producing any successful-looking partial export.
        for iid in ids:
            project.require_image(iid)
            if scope_id:scope_arrays(project,iid,scope_id)
            if include_gt:require_gt(iid,scope_id)
            if not include_gt and not project.state['alignments'].get(iid):raise ValueError('먼저 회전 결과를 생성하세요. GT는 별도 내보내기입니다.')
            if project.state['alignments'].get(iid):alignment_current(project,iid)
            met=project.state['measurements'].get(iid)
            if met and met.get('scope_id')!=scope_id:raise ValueError('계측 결과의 선택 범위와 출력 범위가 다릅니다. 같은 범위로 다시 측정하거나 출력하세요.')
            if met and met['input_hash']!=measurement_hash(project,iid):raise ValueError('만료된 계측 결과가 있습니다. 다시 측정하세요.')
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('export_mode.json',json.dumps({'include_gt':include_gt,'scope_id':scope_id,'partial_binary_target':bool(scope_id),'note':'Selected scope label 1 is a binary target union, not a semantic material class. Unselected is UNKNOWN, never background. Provisional measurements retain review_status.'}))
            for iid in ids:
                if include_gt:
                    if scope_id:
                        _,sl,sv,items=scope_arrays(project,iid,scope_id)
                        z.writestr(iid+'/partial_gt/labels.png',image_bytes(sl))
                        z.writestr(iid+'/partial_gt/valid.png',image_bytes(sv.astype('uint8')*255))
                        z.writestr(iid+'/partial_gt/metadata.json',json.dumps(dict(require_gt(iid,scope_id),label_codes={'target':1,'unknown':65535,'uncertain':65534,'excluded':65533},image=project.state['images'][iid]),ensure_ascii=False,indent=2))
                    else:z.writestr(iid+'/gt.zip',export_bytes(project,iid))
                met=project.state['measurements'].get(iid)
                rot=project.state['alignments'].get(iid)
                if rot and rot['input_hash']==fingerprint(project,iid):
                    if scope_id:_,labels,valid,_=scope_arrays(project,iid,scope_id)
                    else:labels,valid,_=compose(project,iid,reviewed_only=include_gt)
                    z.writestr(iid+'/aligned_image.png',image_bytes(warp(project.image(iid),rot['transform'],1)))
                    z.writestr(iid+'/aligned_labels.png',image_bytes(warp(labels,rot['transform'],0,EXCLUDED)))
                    z.writestr(iid+'/aligned_valid.png',image_bytes(warp(valid.astype('uint8')*255,rot['transform'],0)))
                    z.writestr(iid+'/alignment.json',json.dumps(rot,ensure_ascii=False,indent=2))
                if met:
                    z.writestr(iid+'/measurement.json',json.dumps(met,ensure_ascii=False,indent=2))
                    for row in met['rows']:
                        name=project.state['images'][iid]['name']
                        if name.startswith(('=','+','-','@')):name="'"+name
                        writer.writerow([iid,name,met['layer_id'],met.get('scope_id'),met['axis'],row['position_px'],row.get('segment'),row['status'],row.get('length_px'),row.get('length_nm'),met.get('review_status','unknown'),row.get('component_id'),row.get('raw_length_nm'),'|'.join(row.get('quality_flags',[])),'|'.join(row.get('exclusion_reasons',[])),row.get('valid_coverage_px'),row.get('invalid_coverage_px')])
            z.writestr('measurements.csv','\ufeff'+csvbuf.getvalue())
        return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="TEM_results.zip"'})

    @app.post('/api/workflow/export')
    def export(body:dict):
        ids=body.get('image_ids') or list(project.state['images'])
        if not ids:raise ValueError('출력할 이미지가 없습니다.')
        return result_zip(ids,bool(body.get('include_gt',False)),body.get('scope_id'))

    @app.get('/api/workflow/trash')
    def trash():
        values=[]
        for path in (project.root/'trash').glob('*/journal.json'):
            item=json.loads(path.read_text(encoding='utf8'))
            if item['image_id'] not in project.state['images'] and item.get('metadata'):
                values.append(dict(id=path.parent.name,image_id=item['image_id'],name=item['metadata']['images']['name'],created=item.get('created',0)))
        return sorted(values,key=lambda x:x['created'],reverse=True)

    @app.post('/api/workflow/trash/restore')
    def restore(body:dict):return {'image_id':project.restore_deleted(body['trash_id'])}

    @app.get('/api/workflow/jobs')
    async def jobs():return copy.deepcopy(project.state.get('jobs',[]))

    @app.post('/api/workflow/jobs/start')
    async def start_job(body:dict):
        try:
            async with gate:return manager.start(body.get('image_ids') or list(project.state['images']),body.get('steps',[]),body.get('settings',{}))
        except (ValueError,KeyError) as e:raise HTTPException(400,str(e))

    @app.post('/api/workflow/jobs/cancel')
    async def cancel_job():return manager.cancel()

    @app.post('/api/workflow/jobs/retry')
    async def retry_job(body:dict):
        try:
            old=next(j for j in project.state['jobs'] if j['id']==body['job_id'])
            ids=list(dict.fromkeys(r['image_id'] for r in old['rows'] if r['status']=='failed'))
            if not ids:raise ValueError('실패한 이미지가 없습니다.')
            # Failed step only: never duplicate a successful SAM stage when retrying later stages.
            stages={r['stage'] for r in old['rows'] if r['status']=='failed'}
            if len(stages)!=1:raise ValueError('실패 단계가 다릅니다. 단계별로 실패 이미지를 선택해 재실행하세요.')
            stage=next(iter(stages));remaining=old['steps'][old['steps'].index(stage):]
            async with gate:return manager.start(ids,remaining,old['settings'])
        except (ValueError,KeyError,StopIteration) as e:raise HTTPException(400,str(e))

    from .prompt_batches import install as install_prompt_batches
    install_prompt_batches(app,project)
    return manager
