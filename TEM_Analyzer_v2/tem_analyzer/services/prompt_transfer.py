"""Reusable SAM prompts with explicit pixel-centre mapping and optional ECC."""
import copy
import hashlib
import numpy as np
from ..prompts import validate_points
from ..preprocessing import exclusion_mask
from ..algorithms.metrology import transform_points
from .scopes import scope_key


def save_preset(project,iid,key,draft):
    image=project.image(iid);h,w=image.shape[:2];key=scope_key(key)
    auto=draft.get('auto_points',[]);manual=draft.get('manual_points',[]);box=draft.get('box')
    if len(auto)+len(manual)>2048:raise ValueError('프롬프트는 최대 2048개입니다.')
    validate_points(auto,w,h);validate_points(manual,w,h)
    if any(len(p)!=3 or p[2] not in (0,1) for p in manual):raise ValueError('수동점은 [x,y,0 또는 1]입니다.')
    if box is not None and (len(box)!=4 or not np.isfinite(box).all() or not(0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h)):raise ValueError('box 범위 오류')
    mode=draft.get('manual_mode','object')
    if mode not in ('object','independent') or (mode=='independent' and (box or any(p[2]==0 for p in manual))):raise ValueError('독립 양성점 방식에 음성점/box를 넣을 수 없습니다.')
    if not auto and not manual and box is None:raise ValueError('저장할 프롬프트가 없습니다.')
    value=dict(id=key,source_image=iid,source_shape=[h,w],source_sha256=hashlib.sha256(image.tobytes()).hexdigest(),
               draft=copy.deepcopy(dict(auto_points=auto,manual_points=manual,box=box,manual_mode=mode)),
               feature_settings=copy.deepcopy(draft.get('feature_settings',{})))
    project.state.setdefault('prompt_presets',{})[key]=value
    return value


def resize_matrix(shape,size):
    h,w=shape[:2];ww,hh=size;sx,sy=ww/w,hh/h
    return np.array([[sx,0,(sx-1)/2],[0,sy,(sy-1)/2],[0,0,1.]],float)


def transfer_matrix(source,target,method,source_exclude=None,target_exclude=None):
    import cv2
    h,w=target.shape[:2];ratio=min(1,512/max(h,w));size=(max(8,round(w*ratio)),max(8,round(h*ratio)))
    src=resize_matrix(source.shape,size);dst=resize_matrix(target.shape,size);warp=np.eye(3);score=None
    if method in ('ecc','ecc_masked'):
        # ECC assumes the same pixel sampling, NOT the same frame size. Centre-pad
        # the source instead of stretching a rotated/expanded frame anisotropically.
        sh,sw=source.shape[:2];center=np.array([[1,0,(w-sw)/2],[0,1,(h-sh)/2],[0,0,1.]])
        src=dst@center
        gray=source.mean(axis=2).astype('float32')/255
        a=cv2.warpAffine(gray,src[:2].astype('float32'),size,borderValue=float(np.median(gray)))
        b=cv2.resize(target.mean(axis=2).astype('float32')/255,size)
        if a.std()<.005 or b.std()<.005:raise ValueError('정합을 계산할 질감/대비가 부족합니다.')
        ww,hh=size;mask=np.zeros((hh,ww),np.uint8);mask[int(hh*.15):int(hh*.85),int(ww*.15):int(ww*.85)]=255
        if method=='ecc_masked':
            if not hasattr(cv2,'findTransformECCWithMask'):
                raise ValueError('양쪽 제외 ECC에는 findTransformECCWithMask 지원 OpenCV가 필요합니다 (검증 버전 5.0.0). 기존 ECC를 명시적으로 선택하거나 환경 안내를 확인하세요.')
            # Only the central 50% of each frame: footer/canvas padding is not
            # specimen texture. This is a restricted experimental recipe, not
            # general registration or semantic matching of repeated cells.
            mask[:]=0;mask[round(hh*.25):round(hh*.75),round(ww*.25):round(ww*.75)]=255
            sv=np.ones(source.shape[:2],np.uint8)*255 if source_exclude is None else np.uint8(~source_exclude)*255
            tv=np.ones(target.shape[:2],np.uint8)*255 if target_exclude is None else np.uint8(~target_exclude)*255
            am=cv2.warpAffine(sv,src[:2].astype('float32'),size,flags=cv2.INTER_NEAREST)&mask
            bm=cv2.resize(tv,size,interpolation=cv2.INTER_NEAREST)&mask
            for gray,valid in ((a,am),(b,bm)):
                if np.count_nonzero(valid)<max(200,.08*ww*hh) or gray[valid>0].std()<.005:
                    raise ValueError('중앙 유효 영역/질감이 부족해 양쪽 제외 ECC를 적용하지 않았습니다.')
        fits=[]
        for seed in (-10,0,10):
            initial=cv2.getRotationMatrix2D(((ww-1)/2,(hh-1)/2),seed,1).astype('float32')
            try:
                criteria=(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,150,1e-6)
                if method=='ecc_masked':
                    # Coarse-to-fine enlarges the convergence basin for shifts;
                    # a coarse failure never authorizes a weak full-size fit.
                    coarse_ratio=min(1,128/max(size));coarse_size=(max(8,round(ww*coarse_ratio)),max(8,round(hh*coarse_ratio)))
                    scale=resize_matrix(a.shape,coarse_size);seed_matrix=np.eye(3);seed_matrix[:2]=initial
                    coarse_initial=(scale@seed_matrix@np.linalg.inv(scale))[:2].astype('float32')
                    try:
                        coarse_score,coarse=cv2.findTransformECCWithMask(
                            cv2.resize(a,coarse_size,interpolation=cv2.INTER_AREA),cv2.resize(b,coarse_size,interpolation=cv2.INTER_AREA),
                            cv2.resize(am,coarse_size,interpolation=cv2.INTER_NEAREST),cv2.resize(bm,coarse_size,interpolation=cv2.INTER_NEAREST),
                            coarse_initial,cv2.MOTION_EUCLIDEAN,criteria,5)
                        if np.isfinite(coarse_score) and coarse_score>.5 and np.isfinite(coarse).all():
                            seed_matrix[:2]=coarse;initial=(np.linalg.inv(scale)@seed_matrix@scale)[:2].astype('float32')
                    except cv2.error:pass
                    cc,small=cv2.findTransformECCWithMask(a,b,am,bm,initial,cv2.MOTION_EUCLIDEAN,criteria,5)
                else:cc,small=cv2.findTransformECC(a,b,initial,cv2.MOTION_EUCLIDEAN,criteria,mask,5)
                if np.isfinite(small).all() and np.isfinite(cc):fits.append((float(cc),small))
            except cv2.error:continue
        if not fits:raise ValueError('ECC 정합에 실패했습니다. 같은 시야인지 확인하거나 정규화 좌표 방식으로 미리보기 하세요.')
        score,small=max(fits,key=lambda f:f[0])
        if score<.85:raise ValueError(f'ECC 정합 신뢰도가 낮습니다 ({score:.3f}). 좌표를 자동 적용하지 않았습니다.')
        if method=='ecc_masked':
            if abs(np.degrees(np.arctan2(small[1,0],small[0,0])))>20:
                raise ValueError('양쪽 제외 ECC의 작은 회전 검증 범위(±20°) 밖입니다.')
            controls=np.array([[ww*.25,hh*.25,1],[ww*.5,hh*.5,1],[ww*.75,hh*.75,1]])
            if any(cc>=score-.01 and np.linalg.norm(controls@(candidate-small).T,axis=1).max()>5 for cc,candidate in fits):
                raise ValueError('비슷한 ECC 점수의 서로 다른 위치가 있습니다. 반복 셀 정합이 모호해 자동 적용하지 않았습니다.')
        warp[:2]=small
    elif method!='normalized':raise ValueError('재사용 방식은 normalized/ecc/ecc_masked입니다.')
    return np.linalg.inv(dst)@warp@src,None if score is None else float(score)


def preview_preset(project,iid,key,method='normalized'):
    preset=project.state.get('prompt_presets',{}).get(scope_key(key))
    if not preset:raise ValueError('저장한 프롬프트 preset이 없습니다.')
    source=project.image(preset['source_image']);target=project.image(iid)
    if hashlib.sha256(source.tobytes()).hexdigest()!=preset['source_sha256']:raise ValueError('기준 영상이 바뀌었습니다. preset을 다시 저장하세요.')
    ex=exclusion_mask(project,iid)
    matrix,score=transfer_matrix(source,target,method,exclusion_mask(project,preset['source_image']),ex);h,w=target.shape[:2]
    draft=copy.deepcopy(preset['draft']);warnings=['좌표 재사용은 물질 동일성을 보장하지 않습니다. 점·box를 눈으로 확인한 후 SAM을 실행하세요.'];dropped=0
    if method in ('ecc','ecc_masked'):warnings.append('ECC는 같은 pixel sampling의 비슷한 시야·작은 회전/이동용입니다. 배율 차이는 보정하지 않습니다.')
    else:warnings.append('크기 비율 방식은 정합이 아닙니다. 회전·이동을 보정하지 않으므로 점이 다른 셀/물질로 옮겨질 수 있습니다.')
    if method=='ecc_masked':warnings.append('실험적 중앙 50% + 양쪽 제외 ECC입니다. 반복 셀의 잘못된 대응은 높은 상관계수만으로 배제할 수 없습니다. 모든 점 위치를 검토하세요.')
    for name in ('auto_points','manual_points'):
        values=[]
        for p in draft[name]:
            x,y=transform_points([p[:2]],matrix)[0];valid=0<=x<w and 0<=y<h
            valid=valid and not ex[int(y),int(x)]
            if not valid:
                if name=='manual_points':raise ValueError('옮긴 수동점이 영상/유효 영역 밖에 있습니다. 자동 적용하지 않았습니다.')
                dropped+=1;continue
            values.append([float(x),float(y)]+(p[2:] if name=='manual_points' else []))
        draft[name]=values
    if draft['box']:
        x0,y0,x1,y1=draft['box']
        # Box edges are converted to/from pixel-centre coordinates before mapping.
        corners=transform_points(np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])-.5,matrix)+.5
        lo=corners.min(axis=0);hi=corners.max(axis=0)
        if (lo<0).any() or (hi>[w,h]).any():raise ValueError('옮긴 box가 영상 밖입니다. box를 다시 지정하세요.')
        draft['box']=[float(lo[0]),float(lo[1]),float(hi[0]),float(hi[1])]
        if method in ('ecc','ecc_masked'):warnings.append('회전된 box는 축 정렬 외접 box로 변환됩니다.')
    if dropped:warnings.append(f'영상 밖/제외 영역의 자동점 {dropped}개를 제외했습니다.')
    if not draft['auto_points'] and not draft['manual_points'] and draft['box'] is None:raise ValueError('재사용 후 유효 프롬프트가 없습니다.')
    return dict(draft=draft,matrix=matrix.tolist(),method=method,ecc_score=score,warnings=warnings,
                source_image=preset['source_image'],target_image=iid,preset_id=key,inference_run=False)
