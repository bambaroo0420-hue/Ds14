"""Independent ROI automatic candidates: staged, stale-safe, explicitly accepted."""
import copy,time,uuid
import numpy as np
from fastapi import HTTPException
from fastapi.responses import Response
from ..preprocessing import model_input,exclusion_mask,restrict_mask
from ..prompts import grid_points
from ..feature_prompts import FeatureConfig,propose as feature_proposals


def install(app,project,model,lock,reviews):
    from ..v2_api import image_bytes,save_prediction
    staged={}
    def require(token):
        r=staged.get(token)
        if not r or time.monotonic()-r['time']>900:raise ValueError('ROI 자동 후보 미리보기가 만료되었습니다.')
        if reviews.fingerprint(r['iid'],None)!=r['fingerprint']:raise ValueError('영상·모델·제외·전처리가 바뀌었습니다. ROI 후보를 다시 제안하세요.')
        return r

    @app.post('/api/sam/roi-auto/preview')
    def preview(body:dict):
        if not lock.acquire(False):raise HTTPException(409,'모델 작업 중입니다.')
        try:
            iid=body['image_id'];rgb=model_input(project,iid);h,w=rgb.shape[:2];roi=body['roi']
            if len(roi)!=4 or not np.isfinite(roi).all() or any(v!=int(v) for v in roi):raise ValueError('ROI는 정수 픽셀 경계입니다.')
            x0,y0,x1,y1=map(int,roi)
            if not(0<=x0<x1<=w and 0<=y0<y1<=h) or min(x1-x0,y1-y0)<16:raise ValueError('영상 안에 16px 이상 ROI를 지정하세요.')
            grid=int(body.get('grid',8));mode=body.get('prompt_source','grid');values=[float(body.get(k,d)) for k,d in [('pred_iou',.9),('stability',.92),('nms',.8)]]
            if not 2<=grid<=16 or mode not in ('grid','features','grid_features') or not np.isfinite(values).all() or any(not 0<=v<=1 for v in values):raise ValueError('ROI 자동점/필터 설정 범위 오류')
            ex=exclusion_mask(project,iid)[y0:y1,x0:x1];crop=rgb[y0:y1,x0:x1]
            pts=grid_points(crop.shape[:2],grid,ex) if mode!='features' else []
            if mode!='grid':
                prompt=model_input(project,iid,'prompt')[y0:y1,x0:x1]
                pts+=feature_proposals(prompt,ex,pts,FeatureConfig(**body.get('feature_settings',{})))['points']
            items=model.automatic(crop,grid,*values,ex,prepared_points=pts)
            if len(items)>64:raise ValueError('ROI 후보가 64개를 넘습니다. 필터를 높이거나 영역을 나누세요.')
            saved=[]
            for item in items:
                full=np.zeros((h,w),bool);full[y0:y1,x0:x1]=item['mask'];item=copy.deepcopy(item);item['mask']=restrict_mask(project,iid,full)
                if not item['mask'].any():continue
                for key in ('logits','context','probability'):item.pop(key,None)
                item['inference_domains']=[[x0,y0,x1,y1]];saved.append(item)
            now=time.monotonic()
            for key in list(staged):
                if now-staged[key]['time']>900:del staged[key]
            while len(staged)>=2:del staged[next(iter(staged))]
            token=uuid.uuid4().hex;params=dict(body,auto_points=[[p[0]+x0,p[1]+y0] for p in pts],roi=roi)
            staged[token]=dict(iid=iid,items=saved,params=params,time=now,fingerprint=reviews.fingerprint(iid,None))
            return dict(token=token,count=len(saved),prompt_count=len(pts),saved=False,candidates=[dict(index=i,area=int(x['mask'].sum()),score=x.get('score')) for i,x in enumerate(saved)],note='원본 ROI 내부만 분할합니다. crop 가장자리는 실제 물질 경계가 아닐 수 있습니다.')
        finally:lock.release()

    @app.get('/api/roi-auto/{token}.png')
    def image(token:str,index:int=-1):
        r=require(token);rgb=project.image(r['iid']);items=r['items']
        if index < -1 or index>=len(items):raise ValueError('ROI 후보 번호 오류')
        for i,item in enumerate(items):
            if index>=0 and i!=index:continue
            color=np.array([(i*71+70)%190+40,(i*113+60)%190+40,(i*41+90)%190+40])
            rgb[item['mask']]=np.uint8(rgb[item['mask']]*.45+color*.55)
        return Response(image_bytes(rgb),media_type='image/png')

    @app.post('/api/sam/roi-auto/accept')
    def accept(body:dict):
        r=require(body['token']);indices=body.get('indices',[])
        if body.get('image_id')!=r['iid']:raise ValueError('ROI 제안의 이미지와 저장 대상이 다릅니다.')
        if any((c.get('prompts') or {}).get('roi_auto_token')==body['token'] for c in project.state['candidates'][r['iid']]):raise ValueError('이미 저장한 ROI 제안입니다. 새로 제안하거나 Undo 후 다시 저장하세요.')
        if not indices or len(set(indices))!=len(indices) or any(type(i)!=int or not 0<=i<len(r['items']) for i in indices):raise ValueError('저장할 후보를 선택하세요.')
        result=[save_prediction(project,r['iid'],r['items'][i],'roi-auto',prompts=dict(r['params'],roi_auto_token=body['token'])) for i in indices]
        # Retain the immutable preview until expiry: a failed metadata save can be retried.
        return {'created':result,'count':len(result)}
