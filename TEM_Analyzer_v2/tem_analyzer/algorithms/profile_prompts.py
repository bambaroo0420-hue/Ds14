"""Model-free transverse profiles: propose interiors of opposed edge pairs.

These are independent positive points, not material labels or SAM mask seeds.
"""
import numpy as np
from scipy import ndimage as ndi
from scipy.signal import find_peaks


def profile_proposals(gray,allowed,cfg,ratio):
    h,w=gray.shape;image=gray.astype(float)
    if min(h,w)<2 or not allowed.any():
        return [],np.zeros_like(allowed),dict(angle_deg=None,opposed_edge_pairs=0),['프로파일을 계산할 유효 영상 영역이 부족합니다.']
    smoothed=ndi.gaussian_filter(image,3);gy,gx=np.gradient(smoothed)
    energy=gx*gx+gy*gy;safe=ndi.binary_erosion(allowed,iterations=4,border_value=0)
    weight=float(energy[safe].sum())
    z=np.sum(energy[safe]*np.exp(2j*(np.arctan2(gy[safe],gx[safe])+np.pi/2))) / max(weight,1e-12)
    coherence=float(abs(z));angle=float(np.degrees(np.angle(z))/2)
    meta=dict(angle_source='tensor' if cfg.profile_angle is None else 'manual',tensor_coherence=coherence,
              scans=cfg.profile_scans,opposed_edge_pairs=0,analysis_pixel_units=True)
    warnings=[];edge_map=np.zeros_like(allowed)
    if cfg.profile_angle is None and (weight<1e-8 or coherence<.12):
        meta['angle_deg']=None
        return [],edge_map,meta,['층 방향이 약하거나 여러 방향입니다. 프로파일 방향을 직접 지정하거나 Grid/다른 추가점 방식을 사용하세요.']
    if cfg.profile_angle is not None:angle=cfg.profile_angle
    meta['angle_deg']=angle
    if cfg.profile_angle is None:warnings.append(f'프로파일 자동 방향 {angle:.2f}° (coherence {coherence:.3f}); 물질 경계 정답/회전 확정이 아닙니다.')
    tangent=np.array([np.cos(np.deg2rad(angle)),np.sin(np.deg2rad(angle))]);normal=np.array([-tangent[1],tangent[0]])
    yy,xx=np.nonzero(allowed);xy=np.c_[xx,yy];center=np.array([(w-1)/2,(h-1)/2])
    t=(xy-center)@tangent;n=(xy-center)@normal
    scans=np.linspace(*np.quantile(t,[.15,.85]),cfg.profile_scans)
    coordinates=np.arange(np.floor(n.min()),np.ceil(n.max())+1)
    minimum=max(2.,cfg.profile_min_width*ratio,2*cfg.edge_clearance*ratio)
    maximum=cfg.profile_max_width*ratio
    proposals=[]
    for scan in scans:
        # Five parallel samples reduce local texture without rotating/resampling the source file.
        paths=center+coordinates[:,None]*normal[None,:]+(scan+np.arange(-2,3))[:,None,None]*tangent[None,None,:]
        pos=np.moveaxis(paths[...,::-1],-1,0)
        ok=ndi.map_coordinates(allowed.astype(float),pos,order=0,mode='constant',cval=0)>0
        vals=ndi.map_coordinates(image,pos,order=1,mode='constant',cval=0)
        count=ok.sum(axis=0);good=count>=3
        profile=(vals*ok).sum(axis=0)/np.maximum(count,1)
        labels,_=ndi.label(good)
        for region in ndi.find_objects(labels):
            span=region[0]
            if span.stop-span.start<6:continue
            signal=ndi.gaussian_filter1d(profile[span],cfg.profile_smooth,mode='nearest')
            derivative=np.gradient(signal)
            peaks,properties=find_peaks(abs(derivative),prominence=cfg.profile_prominence,distance=2)
            for first,second in zip(peaks[:-1],peaks[1:]):
                width=float(second-first)
                if derivative[first]*derivative[second]>=0 or not minimum<=width<=maximum:continue
                start=float(coordinates[span.start+first]);end=float(coordinates[span.start+second]);mid=(start+end)/2
                point=center+scan*tangent+mid*normal
                x,y=point
                if not (0<=x<w and 0<=y<h and allowed[int(y),int(x)]):continue
                # Favor a narrow, two-sided contrast interval, not the widest EDT basin.
                score=float(min(abs(derivative[first]),abs(derivative[second]))/np.sqrt(width))
                proposals.append((score,float(x),float(y)))
                for v in (start,end):
                    ep=center+scan*tangent+v*normal;ix,iy=np.rint(ep).astype(int)
                    if 0<=ix<w and 0<=iy<h:edge_map[iy,ix]=True
    meta['opposed_edge_pairs']=len(proposals)
    warnings.append('프로파일 점은 밝기 변화 구간의 후보입니다. 결정 격자·구멍·문자도 후보가 될 수 있으며 SAM/마스크 검수가 필요합니다.')
    return proposals,edge_map,meta,warnings
