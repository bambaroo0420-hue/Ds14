"""Temporary ROI inference: no project writes until explicit acceptance."""
import copy,hashlib,io,json,time,uuid
import numpy as np
from PIL import Image
from fastapi import HTTPException
from fastapi.responses import Response
from .preprocessing import effective_template,restrict_mask
from .roi_domains import crop_contacts

class ROIReviews:
    def __init__(self,project,model):self.project=project;self.model=model;self.items={}
    def fingerprint(self,iid,parent):
        p=self.project;p.require_image(iid);c=p.candidate(iid,parent) if parent is not None else None
        if parent is not None and not c:raise ValueError('부모 후보가 삭제되었습니다.')
        from .preprocessing import exclusion_mask
        data={'parent':c,'template':effective_template(p,iid),'preprocessing':p.state.get('preprocessing',{}).get(iid),'model':self.model.info,
              'image':hashlib.sha256(p.image(iid).tobytes()).hexdigest(),'exclude':hashlib.sha256(exclusion_mask(p,iid).tobytes()).hexdigest(),
              'mask':hashlib.sha256(p.mask(iid,parent).tobytes()).hexdigest() if c else None}
        return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def stage(self,iid,parent,item,prompts):
        if parent is None and not prompts.get('roi'):raise ValueError('독립 미리보기에는 추론 ROI가 필요합니다.')
        now=time.monotonic();self.items={k:v for k,v in self.items.items() if now-v['time']<900}
        while len(self.items)>=4:self.items.pop(next(iter(self.items)))
        token=uuid.uuid4().hex;result=copy.deepcopy({k:v for k,v in item.items() if k!='probability'});result['mask']=restrict_mask(self.project,iid,result['mask'])
        if not result['mask'].any():raise ValueError('제외 영역 밖에 남은 마스크가 없습니다.')
        self.items[token]={'time':now,'image_id':iid,'parent':parent,'item':result,'prompts':copy.deepcopy(prompts),'fingerprint':self.fingerprint(iid,parent)}
        # Inspect local crop touches without creating any candidate or mask file.
        touches=bool(crop_contacts(result['mask'],result.get('inference_domains',[])).any())
        warnings=['추론 ROI 가장자리 2 px 이내에 마스크가 있습니다. 절단 의심 영역을 2 px 확장해 GT/계측에서 미지정 처리합니다. 더 넓은 ROI로 재검토하세요.'] if touches else []
        if result.get('prompt_violations'):warnings.append(f"양성/음성 입력점 {len(result['prompt_violations'])}개가 결과와 맞지 않습니다. 다른 후보·점·box를 검토하세요.")
        return {'preview_token':token,'area':int(result['mask'].sum()),'saved':False,'crop_truncated':touches,
                'mask_choice':result.get('mask_choice'),'multimask_scores':result.get('multimask_scores',[]),
                'prompt_violations':result.get('prompt_violations',[]),'warnings':warnings}
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
                if self.fingerprint(r['image_id'],r['parent'])!=r['fingerprint']:raise ValueError('영상·부모 후보·제외 영역·전처리·모델이 변경되었습니다. 다시 미리보기 하세요.')
                p=self.project
                if r['parent'] is not None and hasattr(p,'assert_editable'):p.assert_editable(p.candidate(r['image_id'],r['parent']))
                result=save(r);self.items.pop(token,None);return result
            except (ValueError,KeyError) as e:raise HTTPException(409,str(e)) from e
            finally:lock.release()
