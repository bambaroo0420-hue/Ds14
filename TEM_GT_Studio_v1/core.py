"""Original-resolution TEM annotation and normal-profile dynamic programming."""
from __future__ import annotations
import io, json, re, zipfile, copy
from pathlib import Path
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from PIL import Image
from skimage.segmentation import slic, find_boundaries


def png(a):
    b=io.BytesIO(); Image.fromarray(a).save(b,format='PNG'); return b.getvalue()


def resample(points, closed=False, step=1.0):
    p=np.asarray(points,dtype=float)
    if closed and np.linalg.norm(p[0]-p[-1])>1e-6: p=np.vstack([p,p[0]])
    keep=np.r_[True,np.linalg.norm(np.diff(p,axis=0),axis=1)>1e-6]; p=p[keep]
    if len(p)<2: raise ValueError('경계점이 두 개 이상 필요합니다.')
    d=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    t=np.linspace(0,d[-1],max(2,int(np.ceil(d[-1]/step))+1))
    out=np.column_stack([np.interp(t,d,p[:,i]) for i in range(2)])
    return out[:-1] if closed else out


def normal_dp(gray, points, width=8, continuity=.15, sigma=1., contrast=0., closed=False, valid=None):
    """Dense candidates, no displacement penalty. Exact cyclic closure for closed paths."""
    p=resample(points,closed); h,w=gray.shape
    smooth=ndi.gaussian_filter1d(p,2,axis=0,mode='wrap' if closed else 'nearest')
    tangent=np.roll(smooth,-1,axis=0)-np.roll(smooth,1,axis=0) if closed else np.gradient(smooth,axis=0)
    n=np.column_stack([-tangent[:,1],tangent[:,0]])
    n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-8)
    offsets=np.arange(-int(width),int(width)+1,dtype=float)
    xy=p[:,None,:]+offsets[None,:,None]*n[:,None,:]
    g=ndi.gaussian_filter(gray.astype(float),sigma) if sigma else gray.astype(float)
    gy,gx=np.gradient(g)
    def sample(a,q): return ndi.map_coordinates(a,[q[...,1],q[...,0]],order=1,mode='nearest')
    score=np.abs(sample(gx,xy)*n[:,0,None]+sample(gy,xy)*n[:,1,None])
    if contrast:
        q=n[:,None,:]*2
        c=np.abs(sample(g,xy+q)-sample(g,xy-q))
        score=score/(np.percentile(score,95)+1e-6)+contrast*c/(np.percentile(c,95)+1e-6)
    else: score/=np.percentile(score,95)+1e-6
    feasible=(xy[...,0]>=0)&(xy[...,0]<=w-1)&(xy[...,1]>=0)&(xy[...,1]<=h-1)
    if valid is not None: feasible &= sample(valid.astype(float),xy)>.999
    # Entirely excluded profiles stay at the initial position and require review.
    border=(p[:,0]<=0)|(p[:,0]>=w-1)|(p[:,1]<=0)|(p[:,1]>=h-1)
    feasible[border]=False
    missing=~feasible.any(axis=1)
    feasible[missing,len(offsets)//2]=True
    score[missing]=0; score[~feasible]=-1e9
    raw=score.argmax(axis=1); k=len(offsets)
    if continuity==0:
        chosen=raw
    else:
        penalty=continuity*np.abs(offsets[:,None]-offsets[None,:])
        def solve(start=None):
            costs=-score[0].copy()
            if start is not None:
                costs[:]=1e15; costs[start]=-score[0,start]
            trace=np.zeros((len(p),k),dtype=np.int16)
            for i in range(1,len(p)):
                c=costs[:,None]+penalty
                trace[i]=c.argmin(axis=0)
                costs=c.min(axis=0)-score[i]
            if start is not None: costs+=penalty[:,start]
            end=int(costs.argmin()); value=costs[end]
            seq=np.empty(len(p),int); seq[-1]=end
            for i in range(len(p)-1,0,-1): seq[i-1]=trace[i,seq[i]]
            return value,seq
        if closed:
            chosen=min((solve(j) for j in range(k) if feasible[0,j]),key=lambda x:x[0])[1]
        else: chosen=solve()[1]
    refined=xy[np.arange(len(p)),chosen]
    return {'initial':p.tolist(),'peak':xy[np.arange(len(p)),raw].tolist(),
            'points':refined.tolist(),'closed':bool(closed),'review_profiles':int(missing.sum()),
            'settings':{'width':width,'continuity':continuity,'sigma':sigma,'contrast':contrast}}


def semantic_center(labels,valid):
    e=np.zeros(labels.shape,bool)
    e[:,:-1]|=(labels[:,:-1]!=labels[:,1:]) & valid[:,:-1] & valid[:,1:]
    e[:-1,:]|=(labels[:-1,:]!=labels[1:,:]) & valid[:-1,:] & valid[1:,:]
    return e

def semantic_edges(labels,valid):
    # One raster side per class transition; then radius-1 disk (Euclidean) dilation.
    e=semantic_center(labels,valid)
    safe=ndi.binary_erosion(valid,iterations=1,border_value=0)
    edge=ndi.binary_dilation(e,structure=ndi.generate_binary_structure(2,1)) & safe
    return edge.astype(np.uint8),safe.astype(np.uint8)


class Document:
    def __init__(self,image,name='image'):
        self.image=np.asarray(image.convert('RGB'))
        self.name=Path(name).stem; self.h,self.w=self.image.shape[:2]
        self.labels=np.zeros((self.h,self.w),np.uint16)
        self.valid=np.zeros((self.h,self.w),bool)
        self.exclude=np.zeros((self.h,self.w),bool)
        self.classes={'1':'Layer A','2':'Layer B','3':'Passivation'}
        self.lines=[]; self.meta={'scale':None,'ocr':[],'reviewed':False}
        self.sp=None; self.preview=None; self.history=[]; self.future=[]
    def snapshot(self):
        return (self.labels.copy(),self.valid.copy(),self.exclude.copy(),copy.deepcopy(self.lines),copy.deepcopy(self.meta),copy.deepcopy(self.classes))
    def restore(self,s):
        self.labels,self.valid,self.exclude,self.lines,self.meta,self.classes=copy.deepcopy(s); self.preview=None
    def push(self):
        self.history.append(self.snapshot()); self.history=self.history[-15:]; self.future=[]; self.meta['reviewed']=False
    def undo(self,redo=False):
        src,dst=(self.future,self.history) if redo else (self.history,self.future)
        if src: dst.append(self.snapshot()); self.restore(src.pop())
    def edit(self,mask,cid=1,action='paint'):
        self.push()
        if action=='exclude': self.exclude[mask]=True
        elif action=='include': self.exclude[mask]=False
        elif action=='unlabel': self.valid[mask]=False
        else: self.labels[mask]=cid; self.valid[mask]=True
        self.lines=[] # prevent stale centerline export after semantic changes
    def superpixels(self,roi=None,size=24,compactness=.1,sigma=1):
        x0,y0,x1,y1=roi or [0,0,self.w,self.h]
        x0,y0=max(0,int(x0)),max(0,int(y0)); x1,y1=min(self.w,int(x1)),min(self.h,int(y1))
        if x1-x0<3 or y1-y0<3: raise ValueError('ROI가 너무 작습니다.')
        gray=cv2.cvtColor(self.image[y0:y1,x0:x1],cv2.COLOR_RGB2GRAY)/255.
        result=slic(gray,n_segments=max(2,int(gray.size/max(4,size)**2)),compactness=max(.001,compactness),sigma=sigma,channel_axis=None,start_label=1)
        self.sp=np.zeros((self.h,self.w),np.int32); self.sp[y0:y1,x0:x1]=result
        return find_boundaries(self.sp,mode='inner')
    def refine(self,cid=1,line=None,roi=None,**settings):
        gray=cv2.cvtColor(self.image,cv2.COLOR_RGB2GRAY)
        good=~self.exclude
        if line:
            paths=[normal_dp(gray,line,closed=False,valid=good,**settings)]
            self.preview={'paths':paths,'cid':cid,'roi':roi,'kind':'line'}
        else:
            mask=(self.labels==cid)&self.valid
            contours,hierarchy=cv2.findContours(mask.astype(np.uint8),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
            if not contours: raise ValueError('선택한 층의 mask가 없습니다.')
            paths=[]
            for i,c in enumerate(contours):
                if len(c)<6: continue
                path=normal_dp(gray,c[:,0,:],closed=True,valid=good,**settings)
                path['hole']=bool(hierarchy[0,i,3]>=0); paths.append(path)
            if not paths: raise ValueError('보정 가능한 경계가 없습니다.')
            self.preview={'paths':paths,'cid':cid,'kind':'mask'}
        return self.preview
    def accept(self,other=0):
        if not self.preview: raise ValueError('보정 미리보기를 먼저 실행하세요.')
        prev=self.preview; self.push(); cid=prev['cid']
        if prev['kind']=='line':
            roi=prev.get('roi')
            if not roi: raise ValueError('계면선 분할에는 ROI가 필요합니다.')
            x0,y0,x1,y1=map(int,roi); p=np.array(prev['paths'][0]['points'])
            t=np.gradient(p,axis=0); normal=np.column_stack([-t[:,1],t[:,0]])
            yy,xx=np.mgrid[y0:y1,x0:x1]; q=np.column_stack([xx.ravel(),yy.ravel()])
            _,idx=cKDTree(p).query(q); signed=((q-p[idx])*normal[idx]).sum(axis=1)
            region=self.labels[y0:y1,x0:x1]; allowed=((region==cid)|(region==other)|~self.valid[y0:y1,x0:x1])&~self.exclude[y0:y1,x0:x1]
            new=np.where(signed.reshape(region.shape)>=0,cid,other)
            region[allowed]=new[allowed]; self.valid[y0:y1,x0:x1][allowed]=True
        else:
            new=np.zeros((self.h,self.w),np.uint8)
            for hole in (False,True):
                for path in prev['paths']:
                    if path['hole']==hole:
                        cv2.fillPoly(new,[np.rint(path['points']).astype(np.int32)],0 if hole else 1)
            old=(self.labels==cid)&self.valid
            # Explicit adjacent class fills relinquished pixels; do not invent a class.
            self.labels[old & ~new.astype(bool) & ~self.exclude]=other
            target=new.astype(bool)&~self.exclude
            self.labels[target]=cid; self.valid[target]=True
        self.lines=copy.deepcopy(prev['paths']); self.preview=None
    def export(self):
        effective=self.valid&~self.exclude
        edge,ev=semantic_edges(self.labels,effective)
        # Preserve canonical raster interfaces shared by semantic classes.
        canonical=[]
        for cid in np.unique(self.labels[effective]):
            if cid==0: continue
            cs,_=cv2.findContours(((self.labels==cid)&effective).astype(np.uint8),cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
            for c in cs:
                if len(c)>2: canonical.append({'class_id':int(cid),'points':c[:,0,:].tolist(),'closed':True,'note':'raster outline; ignore edges require valid_edge mask'})
        b=io.BytesIO(); name=re.sub(r'[^\w.-]','_',self.name)
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            for folder,a in [('images',self.image),('semantic_gt',self.labels),('edge_gt',edge),('boundary_center',semantic_center(self.labels,effective).astype(np.uint8)),('valid_semantic',effective.astype(np.uint8)),('valid_edge',ev)]: z.writestr(f'{folder}/{name}.png',png(a))
            meta=copy.deepcopy(self.meta); meta.update(classes=self.classes,shape=[self.h,self.w],original_coordinates=True,edge_radius=1,edge_kernel='cross / Euclidean disk radius 1',label_values={'edge':[0,1],'valid':[0,1]},unannotated_pixels=int((~self.valid).sum()))
            z.writestr(f'metadata/{name}.json',json.dumps(meta,ensure_ascii=False,indent=2))
            z.writestr(f'centerlines/{name}.json',json.dumps({'refined_paths':self.lines,'raster_outlines':canonical},ensure_ascii=False))
            z.writestr('README.txt','Semantic/edge/valid PNGs share original dimensions. Use valid masks in BOTH loss and metrics. edge=1 is positive (not 255). Unannotated pixels are NOT background GT. Raster outline segments at ignore/image borders must be excluded using valid_edge. Refined paths are pre-rasterization coordinates.\n')
        return b.getvalue()
    def project(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            for n,a in [('image',self.image),('labels',self.labels),('valid',self.valid.astype('uint8')),('exclude',self.exclude.astype('uint8'))]: z.writestr(n+'.png',png(a))
            z.writestr('project.json',json.dumps({'version':1,'name':self.name,'classes':self.classes,'lines':self.lines,'meta':self.meta},ensure_ascii=False))
        return b.getvalue()
    @classmethod
    def load(cls,data):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist())>512*1024**2: raise ValueError('프로젝트가 너무 큽니다.')
            info=json.loads(z.read('project.json')); d=cls(Image.open(io.BytesIO(z.read('image.png'))),info['name'])
            for n,typ in [('labels',np.uint16),('valid',bool),('exclude',bool)]:
                a=np.asarray(Image.open(io.BytesIO(z.read(n+'.png')))).astype(typ)
                if a.shape!=(d.h,d.w): raise ValueError('프로젝트 크기 불일치')
                setattr(d,n,a)
            d.classes=info['classes']; d.lines=info['lines']; d.meta=info['meta']; return d


def recognize(image,model_dir='models/easyocr',language='en'):
    from ocr_adapter import read_words
    words=read_words(image,model_dir,language)
    return match_scale_bars(image,words)


def match_scale_bars(image,words):
    # Recognized line boxes normally contain "50 nm". Also handle split number/unit boxes.
    groups=[[word] for word in words if word['confidence']>=20 and word['text'].strip()]
    for a in words:
        if a['confidence']<20 or not re.fullmatch(r'\d+(?:[.,]\d+)?',a['text'].strip()): continue
        ax0,ay0,ax1,ay1=a['box']; ah=max(1,ay1-ay0)
        for b in words:
            if b['confidence']<20 or not re.fullmatch(r'(?:nm|um|µm|μm)',b['text'].strip(),re.I): continue
            bx0,by0,bx1,by1=b['box']
            if -.25*ah<=bx0-ax1<=3*ah and abs((by0+by1-ay0-ay1)/2)<=.7*max(ah,by1-by0): groups.append([a,b])
    scales=[]
    for group in groups:
        s=' '.join(v['text'] for v in group).replace('μ','u').replace('µ','u')
        m=re.search(r'(\d+(?:[.,]\d+)?)\s*(nm|um)\b',s,re.I)
        if m:
            box=[min(v['box'][0] for v in group),min(v['box'][1] for v in group),max(v['box'][2] for v in group),max(v['box'][3] for v in group)]
            scales.append({'nm':float(m[1].replace(',','.'))*(1000 if m[2].lower()=='um' else 1),'box':box,'text':s})
    gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY); bars=[]
    for inv in [False,True]:
        _,bw=cv2.threshold(gray,0,255,(cv2.THRESH_BINARY_INV if inv else cv2.THRESH_BINARY)|cv2.THRESH_OTSU)
        opened=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(12,image.shape[1]//100)),np.uint8))
        cs,_=cv2.findContours(opened,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for c in cs:
            x,y,w,h=cv2.boundingRect(c)
            if w>=20 and w>6*h and h<=max(20,image.shape[0]*.025):
                bars.append({'points':[[x,y+(h-1)/2],[x+w-1,y+(h-1)/2]],'box':[x,y,x+w,y+h],'px':w-1})
    candidates=[]
    for scale in scales:
        sx=(scale['box'][0]+scale['box'][2])/2; sy=(scale['box'][1]+scale['box'][3])/2
        for bar in bars:
            bx=(bar['box'][0]+bar['box'][2])/2; by=(bar['box'][1]+bar['box'][3])/2
            dist=np.hypot(sx-bx,sy-by)
            if dist<max(100,image.shape[1]*.15): candidates.append({**bar,'nm':scale['nm'],'nm_per_pixel':scale['nm']/bar['px'],'distance':float(dist),'text':scale['text']})
    return {'words':words,'candidates':sorted(candidates,key=lambda c:c['distance'])[:8]}
