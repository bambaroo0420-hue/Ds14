"""Pure image and mask operations; no web framework or SAM dependency."""
import re
import numpy as np
from PIL import Image, ImageDraw

def roi_pixels(roi,w,h):
    return (max(0,int(roi[0]*w)),max(0,int(roi[1]*h)),min(w,int(roi[2]*w)),min(h,int(roi[3]*h)))

def excluded(shape,template):
    h,w=shape; out=np.zeros((h,w),bool)
    for roi in [template.get('scale_roi')]+template['text_rois']:
        if roi is None: continue
        x0,y0,x1,y1=roi_pixels(roi,w,h);out[y0:y1,x0:x1]=True
    return out

def brush(mask,strokes):
    im=Image.fromarray((np.asarray(mask,bool)*255).astype('uint8'))
    for s in strokes:
        points=[tuple(map(float,p)) for p in s['points']]
        if not points:continue
        radius=max(1,min(200,int(s.get('radius',5))))
        color=255 if s.get('mode')=='add' else 0
        draw=ImageDraw.Draw(im)
        if len(points)>1:draw.line(points,fill=color,width=2*radius,joint='curve')
        for x,y in points:draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
    return np.asarray(im)>0

def scale_from_points(a,b,length,unit='nm'):
    length=float(length)
    if not np.isfinite(length) or length<=0 or unit not in ('nm','um','µm'):raise ValueError('양의 길이와 nm/um 단위를 입력하세요.')
    if len(a)!=2 or len(b)!=2 or not np.isfinite([a,b]).all():raise ValueError('바 양 끝 좌표를 확인하세요.')
    d=float(np.linalg.norm(np.asarray(a,float)-np.asarray(b,float)))
    if d<2:raise ValueError('스케일바 양 끝이 너무 가깝습니다.')
    return length*(1000 if unit!='nm' else 1)/d

def detect_scale(image,roi,words):
    """Suggest a horizontal bright bar with nearby OCR text; user must confirm."""
    from .calibration import bar_candidates
    candidates=bar_candidates(image,roi)
    if not candidates:return dict(words=words,bar=None,nm_per_px=None,confirmed=False)
    length=None;unit=None
    for item in words:
        match=re.search(r'(\d+(?:[.,]\d+)?)\s*(nm|µm|um)',item['text'],re.I)
        if match:length=float(match.group(1).replace(',','.'));unit=match.group(2).lower();break
    bar=candidates[0]['bar']
    nm=scale_from_points(*bar,length,unit) if length else None
    return dict(words=words,bar=bar,nm_per_px=nm,px_per_nm=1/nm if nm else None,length=length,unit=unit,confirmed=False,source='ocr-proposal')

def layer_coverage(project,image_id):
    h,w=project.image(image_id).shape[:2]
    coverage=np.zeros((h,w),np.uint16)
    overlap=np.zeros((h,w),bool)
    for item in project.state['candidates'][image_id]:
        if item['layer_id'] is None:continue
        mask=project.mask(image_id,item['id'])
        overlap|=mask&(coverage!=0)
        coverage[mask]=int(item['layer_id'])
    return coverage,overlap
