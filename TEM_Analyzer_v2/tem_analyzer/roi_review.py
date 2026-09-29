"""Temporary ROI inference: no project writes until explicit acceptance."""
import copy,hashlib,io,json,time,uuid
import numpy as np
from PIL import Image
from fastapi import HTTPException
from fastapi.responses import Response
from .preprocessing import effective_template,restrict_mask

class ROIReviews:
    def __init__(self,project,model):self.project=project;self.model=model;self.items={}
    def fingerprint(self,iid,parent):
        p=self.project;p.require_image(iid);c=p.candidate(iid,parent)
        if not c:raise ValueError('부모 후보가 삭제되었습니다.')
        data={'parent':c,'template':effective_template(p,iid),'preprocessing':p.state.get('preprocessing',{}).get(iid),'model':self.model.info,'mask':hashlib.sha256(p.mask(iid,parent).tobytes()).hexdigest()}
        return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def stage(self,iid,parent,item,prompts):
        if parent is None:raise ValueError('ROI 미리보기에는 부모 후보가 필요합니다.')
        now=time.monotonic();self.items={k:v for k,v in self.items.items() if now-v['time']<900}
        while len(self.items)>=4:self.items.pop(next(iter(self.items)))
        token=uuid.uuid4().hex;result=copy.deepcopy({k:v for k,v in item.items() if k!='probability'});result['mask']=restrict_mask(self.project,iid,result['mask'])
        if not result['mask'].any():raise ValueError('제외 영역 밖에 남은 마스크가 없습니다.')
        self.items[token]={'time':now,'image_id':iid,'parent':parent,'item':result,'prompts':copy.deepcopy(prompts),'fingerprint':self.fingerprint(iid,parent)}
        return {'preview_token':token,'area':int(result['mask'].sum()),'saved':False}
    def require(self,token):
        r=self.items.get(token)
        if not r or time.monotonic()-r['time']>=900:
            self.items.pop(token,None);raise HTTPException(410,'미리보기가 만료되었습니다. 다시 실행하세요.')
        return r
    def install(self,app,lock,save):
        @app.get('/api/roi-previews/{token}.png')
        def mask(token:str):
            r=self.require(token);out=io.BytesIO();Image.fromarray(r['item']['mask'].astype('uint8')*255).save(out,format='PNG');return Response(out.getvalue(),media_type='image/png')
        @app.delete('/api/roi-previews/{token}')
        def discard(token:str):self.items.pop(token,None);return {'saved':False,'discarded':True}
        @app.post('/api/roi-previews/{token}/accept')
        def accept(token:str):
            if not lock.acquire(blocking=False):raise HTTPException(409,'모델 작업 중입니다.')
            try:
                r=self.require(token)
                if self.fingerprint(r['image_id'],r['parent'])!=r['fingerprint']:raise ValueError('부모 후보·전처리·모델이 변경되었습니다. 다시 미리보기 하세요.')
                p=self.project
                if hasattr(p,'assert_editable'):p.assert_editable(p.candidate(r['image_id'],r['parent']))
                result=save(r);self.items.pop(token,None);return result
            except (ValueError,KeyError) as e:raise HTTPException(409,str(e)) from e
            finally:lock.release()
