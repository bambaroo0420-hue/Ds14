"""Geometry utilities; all coordinates are original-image (x,y) pixels."""
import io
import numpy as np
from scipy import ndimage as ndi
from PIL import Image
from matplotlib.figure import Figure

def read_image(data):
    with Image.open(io.BytesIO(data)) as im:
        if im.width*im.height > 24_000_000:
            raise ValueError('이미지가 24 MP를 넘습니다. 관심 영역을 원본 해상도로 잘라 사용하세요.')
        if im.mode in ('I','F') or im.mode.startswith('I;16'):
            raise ValueError('이 버전은 8-bit JPG/PNG/RGB TIFF를 지원합니다. 16-bit 원본은 별도 변환 기준을 정하세요.')
        return np.asarray(im.convert('RGB')).copy()


def gray(rgb):
    a=np.asarray(rgb,dtype=np.float32)
    return a/255 if a.ndim==2 else (a[...,0]*.299+a[...,1]*.587+a[...,2]*.114)/255


def denoise(rgb,method='off',sigma=1.2,sigma_space=2.,sigma_color=.08):
    a=gray(rgb)
    if method=='off': return a
    if method=='gaussian':
        if not 0 < sigma <= 15: raise ValueError('Gaussian sigma 범위: 0 초과 ~ 15 px')
        return ndi.gaussian_filter(a,float(sigma),mode='reflect')
    if method!='bilateral': raise ValueError('알 수 없는 필터')
    if not .1<=sigma_space<=4 or not .001<=sigma_color<=1:
        raise ValueError('bilateral: space 0.1~4 px, color 0.001~1 (정규화 밝기)')
    # Finite support 3 sigma, explicit bilateral weights. Memory O(image pixels).
    r=int(np.ceil(3*sigma_space)); pad=np.pad(a,r,mode='reflect')
    acc=np.zeros_like(a); weight=np.zeros_like(a); h,w=a.shape
    for dy in range(-r,r+1):
        for dx in range(-r,r+1):
            b=pad[r+dy:r+dy+h,r+dx:r+dx+w]
            ww=np.exp(-(dx*dx+dy*dy)/(2*sigma_space*sigma_space)-(b-a)**2/(2*sigma_color*sigma_color))
            acc+=ww*b;weight+=ww
    return acc/np.maximum(weight,1e-10)


def mask_contours(mask):
    if not np.any(mask): raise ValueError('빈 마스크입니다.')
    # Contouring on padded original resolution. Do not use pyplot/global GUI state.
    fig=Figure();ax=fig.subplots()
    cc=ax.contour(np.pad(np.asarray(mask,float),1),levels=[.5])
    out=[s-1 for s in cc.allsegs[0] if len(s)>5]
    fig.clear()
    if not out: raise ValueError('마스크 경계를 찾지 못했습니다.')
    return out


def resample(line,spacing=2.):
    p=np.asarray(line,float);lens=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    keep=np.r_[True,np.diff(lens)>1e-7];p=p[keep];lens=lens[keep]
    if len(p)<2 or lens[-1]<4:raise ValueError('계면 구간이 너무 짧습니다. 최소 4 px 이상 선택하세요.')
    n=min(2500,max(3,int(np.ceil(lens[-1]/spacing))+1));s=np.linspace(0,lens[-1],n)
    return np.c_[np.interp(s,lens,p[:,0]),np.interp(s,lens,p[:,1])]

