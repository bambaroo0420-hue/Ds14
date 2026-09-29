"""Version 2 transactions, review tools and reproducible training exports."""
import asyncio,copy,io,json,time,uuid,zipfile,csv,hashlib
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from fastapi import HTTPException,Request
from fastapi.responses import JSONResponse,Response
from .preprocessing import model_input,restrict_mask,filtered,effective_template
from .operations import brush,excluded,roi_pixels,detect_scale,scale_from_points
from .labels import compose,pack,unpack,protection,UNKNOWN,UNCERTAIN,EXCLUDED
from .boundary import refine_all,topology


def load_prior(project,iid,c):
    prior={'mask':project.mask(iid,c['id'])}
    path=project.root/'logits'/f"{iid}_{c['id']}.npy"
    if path.exists() and c.get('logits_context'):
        prior.update(logits=np.load(path,allow_pickle=False),context=c['logits_context'])
    return prior


def save_prediction(project,iid,item,source,parent=None,prompts=None):
    c=project.put_candidate(iid,restrict_mask(project,iid,item['mask']),source,float(item['score']) if item.get('score') is not None else None,parent,prompts,inference_domains=item.get('inference_domains',[]))
    if item.get('logits') is not None and item.get('context'):
        np.save(project.root/'logits'/f"{iid}_{c['id']}.npy",item['logits'],allow_pickle=False);c['logits_context']=item['context']
    for key in ('prior_source','embedding_reused','mask_choice','multimask_scores','prompt_violations','roi_alignment'):
        if key in item:c[key]=item[key]
    project.save();return c


def delete_many(project,ids):
    deleted=[];failed={}
    for iid in dict.fromkeys(ids):
        try:project.delete_image(iid);deleted.append(iid)
        except (KeyError,OSError) as e:failed[iid]=str(e)
    return {'deleted':deleted,'failed':failed,'count':len(deleted)}


def image_bytes(a):
    out=io.BytesIO();Image.fromarray(a).save(out,format='PNG');return out.getvalue()


def export_bytes(project,iid):
    labels,valid,conflict=compose(project,iid,reviewed_only=True)
    # Only boundaries between valid labels are supervised; unknowns are not background.
    edges=np.zeros(labels.shape,bool)
    for axis in (0,1):
        a=[slice(None)]*2;b=a.copy();a[axis]=slice(1,None);b[axis]=slice(None,-1)
        a,b=tuple(a),tuple(b);diff=(labels[a]!=labels[b])&valid[a]&valid[b];edges[a]|=diff;edges[b]|=diff
    edges=ndi.binary_dilation(edges,iterations=1)&valid
    semantic=labels.copy();semantic[~valid]=0
    lab_mask=labels.copy();lab_mask[~valid]=UNKNOWN
    centers=np.zeros(labels.shape,np.uint8)
    for lid in np.unique(labels[valid]):
        if lid==0:continue
        comps,n=ndi.label((labels==lid)&valid)
        for k in range(1,n+1):
            dist=ndi.distance_transform_edt(comps==k);center=np.unravel_index(int(dist.argmax()),dist.shape);centers[center]=255
    meta={'schema':2,'image_id':iid,'image':project.state['images'][iid],'revision':project.state['revision'],'scale':project.state['scale'].get(iid),'preprocessing':project.state['preprocessing'].get(iid),'classes':project.state['layers'],'label_codes':{'background':0,'unknown':UNKNOWN,'uncertain':UNCERTAIN,'excluded':EXCLUDED},'contract':'semantic invalid pixels are 0; ALWAYS apply valid.png. Only reviewed active candidates included. center.png is one distance-maximum point per class component. lab_mask.png collapses all invalid labels to 65535; TEM SAM Lab ignore_label must be 65535.','runs':project.state['runs'],'conflict_pixels':int(conflict.sum()),'candidates':[c for c in project.state['candidates'][iid] if c.get('active',True) and not c.get('deleted')]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,a in [('image',project.image(iid)),('labels',labels),('semantic',semantic),('lab_mask',lab_mask),('valid',valid.astype('uint8')*255),('edge',edges.astype('uint8')*255),('center',centers)]:z.writestr(name+'.png',image_bytes(a))
        z.writestr('metadata.json',json.dumps(meta,ensure_ascii=False,indent=2))
    return out.getvalue()


def metric(pred,truth,valid,tolerance=2.):
    p=np.asarray(pred,bool)&valid;t=np.asarray(truth,bool)&valid
    inter=int((p&t).sum());union=int((p|t).sum());total=int(p.sum()+t.sum())
    safe=ndi.binary_erosion(valid,border_value=0)
    pe=(p&~ndi.binary_erosion(p))&safe;te=(t&~ndi.binary_erosion(t))&safe
    if pe.any() and te.any():
        dp=ndi.distance_transform_edt(~pe);dt=ndi.distance_transform_edt(~te)
        precision=float((dt[pe]<=tolerance).mean());recall=float((dp[te]<=tolerance).mean());f1=2*precision*recall/(precision+recall) if precision+recall else 0.
        distance=float((dt[pe].sum()+dp[te].sum())/(pe.sum()+te.sum()))
    else:f1=1. if not pe.any() and not te.any() else 0.;distance=None
    return dict(iou=inter/union if union else 1.,dice=2*inter/total if total else 1.,boundary_f1=f1,mean_boundary_distance_px=distance,valid_pixels=int(valid.sum()),tolerance_px=tolerance)


def install(app,project,model,model_lock):
    gate=asyncio.Lock();previews={}
    @app.middleware('http')
    async def transaction(request:Request,call_next):
        if not request.url.path.startswith('/api/'):return await call_next(request)
        if request.url.path.startswith('/api/workflow/jobs'):return await call_next(request)
        if getattr(project,'busy_job',False) and request.method in ('POST','DELETE','PUT','PATCH'):
            return JSONResponse({'detail':'일괄 작업 중입니다. 취소 또는 완료 후 편집하세요.'},status_code=409)
        async with gate:
            path=request.url.path;mutating=request.method in ('POST','DELETE','PUT','PATCH')
            if getattr(project,'busy_job',False) and mutating:return JSONResponse({'detail':'일괄 작업 중에는 편집할 수 없습니다.'},status_code=409)
            transactional=mutating and not (path.startswith('/api/images') or path in ('/api/model/load','/api/v2/delete','/api/v2/undo','/api/v2/redo') or path.startswith('/api/prompts/') or path.startswith('/api/v2/boundary/preview') or path.startswith('/api/v2/evaluate') or path.startswith('/api/v2/boundary/cancel'))
            before=copy.deepcopy(project.state) if transactional else None;start=time.perf_counter()
            body={}
            if mutating and 'application/json' in request.headers.get('content-type',''):
                try:body=await request.json()
                except Exception:pass
            if (path=='/api/sam/prompt' and body.get('preview')) or (path.startswith('/api/roi-previews/') and request.method=='DELETE'):transactional=False;before=None
            if transactional:project.checkpoint(path)
            try:
                response=await call_next(request)
                if transactional and response.status_code>=400:project.state=before;project.save()
                elif transactional:
                    if path.startswith('/api/sam/'):
                        run={'id':uuid.uuid4().hex,'endpoint':path,'inputs':body,'seconds':time.perf_counter()-start,'model':copy.deepcopy(model.info),'preprocessing':copy.deepcopy(project.state['preprocessing'].get(body.get('image_id'))),'timestamp':time.time()}
                        project.state['runs'].append(run)
                        for c in project.state['candidates'].get(body.get('image_id'),[]):
                            if c['id']>=before['next_candidate']:c['run_id']=run['id']
                        iid=body.get('image_id')
                        if iid in project.state['images']:run['image_sha256']=hashlib.sha256(project.image(iid).tobytes()).hexdigest()
                    project.save()
                return response
            except Exception as e:
                if transactional:project.state=before;project.save()
                if isinstance(e,(ValueError,KeyError,OSError)):return JSONResponse({'detail':str(e)},status_code=400)
                raise

    @app.post('/api/v2/undo')
    def undo():return project.undo()
    @app.post('/api/v2/redo')
    def redo():return project.undo(True)
    @app.post('/api/v2/delete')
    def delete(body:dict):return delete_many(project,body.get('image_ids',[]))
    @app.post('/api/v2/filters')
    def filters(body:dict):
        iid=body['image_id'];project.require_image(iid)
        branch=body['branch']
        if branch not in ('sam','edge'):raise ValueError('필터 분기 오류')
        cfg=body['config'];filtered(np.zeros((2,2,3),np.uint8),cfg)
        project.state['preprocessing'][iid][branch+'_filter']=cfg
        if branch=='sam':project.invalidate(iid,'SAM 전처리 변경')
        return {'ok':True}
    @app.get('/api/v2/filter/{iid}/{branch}.png')
    def filter_preview(iid:str,branch:str):
        if branch not in ('sam','edge'):raise ValueError('필터 분기 오류')
        return Response(image_bytes(model_input(project,iid,branch)),media_type='image/png')
    @app.post('/api/v2/lock')
    def lock(body:dict):
        layer=next((x for x in project.state['layers'] if x['id']==body['layer_id']),None)
        if layer is None:raise ValueError('레이어가 없습니다.')
        layer['locked']=bool(body['locked']);return layer
    @app.post('/api/v2/annotations')
    def annotate(body:dict):
        iid=body['image_id'];shape=project.image(iid).shape[:2];kind=body['kind']
        if kind not in ('background','unknown','uncertain','exclude','protect','unprotect'):raise ValueError('영역 종류 오류')
        area=brush(np.zeros(shape,bool),body['strokes'])
        if kind in ('protect','unprotect'):
            old=unpack(project.state['protected'].get(iid),shape);old[area]=kind=='protect';project.state['protected'][iid]=pack(old)
        else:
            area&=~protection(project,iid)
            ann=project.state['annotations'].setdefault(iid,{})
            for k in ('background','unknown','uncertain','exclude'):
                old=unpack(ann.get(k),shape);old[area]=k==kind;ann[k]=pack(old)
        return {'pixels':int(area.sum())}
    @app.get('/api/v2/labels/{iid}.png')
    def label_preview(iid:str):
        labels,valid,conflict=compose(project,iid);rgb=np.zeros((*labels.shape,3),np.uint8)
        for layer in project.state['layers']:rgb[labels==layer['id']]=list(bytes.fromhex(layer['color'][1:]))
        rgb[labels==UNKNOWN]=[80,80,80];rgb[labels==UNCERTAIN]=[255,210,0];rgb[labels==EXCLUDED]=[220,40,100]
        return Response(image_bytes(rgb),media_type='image/png')
    @app.get('/api/v2/export/{iid}.zip')
    def export(iid:str):return Response(export_bytes(project,iid),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="TEM_GT_{iid}.zip"'})
    @app.post('/api/v2/evaluate')
    def evaluate(body:dict):
        iid=body['image_id'];_,valid,_=compose(project,iid)
        if not valid.any():raise ValueError('평가할 확정 레이블 영역이 없습니다.')
        tol=float(body.get('tolerance',2))
        if not 0<=tol<=100:raise ValueError('경계 허용오차 범위 0~100 px')
        ref=project.candidate(iid,body['reference_id'])
        if not ref or not ref.get('reviewed'):raise ValueError('검수 확정한 기준 후보를 선택하세요.')
        result=metric(project.mask(iid,body['candidate_id']),project.mask(iid,body['reference_id']),valid,tol)
        result.update(image_id=iid,candidate_id=body['candidate_id'],reference_id=body['reference_id'],reference='user-reviewed candidate, not independent external GT')
        if body.get('csv'):
            buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=list(result));writer.writeheader();writer.writerow(result)
            return Response('\ufeff'+buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="evaluation.csv"'})
        return result
    @app.post('/api/v2/ocr-batch')
    def ocr_batch(body:dict):
        from .ocr import read_words
        results={};ids=body.get('image_ids') or list(project.state['images'])
        for iid in ids:
            try:
                im=project.image(iid);tpl=effective_template(project,iid);roi=tpl.get('scale_roi')
                if not project.state.get('legacy_templates_enabled'):tpl={};roi=None
                roi=roi or [0,0,1,1]
                words=[];ocr_error=None
                for r in [tpl.get('scale_text_roi') or roi]:
                    x0,y0,x1,y1=roi_pixels(r,im.shape[1],im.shape[0])
                    try:ws=read_words(im[y0:y1,x0:x1],body.get('ocr_dir','models/easyocr'),'en')
                    except (ValueError,ImportError,OSError,RuntimeError) as e:ws=[];ocr_error=str(e)
                    for w in ws:w['box']=[w['box'][0]+x0,w['box'][1]+y0,w['box'][2]+x0,w['box'][3]+y0]
                    words.extend(ws)
                item=detect_scale(im,roi,words)
                if not item.get('nm_per_px') and body.get('fallback_length'):
                    from .calibration import bar_candidates
                    bars=bar_candidates(im,roi)
                    if bars:
                        b=bars[0];nm=scale_from_points(*b['bar'],body['fallback_length'],body.get('unit','nm'));item=dict(b,nm_per_px=nm,px_per_nm=1/nm,length=body['fallback_length'],unit=body.get('unit','nm'),source='manual-common-fallback',confirmed=False)
                if ocr_error:item['ocr_warning']=ocr_error
                if item.get('nm_per_px'):project.state['scale'][iid]=item
                project.state['preprocessing'][iid].update(reviewed=False,scale_requested=True,scale_status='proposed' if item.get('nm_per_px') else 'failed')
                results[iid]=item
            except (ValueError,ImportError,OSError,RuntimeError) as e:
                results[iid]={'error':str(e)};project.state['preprocessing'].setdefault(iid,{}).update(reviewed=False,scale_requested=True,scale_status='error',last_error=str(e))
        return results

    @app.post('/api/v2/boundary/preview')
    def boundary_preview(body:dict):
        iid=body['image_id'];a=project.candidate(iid,body['candidate_id']);b=project.candidate(iid,body['neighbor_id']) if body.get('neighbor_id') else None
        if body.get('neighbor_id') and b is None:raise ValueError('인접 후보 B가 없습니다.')
        if not a or a['layer_id'] is None or not a.get('active',True):raise ValueError('레이어에 지정된 활성 후보 A를 선택하세요.')
        if b and (b['layer_id'] is None or b['layer_id']==a['layer_id'] or not b.get('active',True)):raise ValueError('서로 다른 레이어의 인접 활성 후보 B를 선택하세요.')
        project.assert_editable(a);project.assert_editable(b)
        labels,valid,conflict=compose(project,iid)
        if conflict.any():raise ValueError('레이어 겹침을 먼저 해결하세요.')
        am=project.mask(iid,a['id']);bm=project.mask(iid,b['id']) if b else labels==0
        if not bm.any():raise ValueError('인접 후보 B 또는 명시적 배경 영역이 필요합니다.')
        guard=protection(project,iid);eligible=(am|bm)&valid&~guard&((labels==a['layer_id'])|(labels==(b['layer_id'] if b else 0)))
        rgb=model_input(project,iid,'edge')
        settings=body.get('settings',{});record=project.state['preprocessing'][iid];edge_cfg=record.get('edge_filter',{})
        # model_input already filtered. Erode safety for configured filter support, without filtering twice.
        safe=~excluded(am.shape,effective_template(project,iid));safe&=~guard
        from .preprocessing import filter_support
        support=filter_support(edge_cfg)
        if support:safe=ndi.binary_erosion(safe,iterations=support)
        result=refine_all(rgb,am,safe,settings,overrides=body.get('overrides'),pins=body.get('pins'))
        candidate=am.copy();candidate[eligible]=result['mask'][eligible]
        # Only move the common interface, never the free external boundary of A.
        radius=max(float(result['settings']['inside']),float(result['settings']['outside']))+2
        common_band=ndi.distance_transform_edt(~bm)<=radius
        candidate[~common_band]=am[~common_band]
        new_b=bm.copy();changed=candidate!=am;new_b[changed]=~candidate[changed]
        if topology(candidate)!=topology(am) or topology(new_b)!=topology(bm):raise ValueError('공유 경계 적용 시 연결 구조가 달라집니다. 탐색 폭을 줄이세요.')
        token=uuid.uuid4().hex
        previews.clear();previews[token]={'image_id':iid,'revision':project.state['revision'],'a':copy.deepcopy(a),'b':copy.deepcopy(b),'mask_a':candidate,'mask_b':new_b,'loops':result['loops'],'settings':result['settings'],'inputs':body,'changed':int(changed.sum())}
        return {'token':token,'changed_pixels':int(changed.sum()),'loops':[{k:v for k,v in loop.items() if k not in ('response','offset_grid')} for loop in result['loops']], 'note':'청록 DP 곡선은 제안입니다. 최종 미리보기 마스크는 보호·공유 경계 제약을 적용합니다.'}
    @app.get('/api/v2/boundary/{token}.png')
    def boundary_mask(token:str):
        p=previews.get(token)
        if not p:raise ValueError('미리보기가 만료되었습니다.')
        return Response(image_bytes(p['mask_a'].astype('uint8')*255),media_type='image/png')
    @app.get('/api/v2/boundary/{token}/profile')
    def profile(token:str,loop:int=0,index:int=0):
        p=previews.get(token)
        if not p or not 0<=loop<len(p['loops']):raise ValueError('미리보기 경계가 없습니다.')
        line=p['loops'][loop]
        if not 0<=index<len(line['initial']):raise ValueError('경계 점 번호 오류')
        return {'offset':line['offset_grid'],'gradient':line['response'][index],'chosen':line['offset_px'][index],'point':line['initial'][index],'normal':line['normal'][index],'uncertain':line['uncertain'][index]}
    @app.post('/api/v2/boundary/apply')
    def boundary_apply(body:dict):
        p=previews.get(body['token'])
        # Middleware checkpoints add one to the revision immediately before this endpoint.
        if not p or p['revision']!=project.state['revision']-1:raise ValueError('미리보기 후 상태가 바뀌었습니다. 다시 미리보기 하세요.')
        iid=p['image_id'];created=[]
        for old,mask in [(p['a'],p['mask_a']),(p['b'],p['mask_b'])]:
            if old:
                project.assert_editable(old)
                c=project.put_candidate(iid,mask,'boundary',parent=old['id'],prompts={'settings':p['settings'],'inputs':p['inputs']});c.update(layer_id=old['layer_id'],instance_id=old['instance_id'],reviewed=True)
                project.candidate(iid,old['id']).update(active=False,reviewed=False);created.append(c)
            else:
                ann=project.state['annotations'].setdefault(iid,{});ann['background']=pack(mask)
        previews.clear();return {'created':created,'changed_pixels':p['changed']}
    @app.post('/api/v2/boundary/cancel')
    def boundary_cancel(body:dict):previews.pop(body.get('token'),None);return {'ok':True}

    return gate
