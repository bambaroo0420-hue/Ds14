"""Local-only API. Unimplemented pages expose data but never fabricate results."""
import io
import os
from pathlib import Path
from threading import Lock
import numpy as np
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .storage import Project
from .sam_service import ModelService
from .operations import excluded, brush, scale_from_points, detect_scale, layer_coverage, roi_pixels

ROOT=Path(os.environ.get('TEM_PROJECT_DIR',Path(__file__).resolve().parent.parent/'projects'/'default')).resolve()
project=Project(ROOT); model=ModelService(); model_lock=Lock()
WEB=Path(__file__).resolve().parent.parent/'web'
app=FastAPI(title='TEM Analyzer v1')
app.mount('/web',StaticFiles(directory=WEB),name='web')

def fail(exc):
    if isinstance(exc,(KeyError,ValueError)):raise HTTPException(400,str(exc)) from exc
    raise exc

def png(a):
    out=io.BytesIO();Image.fromarray(a).save(out,format='PNG');return Response(out.getvalue(),media_type='image/png')

@app.get('/')
def index():return FileResponse(WEB/'index.html')

@app.get('/api/state')
def state():return dict(project.state,model=model.info,capabilities={'boundary':'planned','measurement':'planned','sam':'available' if model.info else 'requires_model'})

@app.post('/api/images')
async def upload(file:UploadFile=File(...)):
    try:
        data=await file.read(100*1024*1024+1)
        if len(data)>100*1024*1024:raise ValueError('파일은 100 MB 이하로 제한합니다.')
        return {'image_id':project.add_image(data,file.filename or 'image')}
    except (ValueError,OSError) as e:fail(e)

@app.get('/api/images/{image_id}.png')
def image(image_id:str):
    try:project.require_image(image_id);return FileResponse(project.root/'images'/f'{image_id}.png')
    except KeyError as e:fail(e)

@app.delete('/api/images/{image_id}')
def remove(image_id:str):
    try:project.delete_image(image_id);return {'ok':True}
    except KeyError as e:fail(e)

class TemplateIn(BaseModel):
    id:str;name:str;scale_roi:list[float]|None=None;text_rois:list[list[float]]=[]
@app.post('/api/templates')
def template(body:TemplateIn):
    try:return project.update_template(body.model_dump())
    except ValueError as e:fail(e)

class SelectTemplate(BaseModel):id:str
@app.post('/api/templates/select')
def select_template(body:SelectTemplate):
    if body.id not in project.state['templates']:raise HTTPException(400,'존재하지 않는 템플릿')
    project.state['selected_template']=body.id;project.save();return {'ok':True}

class ScaleManual(BaseModel):image_id:str;a:list[float];b:list[float];length:float;unit:str='nm'
@app.post('/api/scale/manual')
def scale_manual(body:ScaleManual):
    try:
        project.require_image(body.image_id)
        nm=scale_from_points(body.a,body.b,body.length,body.unit)
        project.state['scale'][body.image_id]=dict(nm_per_px=nm,bar=[body.a,body.b],confirmed=True,source='manual');project.save()
        return project.state['scale'][body.image_id]
    except (KeyError,ValueError) as e:fail(e)

class ScaleAuto(BaseModel):image_id:str;ocr_dir:str='models/easyocr';language:str='en'
@app.post('/api/scale/detect')
def scale_detect(body:ScaleAuto):
    try:
        im=project.image(body.image_id);tpl=project.state['templates'][project.state['selected_template']]
        if tpl.get('scale_roi') is None: raise ValueError('스케일 ROI를 드래그하여 저장한 뒤 OCR을 실행하세요.')
        x0,y0,x1,y1=roi_pixels(tpl['scale_roi'],im.shape[1],im.shape[0])
        # EasyOCR is optional and configured for local weights, with download disabled.
        from .ocr import read_words
        words=read_words(im[y0:y1,x0:x1],body.ocr_dir,body.language)
        for word in words:word['box']=[word['box'][0]+x0,word['box'][1]+y0,word['box'][2]+x0,word['box'][3]+y0]
        item=detect_scale(im,tpl['scale_roi'],words)
        project.state['scale'][body.image_id]=item;project.save();return item
    except (KeyError,ValueError,ImportError) as e:fail(e)

class ScaleConfirm(BaseModel):image_id:str
@app.post('/api/scale/confirm')
def scale_confirm(body:ScaleConfirm):
    item=project.state['scale'].get(body.image_id)
    if not item or not item.get('nm_per_px'):raise HTTPException(400,'스케일을 먼저 확인하세요.')
    item['confirmed']=True;project.save();return item

class ModelIn(BaseModel):checkpoint:str;variant:str='vit_h';device:str='auto';decoder_path:str|None=None;refiner_path:str|None=None
@app.post('/api/model/load')
def model_load(body:ModelIn):
    if not model_lock.acquire(blocking=False):raise HTTPException(409,'모델 작업 중입니다.')
    try:return model.load(**body.model_dump())
    except (ValueError,ImportError,RuntimeError,FileNotFoundError) as e:fail(ValueError(str(e)))
    finally:model_lock.release()

class AutoIn(BaseModel):image_id:str;grid:int=Field(default=16,ge=2,le=32);pred_iou:float=Field(default=.90,ge=0,le=1);stability:float=Field(default=.92,ge=0,le=1);nms:float=Field(default=.8,ge=0,le=1)
@app.post('/api/sam/automatic')
def automatic(body:AutoIn):
    if not model_lock.acquire(blocking=False):raise HTTPException(409,'모델 작업 중입니다.')
    try:
        im=project.image(body.image_id);tpl=project.state['templates'][project.state['selected_template']]
        items=model.automatic(im,body.grid,body.pred_iou,body.stability,body.nms,excluded(im.shape[:2],tpl))
        saved=[]
        for item in items:
            c=project.put_candidate(body.image_id,item['mask'],'grid',item['score'],prompts={'grid':body.grid,'stability':item['stability'],'bbox':item['bbox']})
            saved.append(c)
        return {'created':saved,'count':len(saved),'grid_points_max':body.grid**2}
    except (KeyError,ValueError,RuntimeError,MemoryError) as e:fail(ValueError(str(e)))
    finally:model_lock.release()

class PromptIn(BaseModel):image_id:str;points:list[list[float]]=[];box:list[float]|None=None;roi:list[float]|None=None;parent:int|None=None
@app.post('/api/sam/prompt')
def prompt(body:PromptIn):
    if not model_lock.acquire(blocking=False):raise HTTPException(409,'모델 작업 중입니다.')
    try:
        im=project.image(body.image_id)
        if body.parent is not None and project.candidate(body.image_id,body.parent) is None:raise ValueError('부모 후보가 없습니다.')
        item=model.in_roi(im,body.roi,body.points,body.box) if body.roi else model.prompt(im,body.points,body.box)
        if body.roi and body.parent is not None:
            item['mask'] &= project.mask(body.image_id,body.parent)
        return project.put_candidate(body.image_id,item['mask'],'roi-refine' if body.roi else 'manual',item['score'],body.parent,{'points':body.points,'box':body.box,'roi':body.roi})
    except (KeyError,ValueError,RuntimeError) as e:fail(ValueError(str(e)))
    finally:model_lock.release()

@app.get('/api/masks/{image_id}/{candidate_id}.png')
def mask(image_id:str,candidate_id:int):
    try:return png((project.mask(image_id,candidate_id)*255).astype('uint8'))
    except KeyError as e:fail(e)

class Duplicate(BaseModel):image_id:str;candidate_id:int
@app.post('/api/candidates/duplicate')
def duplicate(body:Duplicate):
    try:
        old=project.candidate(body.image_id,body.candidate_id)
        if old is None:raise KeyError('후보가 없습니다.')
        return project.put_candidate(body.image_id,project.mask(body.image_id,body.candidate_id),'duplicate',old['predicted_iou'],body.candidate_id)
    except KeyError as e:fail(e)

class Paint(BaseModel):image_id:str;candidate_id:int;strokes:list[dict]
@app.post('/api/candidates/brush')
def paint(body:Paint):
    try:
        old=project.candidate(body.image_id,body.candidate_id)
        if old is None:raise KeyError('후보가 없습니다.')
        edited=brush(project.mask(body.image_id,body.candidate_id),body.strokes)
        return project.put_candidate(body.image_id,edited,'brush',None,body.candidate_id)
    except (KeyError,ValueError) as e:fail(e)

class LayerIn(BaseModel):id:int|None=None;name:str;color:str='#28dc82'
@app.post('/api/layers')
def layer(body:LayerIn):
    if not body.name.strip():raise HTTPException(400,'레이어 이름을 입력하세요.')
    layers=project.state['layers'];lid=body.id or (max(x['id'] for x in layers)+1 if layers else 1)
    old=next((x for x in layers if x['id']==lid),None)
    if old:old.update(name=body.name,color=body.color)
    else:layers.append(dict(id=lid,name=body.name,color=body.color))
    project.save();return {'id':lid}

class Assign(BaseModel):image_id:str;candidate_id:int;layer_id:int|None;instance_id:str|None=None;reviewed:bool=False
@app.post('/api/layers/assign')
def assign(body:Assign):
    item=project.candidate(body.image_id,body.candidate_id)
    if item is None:raise HTTPException(400,'후보가 없습니다.')
    if body.layer_id is not None and body.layer_id not in [x['id'] for x in project.state['layers']]:raise HTTPException(400,'레이어가 없습니다.')
    item.update(layer_id=body.layer_id,instance_id=body.instance_id,reviewed=body.reviewed);project.save();return item

@app.get('/api/coverage/{image_id}.png')
def coverage(image_id:str):
    try:
        labels,overlap=layer_coverage(project,image_id)
        rgb=np.zeros((*labels.shape,3),np.uint8)
        for layer in project.state['layers']:
            color=layer['color'].lstrip('#');rgb[labels==layer['id']]=tuple(bytes.fromhex(color[:6]))
        rgb[overlap]=[255,255,0]
        return png(rgb)
    except (KeyError,ValueError) as e:fail(e)

@app.get('/api/coverage/{image_id}/stats')
def coverage_stats(image_id:str):
    try:
        labels,overlap=layer_coverage(project,image_id)
        template=project.state['templates'][project.state['selected_template']]
        valid=~excluded(labels.shape,template)
        return dict(unassigned=int(((labels==0)&valid).sum()),overlap=int((overlap&valid).sum()),excluded=int((~valid).sum()),total=int(labels.size))
    except KeyError as e:fail(e)


class PrepareGrid(BaseModel):
    image_id:str
    grid:int=Field(default=16,ge=2,le=32)

@app.post('/api/prompts/grid')
def prepare_grid(body:PrepareGrid):
    from .prompts import grid_points
    try:
        im=project.image(body.image_id)
        template=project.state['templates'][project.state['selected_template']]
        points=grid_points(im.shape[:2],body.grid,excluded(im.shape[:2],template))
        return {'points':points,'count':len(points),'inference_run':False}
    except (KeyError,ValueError) as e:fail(e)

class PrepareML(BaseModel):
    image_id:str
    existing:list[list[float]]=Field(default_factory=list)
    count:int=Field(default=12,ge=1,le=100)
    clusters:int=Field(default=5,ge=2,le=12)
    min_distance:float=Field(default=12,ge=1,le=1000)

@app.post('/api/prompts/ml')
def prepare_ml(body:PrepareML):
    from .prompts import ml_points,validate_points
    try:
        im=project.image(body.image_id)
        validate_points(body.existing,im.shape[1],im.shape[0])
        template=project.state['templates'][project.state['selected_template']]
        points=ml_points(im,excluded(im.shape[:2],template),body.existing,body.count,body.clusters,body.min_distance)
        return {'points':points,'count':len(points),'method':'unsupervised_kmeans_intensity_texture','inference_run':False}
    except (KeyError,ValueError) as e:fail(e)

class PreparedRun(BaseModel):
    image_id:str
    auto_points:list[list[float]]=Field(default_factory=list)
    manual_points:list[list[float]]=Field(default_factory=list)
    box:list[float]|None=None
    manual_mode:str='object'
    pred_iou:float=Field(default=.90,ge=0,le=1)
    stability:float=Field(default=.92,ge=0,le=1)
    nms:float=Field(default=.8,ge=0,le=1)

@app.post('/api/sam/prepared')
def run_prepared(body:PreparedRun):
    from .prompts import validate_points
    if not model_lock.acquire(blocking=False):raise HTTPException(409,'모델 작업 중입니다.')
    try:
        im=project.image(body.image_id);h,w=im.shape[:2]
        validate_points(body.auto_points,w,h);validate_points(body.manual_points,w,h)
        if any(len(p)!=3 or p[2] not in (0,1) for p in body.manual_points):raise ValueError('수동점은 [x,y,0 또는 1] 형식이어야 합니다.')
        if body.manual_mode not in ('object','independent'):raise ValueError('잘못된 수동점 실행 방식')
        if body.box is not None:
            if len(body.box)!=4 or not (0<=body.box[0]<body.box[2]<=w and 0<=body.box[1]<body.box[3]<=h):raise ValueError('잘못된 box')
        auto=list(body.auto_points);manual=body.manual_points
        if body.manual_mode=='independent':
            if body.box or any(p[2]==0 for p in manual):raise ValueError('음성점·box는 한 객체로 묶기 모드에서 사용하세요.')
            auto += [p[:2] for p in manual];manual=[]
        if not auto and not manual and body.box is None:raise ValueError('Grid/ML/수동점 또는 box를 먼저 준비하세요.')
        template=project.state['templates'][project.state['selected_template']]
        prepared={'auto_points':auto,'manual_points':body.manual_points,'box':body.box,'manual_mode':body.manual_mode}
        result=[]
        if auto:
            items=model.automatic(im,pred_iou=body.pred_iou,stability=body.stability,nms=body.nms,exclude=excluded((h,w),template),prepared_points=auto)
            for item in items:
                result.append(project.put_candidate(body.image_id,item['mask'],'prepared-auto',item['score'],prompts={**prepared,'stability':item['stability']}))
        if manual or body.box:
            item=model.prompt(im,manual,body.box)
            result.append(project.put_candidate(body.image_id,item['mask'],'manual',item['score'],prompts=prepared))
        project.state.setdefault('prepared_prompts',{})[body.image_id]=prepared;project.save()
        return {'count':len(result),'created':result}
    except (KeyError,ValueError,RuntimeError) as e:fail(ValueError(str(e)))
    finally:model_lock.release()

@app.delete('/api/candidates/{image_id}/{candidate_id}')
def delete_candidate(image_id:str,candidate_id:int):
    try:
        if project.candidate(image_id,candidate_id) is None:raise KeyError('후보가 없습니다.')
        project.state['candidates'][image_id]=[c for c in project.state['candidates'][image_id] if c['id']!=candidate_id]
        project.mask_path(image_id,candidate_id).unlink(missing_ok=True)
        project.save();return {'ok':True}
    except KeyError as e:fail(e)

@app.delete('/api/layers/{layer_id}')
def delete_layer(layer_id:int):
    if layer_id not in [x['id'] for x in project.state['layers']]:raise HTTPException(400,'레이어가 없습니다.')
    project.state['layers']=[x for x in project.state['layers'] if x['id']!=layer_id]
    for items in project.state['candidates'].values():
        for item in items:
            if item['layer_id']==layer_id:item.update(layer_id=None,instance_id=None,reviewed=False)
    project.save();return {'ok':True,'candidates_preserved':True}

@app.get('/api/layer-mask/{image_id}/{layer_id}.png')
def layer_mask(image_id:str,layer_id:int):
    try:
        shape=project.image(image_id).shape[:2];mask=np.zeros(shape,bool)
        for c in project.state['candidates'][image_id]:
            if c['layer_id']==layer_id:mask|=project.mask(image_id,c['id'])
        return png((mask*255).astype('uint8'))
    except KeyError as e:fail(e)
