"""Image-specific OCR/scale proposals. Location is a hint, never a fixed crop."""
import re
import numpy as np
from ..operations import detect_scale
from ..calibration import bar_candidates


def propose_annotations(image, words):
    h, w = image.shape[:2]
    clean = [x for x in words if x.get('confidence', 0) >= .25]
    scale = detect_scale(image, [0, 0, 1, 1], clean)
    regions = []

    def add(box, kind, text='', confidence=None,recommended=True,reason=''):
        x0, y0, x1, y1 = box
        pad = max(3, round(h * .003))
        box = [max(0, x0-pad), max(0, y0-pad), min(w, x1+pad), min(h, y1+pad)]
        if box[0] >= box[2] or box[1] >= box[3]:
            return
        regions.append(dict(kind=kind, box=box, roi=[box[0]/w, box[1]/h, box[2]/w, box[3]/h], text=text, confidence=confidence,recommended=recommended,reason=reason))

    if scale.get('bar'):
        bb=scale['bar_box'];tb=scale['text_box']
        add([min(bb[0],tb[0]),min(bb[1],tb[1]),max(bb[2],tb[2]),max(bb[3],tb[3])], 'scale', scale['text'])
    else:
        # Bar-only proposals remain uncalibrated; microscopy structures can look like bars.
        for bar in bar_candidates(image, [0, .65, 1, 1])[:3]:
            add(bar['box'], 'bar_unverified',recommended=False,reason='숫자·단위와 연결되지 않은 바는 구조일 수 있어 기본 비선택')
    text_regions=[]
    for word in clean:
        box, text = word['box'], word['text']
        if scale.get('text_box'):
            s=scale['text_box']
            if s[0]<=box[0] and s[1]<=box[1] and s[2]>=box[2] and s[3]>=box[3]:continue
        if box[1] < h * .35 and re.search(r'\d\s*[kKxX×]|[kK]\s*[xX×]', text):
            kind = 'magnification'
        elif box[1] > h * .60:
            kind = 'footer'
        else:
            kind = 'text'
        text_regions.append(dict(box=list(box),kind=kind,text=text,confidence=word['confidence']))
    # OCR splits a long acquisition footer into words; exclude each text line once.
    merged=[]
    for r in sorted(text_regions,key=lambda r:(r['box'][1],r['box'][0])):
        for prev in merged:
            a,b=prev['box'],r['box'];height=max(a[3]-a[1],b[3]-b[1],1)
            if prev['kind']==r['kind']=='footer' and min(a[3],b[3])-max(a[1],b[1])>height*.4 and max(a[0],b[0])-min(a[2],b[2])<height*5:
                prev['text']+=' '+r['text'];prev['box']=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])];prev['confidence']=min(prev['confidence'],r['confidence']);break
        else:merged.append(r)
    for r in merged:
        a,b,c,d=r['box'];oversized=(d-b)>h*.16 or (c-a)*(d-b)>h*w*.06
        add(r['box'],r['kind'],r['text'],r['confidence'],not oversized,'과대 OCR 박스: 실제 구조 오인 가능, 수동 확인' if oversized else '')
    tpl = {'scale_roi': next((r['roi'] for r in regions if r['kind']=='scale' and r['recommended']), None),
           'text_rois': [r['roi'] for r in regions if r['kind']!='scale' and r['recommended']]}
    return dict(regions=regions, template=tpl, scale=scale, words=clean,
                status='needs_review', warnings=([r['reason'] for r in regions if not r['recommended']] if clean else ['OCR 문자를 찾지 못했습니다. 수동 영역/스케일을 지정하세요.']))
