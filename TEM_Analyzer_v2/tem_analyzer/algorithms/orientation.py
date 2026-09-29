"""Experimental image-direction proposal; NOT a semantic layer boundary fit."""
import numpy as np
from scipy import ndimage as ndi


def image_direction(image,excluded,roi=None):
    import cv2
    h,w=image.shape[:2]
    if max(h,w)>2048:raise ValueError('영상 방향 보조 추정은 2048 px 이하 입력/크롭을 사용하세요.')
    gray=image.astype(float).mean(axis=2)
    # Suppress publication arrows/colored guides and frame, plus OCR exclusions.
    guard=np.asarray(excluded,bool)|ndi.binary_dilation(np.ptp(image.astype(float),axis=2)>35,iterations=5)
    guard=ndi.binary_dilation(guard,iterations=8)
    border=max(4,round(min(h,w)*.012));guard[:border]=True;guard[-border:]=True;guard[:,:border]=True;guard[:,-border:]=True
    if roi:
        if len(roi)!=4 or not (0<=roi[0]<roi[2]<=1 and 0<=roi[1]<roi[3]<=1):raise ValueError('방향 추정 ROI는 0~1 box입니다.')
        x0,y0,x1,y1=(np.array(roi)*[w,h,w,h]).astype(int)
        keep=np.zeros((h,w),bool);keep[y0:y1,x0:x1]=True;guard|=~keep
    blurred=ndi.gaussian_filter(gray,4)
    edges=cv2.Canny(np.uint8(np.clip(blurred,0,255)),10,25);edges[guard]=0
    lines=cv2.HoughLinesP(edges,1,np.pi/720,25,minLineLength=max(20,round(min(h,w)*.10)),maxLineGap=15)
    if lines is None:raise ValueError('방향을 지지하는 직선이 부족합니다. 레이어 경계/기준점 모드를 사용하세요.')
    lines=np.asarray(lines).reshape(-1,4).astype(float);delta=lines[:,2:]-lines[:,:2]
    lengths=np.linalg.norm(delta,axis=1);angles=(np.degrees(np.arctan2(delta[:,1],delta[:,0]))+90)%180-90
    histogram,bins=np.histogram(angles,bins=np.linspace(-90,90,181),weights=lengths)
    peak=float(bins[np.argmax(ndi.gaussian_filter1d(histogram,2,mode='wrap'))]+.5)
    difference=abs((angles-peak+90)%180-90);selected=difference<=5
    support=float(lengths[selected].sum()/max(lengths.sum(),1))
    if selected.sum()<3 or support<.30:raise ValueError('여러 방향이 섞여 영상 방향을 신뢰하기 어렵습니다. ROI를 좁히거나 기준점을 지정하세요.')
    z=np.sum(lengths[selected]*np.exp(2j*np.deg2rad(angles[selected])))/lengths[selected].sum()
    angle=float(np.degrees(np.angle(z))/2)
    spread=float(np.sqrt(np.average(((angles[selected]-angle+90)%180-90)**2,weights=lengths[selected])))
    low=ndi.gaussian_filter(gray,8);gy,gx=np.gradient(low);weights=gx*gx+gy*gy
    keep=~ndi.binary_dilation(guard,iterations=8)
    if not keep.any() or weights[keep].sum()<1e-8:raise ValueError('방향 검증에 사용할 유효 영상이 부족합니다.')
    tangent=np.arctan2(gy,gx)+np.pi/2
    tensor=np.sum(weights[keep]*np.exp(2j*tangent[keep]))/weights[keep].sum()
    tensor_angle=float(np.degrees(np.angle(tensor))/2);agreement=float(abs((tensor_angle-angle+90)%180-90))
    best=lines[selected][np.argmax(lengths[selected])].reshape(2,2).tolist()
    return dict(angle_deg=angle,residual_px=None,anisotropy=None,points=best,
                method='masked Gaussian+Canny+Hough consensus, cross-checked by coarse structure tensor',
                line_count=int(selected.sum()),support_fraction=support,angular_spread_deg=spread,
                tensor_angle_deg=tensor_angle,tensor_coherence=float(abs(tensor)),agreement_deg=agreement,
                reliable_proposal=bool(abs(tensor)>.15 and agreement<8 and spread<3),
                note='영상 주 방향입니다. 선택 레이어의 실제 경계를 검증한 것이 아니며 결정 격자·화살표·잔여 문자에 영향받을 수 있습니다.')
