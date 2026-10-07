"""Pure image and mask operations; no web framework or SAM dependency."""
import re
import numpy as np
from PIL import Image, ImageDraw

def roi_pixels(roi,w,h):
    return (max(0,int(roi[0]*w)),max(0,int(roi[1]*h)),min(w,int(roi[2]*w)),min(h,int(roi[3]*h)))

def excluded(shape,template):
    h,w=shape; out=np.zeros((h,w),bool)
    for roi in [template.get(k) for k in ('scale_roi','scale_text_roi','sample_roi','magnification_roi')]+template.get('text_rois',[]):
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
    from .calibration import bar_candidates
    bars=bar_candidates(image,roi);pairs=[]
    clean=[dict(x,text=x['text'].replace('μ','u').replace('µ','u')) for x in words if x.get('confidence',1)>=.2]
    groups=list(clean)
    for a in clean:
        if not re.fullmatch(r'\d+(?:[.,]\d+)?',a['text'].strip()):continue
        for b in clean:
            if not re.fullmatch(r'(?:nm|um)',b['text'].strip(),re.I):continue
            ax,ay,ar,ab=a['box'];bx,by,br,bb=b['box'];h=max(ab-ay,bb-by,1)
            if -h*.25<=bx-ar<=h*3 and abs((ay+ab-by-bb)/2)<h*.7:
                groups.append(dict(text=a['text']+' '+b['text'],box=[ax,min(ay,by),br,max(ab,bb)],confidence=min(a['confidence'],b['confidence'])))
    for word in groups:
        # A material thickness label such as 'TaOx ~ 7 nm' is NOT a scale label.
        match=re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(nm|um)\s*',word['text'],re.I)
        if not match:continue
        length=float(match[1].replace(',','.'));unit=match[2].lower()
        if length<=0:continue
        tx0,ty0,tx1,ty1=word['box'];tx=(tx0+tx1)/2;ty=(ty0+ty1)/2
        for bar in bars:
            a,b=bar['bar'];cx=(a[0]+b[0])/2;cy=(a[1]+b[1])/2
            # Never calibrate from a text glyph's short horizontal stroke.
            bx0,by0,bx1,by1=bar['box'];text_height=max(1,ty1-ty0)
            # CRAFT may merge a label and the bar into one tall OCR rectangle.
            # Only shorten its effective text height when a long rectangular bar
            # sits below the rectangle's midpoint; glyph strokes still fail width.
            if by0>ty0+text_height*.55 and bx1-bx0>=(tx1-tx0)*.65:
                text_height=max(1,min(text_height,by0-ty0))
            overlap=max(0,min(tx1,bx1)-max(tx0,bx0))*max(0,min(ty1,by1)-max(ty0,by0))
            # OCR boxes include padding and an axis-aligned box may overlap a
            # tilted bar. Permit the bottom margin, never the middle of text.
            if overlap>(tx1-tx0)*text_height*.4 or cy<ty0+text_height*.75 or bar['pixel_length']<max(12,text_height*2,(tx1-tx0)*.65):continue
            # Default acquisition layout: label above and horizontally near bar.
            if ty>cy+max(4,ty1-ty0) or abs(tx-cx)>max(bar['pixel_length'],30) or abs(ty-cy)>max(80,image.shape[0]*.12):continue
            distance=float(np.hypot(tx-cx,ty-cy));nm=scale_from_points(a,b,length,unit)
            pairs.append(dict(bar=bar['bar'],bar_box=bar['box'],pixel_length=bar['pixel_length'],nm_per_px=nm,px_per_nm=1/nm,length=length,unit=unit,text=word['text'],text_box=word['box'],distance=distance))
    pairs.sort(key=lambda p:p['distance'])
    unique=[]
    for p in pairs:
        if not any(p['bar']==q['bar'] and p['length']==q['length'] and p['unit']==q['unit'] for q in unique):unique.append(p)
    return dict(words=words,candidates=unique,**(unique[0] if unique else {'bar':None,'nm_per_px':None}),confirmed=False,source='ocr-proposal',ambiguous=len(unique)>1)

def layer_coverage(project,image_id):
    from .labels import compose,EXCLUDED
    labels,valid,overlap=compose(project,image_id)
    labels=labels.copy();labels[labels>=EXCLUDED]=0
    return labels,overlap
