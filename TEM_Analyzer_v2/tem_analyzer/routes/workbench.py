"""Read-only evidence views and persistent, validated manual-object drafts."""
import copy
import numpy as np
from PIL import Image,ImageDraw,ImageColor
from fastapi.responses import Response
from ..labels import compose,protection,UNKNOWN,UNCERTAIN,EXCLUDED
from ..services.layers import active
from ..services.recipe_groups import validate_groups
from ..services.measurement import alignment_current,measurement_hash
from ..algorithms.metrology import warp


def overlay(project,iid,ids=None,diagnostic=False):
    h,w=project.image(iid).shape[:2];rgba=np.zeros((h,w,4),np.uint8)
    colors={l['id']:ImageColor.getrgb(l['color']) for l in project.state['layers']}
    for c in active(project,iid):
        if ids is not None and c['id'] not in ids:continue
        if ids is None and c['layer_id'] is None:continue
        rgba[project.mask(iid,c['id'])]=[*colors.get(c['layer_id'],(100,220,250)),180]
    if diagnostic:
        labels,valid,conflict=compose(project,iid);yy,xx=np.indices((h,w))
        rgba[labels==UNKNOWN]=[250,210,45,95]
        rgba[labels==UNCERTAIN]=[170,100,240,160]
        rgba[labels==EXCLUDED]=[230,75,140,160]
        rgba[labels==0]=[105,115,130,140]
        rgba[conflict]=[255,40,45,240]
        rgba[protection(project,iid)&((xx+yy)%10<3)]=[255,255,255,230]
    return rgba


def install(app,project):
    from ..v2_api import image_bytes
    def image_response(im):return Response(image_bytes(np.asarray(im)),media_type='image/png')

    @app.get('/api/workbench/{iid}/overlay.png')
    def masks(iid:str,ids:str|None=None,diagnostic:bool=False):
        chosen=None if ids is None else {int(x) for x in ids.split(',') if x}
        if chosen is not None and not chosen.issubset({c['id'] for c in active(project,iid)}):raise ValueError('선택 후보가 변경되었습니다.')
        return image_response(overlay(project,iid,chosen,diagnostic))

    @app.get('/api/workbench/{iid}/audit')
    def audit(iid:str):
        labels,valid,conflict=compose(project,iid);reviewed,review_valid,review_conflict=compose(project,iid,True)
        pending=[c['id'] for c in active(project,iid) if c['layer_id'] is not None and not c.get('reviewed')]
        return dict(image_id=iid,total_pixels=int(labels.size),valid_pixels=int(valid.sum()),unknown_pixels=int((labels==UNKNOWN).sum()),
                    uncertain_pixels=int((labels==UNCERTAIN).sum()),excluded_pixels=int((labels==EXCLUDED).sum()),background_pixels=int((labels==0).sum()),
                    overlap_pixels=int(conflict.sum()),protected_pixels=int(protection(project,iid).sum()),unreviewed_masks=pending,
                    export_valid_pixels=int(review_valid.sum()),full_semantic_ready=bool(valid.any() and not pending and not conflict.any() and not ((labels==UNKNOWN)|(labels==UNCERTAIN)).any()),
                    note='노랑은 모든 미지정 영역입니다. 실제 두 층 사이 틈인지는 A/B 검토가 필요합니다. 제외 픽셀은 학습 valid=0입니다.')

    @app.post('/api/workbench/groups')
    def groups(body:dict):
        iid=body['image_id'];im=project.image(iid);values=validate_groups(body.get('groups',[]),im.shape[1],im.shape[0])
        old=project.state.get('manual_groups',{}).get(iid,[])
        for group in old:
            if not group.get('locked'):continue
            new=next((g for g in values if g['name']==group['name']),None)
            if new is None or {k:v for k,v in new.items() if k!='locked'}!={k:v for k,v in group.items() if k!='locked'}:
                raise ValueError('잠긴 Manual 그룹은 먼저 잠금을 해제하세요.')
        project.state.setdefault('manual_groups',{})[iid]=values
        return {'groups':copy.deepcopy(values)}

    @app.get('/api/workbench/{iid}/rotation.png')
    def rotation(iid:str,aligned:bool=False):
        r=alignment_current(project,iid);im=Image.fromarray(project.image(iid)).convert('RGBA')
        # Draw actual selected reference masks, not arbitrary active-layer context.
        from ..services.measurement import target_masks
        _,_,items,_=target_masks(project,iid,r['config'])
        im=Image.alpha_composite(im,Image.fromarray(overlay(project,iid,{c['id'] for c in items})))
        draw=ImageDraw.Draw(im);f=r['fit'];pts=np.asarray(f.get('points',[]));radius=max(1,min(im.size)//240)
        for index,p in enumerate(pts):
            weight=f.get('weights',[1]*len(pts))[index];color='lime' if weight>=.5 else 'red'
            draw.ellipse((p[0]-radius,p[1]-radius,p[0]+radius,p[1]+radius),fill=color)
        if len(pts)>1:
            center=np.asarray(f.get('center',pts.mean(axis=0)));d=np.asarray(f.get('direction',[np.cos(np.radians(f['angle_deg'])),np.sin(np.radians(f['angle_deg']))]))
            t=(pts-center)@d;a=center+d*t.min();b=center+d*t.max();draw.line([tuple(a),tuple(b)],fill='cyan',width=max(2,radius))
        if r.get('used_roi'):draw.rectangle((np.array(r['used_roi'])*[im.width,im.height,im.width,im.height]).tolist(),outline='yellow',width=2)
        if aligned:im=Image.fromarray(warp(np.asarray(im.convert('RGB')),r['transform'],order=1))
        return image_response(im)

    @app.get('/api/workbench/{iid}/measurement.png')
    def measurement(iid:str,row:int=-1,aligned:bool=True):
        m=project.state.get('measurements',{}).get(iid)
        if not m or m['input_hash']!=measurement_hash(project,iid):raise ValueError('최신 계측 결과가 없습니다. 다시 계측하세요.')
        im=Image.fromarray(project.image(iid)).convert('RGBA')
        im=Image.alpha_composite(im,Image.fromarray(overlay(project,iid,set(m['candidate_ids']))))
        if aligned:im=Image.fromarray(warp(np.asarray(im.convert('RGB')),m['transform'],order=1))
        draw=ImageDraw.Draw(im);rows=m['rows']
        if row>=len(rows) or row < -1:raise ValueError('계측 행 범위 오류')
        values=[(row,rows[row])] if row>=0 else list(enumerate(rows))[::max(1,len(rows)//150)]
        for index,r in values:
            pts=r.get('aligned_endpoints' if aligned else 'original_endpoints')
            if not pts:continue
            color='cyan' if r['status']=='ok' else 'red';draw.line([tuple(p) for p in pts],fill=color,width=2)
            for x,y in pts:draw.ellipse((x-3,y-3,x+3,y+3),outline='yellow',width=1)
            if row>=0:draw.text(tuple(pts[0]),f" #{index+1} {r.get('raw_length_nm',0):.3f} nm {r['status']}",fill='white',stroke_width=1,stroke_fill='black')
        return image_response(im)
