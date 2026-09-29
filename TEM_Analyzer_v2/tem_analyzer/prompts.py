"""Prompt preparation only: no SAM inference. ML uses local unsupervised k-means."""
import numpy as np
from scipy import ndimage as ndi
from scipy.cluster.vq import kmeans2, vq

def validate_points(points, width, height):
    out=[]
    for p in points:
        if len(p)<2 or not np.isfinite(p[:2]).all(): raise ValueError('유효하지 않은 prompt 좌표')
        x,y=map(float,p[:2])
        if not (0<=x<width and 0<=y<height): raise ValueError('prompt가 이미지 밖에 있습니다.')
        out.append([x,y])
    return out

def grid_points(shape, grid, excluded):
    h,w=shape
    if not 2<=int(grid)<=32:raise ValueError('Grid는 2~32입니다.')
    return [[float(x*w),float(y*h)] for y in (np.arange(grid)+.5)/grid for x in (np.arange(grid)+.5)/grid if not excluded[min(h-1,int(y*h)),min(w-1,int(x*w))]]

def ml_points(image, excluded, existing, count=12, clusters=5, min_distance=12):
    """Cluster intensity/local texture at <=256 px and pick interior component centers.
    This does not identify material classes and has no externally trained model.
    """
    from PIL import Image
    h,w=image.shape[:2];scale=min(1.,256/max(h,w));ww=max(1,round(w*scale));hh=max(1,round(h*scale))
    g=np.asarray(Image.fromarray(image).convert('L').resize((ww,hh)),dtype=np.float32)/255
    allowed=~np.asarray(Image.fromarray(excluded.astype('uint8')).resize((ww,hh),Image.Resampling.NEAREST),bool)
    mean=ndi.gaussian_filter(g,2);std=np.sqrt(np.maximum(ndi.gaussian_filter(g*g,2)-mean*mean,0))
    grad=np.hypot(ndi.sobel(mean,axis=0),ndi.sobel(mean,axis=1))
    features=np.stack([mean,std,grad],-1);samples=features[allowed]
    if len(samples)<clusters: return []
    spread=np.maximum(samples.std(0),.01);features=features/spread
    rng=np.random.default_rng(42);sample=features[allowed];sample=sample[rng.choice(len(sample),min(12000,len(sample)),replace=False)]
    k=min(clusters,len(np.unique(sample,axis=0)))
    if k<1:return []
    centers,_=kmeans2(sample,k,iter=20,minit='++',seed=42)
    labels=vq(features.reshape(-1,3),centers)[0].reshape(hh,ww)
    options=[]
    for c in range(k):
        cc,n=ndi.label((labels==c)&allowed)
        for label,region in enumerate(ndi.find_objects(cc),1):
            if region is None:continue
            sub=cc[region];component=(sub==label)
            if component.sum()<8:continue
            dist=ndi.distance_transform_edt(np.pad(component,1))[1:-1,1:-1]
            y,x=np.unravel_index(dist.argmax(),dist.shape)
            py=region[0].start+y;px=region[1].start+x
            options.append((float(dist[y,x]),(px+.5)*w/ww,(py+.5)*h/hh))
    chosen=[];others=[p[:2] for p in existing]
    for score,x,y in sorted(options,reverse=True):
        if excluded[min(h-1,int(y)),min(w-1,int(x))]:continue
        if any(np.hypot(x-p[0],y-p[1])<min_distance for p in others):continue
        chosen.append([float(x),float(y)]);others.append([x,y])
        if len(chosen)>=count:break
    return chosen

