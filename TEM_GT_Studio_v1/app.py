from __future__ import annotations
import argparse,base64,io,json,os,secrets,threading,traceback,uuid,webbrowser
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from flask import Flask,request,jsonify,send_file
from scipy import ndimage as ndi
import cv2
from core import Document,png,recognize,semantic_edges
from sam_adapter import SamAdapter
from model_paths import inventory

app=Flask(__name__,static_folder='static'); app.config['MAX_CONTENT_LENGTH']=128*1024*1024
DOCS={}; SAM=SamAdapter(); LOCK=threading.RLock(); TOKEN=secrets.token_urlsafe(24)
COLORS=np.array([[0,0,0],[50,190,255],[255,164,65],[138,235,139],[240,100,180],[190,155,255],[255,220,70]],np.uint8)

def uri(a): return 'data:image/png;base64,'+base64.b64encode(png(a)).decode()
def current():
    key=request.args.get('id') or (request.get_json(silent=True) or {}).get('id')
    if key not in DOCS: raise ValueError('이미지를 먼저 선택하세요.')
    return DOCS[key]
def state(d):
    rgba=np.zeros((d.h,d.w,4),np.uint8)
    rgba[:,:,:3]=COLORS[d.labels%len(COLORS)]; rgba[:,:,3]=np.where(d.valid,110,0)
    rgba[d.exclude]=[255,60,70,150]
    e,_=semantic_edges(d.labels,d.valid&~d.exclude)
    edge=np.zeros_like(rgba); edge[e.astype(bool)]=[255,255,0,255]
    return {'overlay':uri(rgba),'edge':uri(edge),'width':d.w,'height':d.h,'name':d.name,'classes':d.classes,'meta':d.meta,'lines':d.preview['paths'] if d.preview else [],'valid_pixels':int((d.valid&~d.exclude).sum())}
@app.before_request
def guard():
    if request.method=='POST' and request.headers.get('X-GT-Token')!=TOKEN: return jsonify(error='Invalid session token'),403
@app.errorhandler(Exception)
def error(e):
    traceback.print_exc(); return jsonify(error=str(e)),400
@app.get('/')
def index(): return app.send_static_file('index.html')
@app.get('/api/session')
def session(): return jsonify(token=TOKEN)
@app.get('/api/documents')
def documents(): return jsonify([{'id':k,'name':d.name} for k,d in DOCS.items()])
@app.get('/api/state')
def getstate(): return jsonify(state(current()))
@app.get('/api/image')
def getimage(): return send_file(io.BytesIO(png(current().image)),mimetype='image/png')
@app.post('/api/upload')
def upload():
    ids=[]
    for f in request.files.getlist('files'):
        if f.filename.lower().endswith('.zip'): d=Document.load(f.read())
        else:
            img=Image.open(f.stream)
            if img.width*img.height>32_000_000: raise ValueError('최대 3200만 픽셀입니다. 큰 이미지는 ROI로 나누세요.')
            d=Document(img,f.filename)
        key=uuid.uuid4().hex; DOCS[key]=d; ids.append(key)
    return jsonify(ids=ids)
@app.post('/api/delete')
def delete():
    key=request.json['id']; DOCS.pop(key,None); return jsonify(ok=True)
@app.post('/api/edit')
def edit():
    d=current(); a=request.json; mask=np.zeros((d.h,d.w),np.uint8); pts=np.rint(a.get('points',[])).astype(np.int32)
    kind=a['kind']
    if kind=='polygon':
        if len(pts)<3: raise ValueError('다각형은 3점 이상 필요합니다.')
        cv2.fillPoly(mask,[pts],1)
    elif kind=='rectangle':
        if len(pts)!=2: raise ValueError('사각형 두 점 필요')
        cv2.rectangle(mask,tuple(pts[0]),tuple(pts[1]),1,-1)
    elif kind=='brush':
        if not len(pts): raise ValueError('브러시 점 없음')
        radius=max(1,int(a.get('radius',5)))
        for p in pts: cv2.circle(mask,tuple(p),radius,1,-1)
        if len(pts)>1: cv2.polylines(mask,[pts],False,1,2*radius)
    elif kind=='superpixel':
        if d.sp is None: raise ValueError('Superpixel을 먼저 생성하세요.')
        ids=set()
        for x,y in pts:
            if 0<=x<d.w and 0<=y<d.h: ids.add(int(d.sp[y,x]))
        ids.discard(0); mask=np.isin(d.sp,list(ids)).astype('uint8')
    cid=int(a.get('cid',1))
    if not 0<=cid<=65534: raise ValueError('class ID는 0~65534입니다.')
    d.edit(mask.astype(bool),cid,a.get('action','paint')); return jsonify(state(d))
@app.post('/api/classes')
def classes():
    d=current(); vals=request.json['classes']
    if any(not str(k).isdigit() or not 1<=int(k)<=65534 or not v.strip() for k,v in vals.items()): raise ValueError('유효한 class ID/이름 필요')
    if any(str(int(k)) not in vals for k in np.unique(d.labels[d.valid]) if k): raise ValueError('사용 중인 class는 삭제할 수 없습니다.')
    d.push(); d.classes=vals; return jsonify(state(d))
@app.post('/api/undo')
def undo():
    d=current(); d.undo(request.json.get('redo',False)); return jsonify(state(d))
@app.post('/api/superpixels')
def superpixels():
    d=current(); a=request.json; b=d.superpixels(a.get('roi'),float(a.get('size',24)),float(a.get('compactness',.1)),float(a.get('sigma',1)))
    overlay=np.zeros((d.h,d.w,4),np.uint8); overlay[b]=[255,255,255,180]
    return jsonify(overlay=uri(overlay))
@app.post('/api/refine')
def refine():
    d=current(); a=request.json
    d.refine(cid=int(a['cid']),line=a.get('line'),roi=a.get('roi'),width=max(1,min(30,int(a.get('width',8)))),continuity=max(0,float(a.get('continuity',.15))),sigma=max(0,float(a.get('sigma',1))),contrast=max(0,float(a.get('contrast',0))))
    return jsonify(state(d))
@app.post('/api/accept')
def accept():
    d=current(); d.accept(int(request.json.get('other',0))); return jsonify(state(d))
@app.post('/api/ocr')
def ocr():
    d=current(); a=request.json
    with LOCK: result=recognize(d.image,a.get('model_dir') or 'models/easyocr',a.get('language','en'))
    d.push(); d.meta['ocr']=result; return jsonify(result)
@app.post('/api/exclude_ocr')
def excludeocr():
    d=current(); a=request.json; ocr=d.meta.get('ocr'); boxes=[w['box'] for w in (ocr.get('words',[]) if isinstance(ocr,dict) else [])]
    scale=d.meta.get('scale') or {}
    if scale.get('bar_box'): boxes.append(scale['bar_box'])
    margin=int(a.get('margin',3)); mask=np.zeros((d.h,d.w),np.uint8)
    for box in boxes:
        x0,y0,x1,y1=map(lambda v:int(round(v)),box)
        cv2.rectangle(mask,(max(0,x0-margin),max(0,y0-margin)),(min(d.w-1,x1+margin),min(d.h-1,y1+margin)),1,-1)
    d.edit(mask.astype(bool),action='exclude'); return jsonify(state(d))
@app.post('/api/scale')
def scale():
    d=current(); a=request.json; points=a.get('points')
    val=float(a.get('nm_per_pixel') or 0)
    info={'confirmed':True,'source':'direct'}
    if points:
        length=float(np.linalg.norm(np.array(points[1])-points[0])); nm=float(a['nm'])
        if length<=0 or nm<=0: raise ValueError('길이는 양수여야 합니다.')
        val=nm/length; info.update(points=points,length_nm=nm,length_px=length,source='bar')
    if not np.isfinite(val) or val<=0: raise ValueError('nm/px는 양수여야 합니다.')
    info['nm_per_pixel']=val
    if a.get('bar_box'): info['bar_box']=a['bar_box']
    d.push(); d.meta['scale']=info; return jsonify(state(d))
@app.post('/api/review')
def review():
    d=current(); d.meta['reviewed']=bool(request.json['reviewed']); return jsonify(state(d))
@app.get('/api/models')
def models(): return jsonify(files=inventory())
@app.post('/api/sam_load')
def samload():
    a=request.json
    with LOCK: SAM.load(a['backend'],a['checkpoint'],a['model_type'],a['device'])
    return jsonify(ok=True)
@app.post('/api/sam')
def sam():
    d=current(); a=request.json
    with LOCK: mask=SAM.predict(d.image,a.get('points',[]),a.get('roi'),a.get('crop',False),float(a.get('sigma',0)),a.get('batch',False))
    mask &= ~d.exclude; d.edit(mask,int(a['cid'])); return jsonify(state(d))
@app.post('/api/import_mask')
def importmask():
    d=current(); f=request.files['mask']; a=np.asarray(Image.open(f.stream))
    if a.shape!=(d.h,d.w): raise ValueError('원본 크기의 단일 채널 정수 mask가 필요합니다.')
    d.push(); d.labels=a.astype(np.uint16); d.valid[:]=True; d.lines=[]
    for k in np.unique(d.labels):
        if k: d.classes.setdefault(str(int(k)),f'Layer {k}')
    return jsonify(state(d))
@app.get('/api/export')
def export():
    d=current()
    if not d.meta['reviewed']: raise ValueError('사용자 확인 체크 후 GT를 내보내세요. 작업 저장은 언제든 가능합니다.')
    return send_file(io.BytesIO(d.export()),mimetype='application/zip',as_attachment=True,download_name=d.name+'_GT.zip')
@app.get('/api/project')
def project():
    d=current(); return send_file(io.BytesIO(d.project()),mimetype='application/zip',as_attachment=True,download_name=d.name+'_project.zip')
@app.post('/api/demo')
def demo():
    rng=np.random.default_rng(14); h,w=384,640; yy,xx=np.mgrid[:h,:w]
    a=np.where(yy<110+8*np.sin(xx/70),55,np.where(yy<225+8*np.sin(xx/70),155,215)).astype(float)
    a=np.clip(a+rng.normal(0,7,(h,w)),0,255).astype('uint8'); im=Image.fromarray(a).convert('RGB'); dr=ImageDraw.Draw(im)
    from PIL import ImageFont
    try: font=ImageFont.truetype('DejaVuSans.ttf',20)
    except OSError: font=ImageFont.load_default(size=20)
    dr.rectangle((0,305,w,h),fill='black'); dr.line((35,330,235,330),fill='white',width=5); dr.text((70,343),'50 nm',fill='white',font=font); dr.text((350,330),'Sample A-01',fill='white',font=font); dr.text((480,10),'120k',fill='white',font=font)
    d=Document(im,'synthetic_TEM'); key=uuid.uuid4().hex; DOCS[key]=d; return jsonify(id=key)
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8765); p.add_argument('--no-browser',action='store_true'); args=p.parse_args()
    if not args.no_browser: threading.Timer(1,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    app.run(host='127.0.0.1',port=args.port,debug=False,threaded=False)
