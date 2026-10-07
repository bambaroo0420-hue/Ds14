from pathlib import Path
import json, hashlib, csv
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, label, maximum_filter
from scipy.signal import correlate2d


def read_image(path):
    a = np.asarray(Image.open(path))
    if a.dtype != np.uint8:
        raise ValueError('Use an explicitly calibrated uint8 image; automatic 16-bit conversion is disabled.')
    return np.array(Image.open(path).convert('RGB'))


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()


def validate_prompt(prompt, shape):
    h,w = shape[:2]
    p=np.asarray(prompt.get('points', []),float).reshape(-1,2)
    labs=np.asarray(prompt.get('labels', []),int)
    if len(p)!=len(labs) or not np.isin(labs,[0,1]).all(): raise ValueError('Point/label mismatch')
    if len(p) and not ((p[:,0]>=0)&(p[:,0]<w)&(p[:,1]>=0)&(p[:,1]<h)).all(): raise ValueError('Point outside image')
    box=prompt.get('box')
    if box is not None:
        x0,y0,x1,y1=box
        if not (0<=x0<x1<w and 0<=y0<y1<h): raise ValueError('Invalid box')
    if box is None and not (labs==1).any(): raise ValueError('A box or a positive point is required')
    return prompt


def translate_prompt(prompt, offset):
    dx,dy=offset
    return dict(box=None if prompt.get('box') is None else (np.asarray(prompt['box'])+[dx,dy,dx,dy]).tolist(),
                points=(np.asarray(prompt['points']).reshape(-1,2)+[dx,dy]).tolist(),labels=list(prompt['labels']))


def bounds(mask, pad=0):
    y,x=np.where(mask)
    if not len(x): raise ValueError('Empty mask: review SAM candidate and prompts')
    h,w=mask.shape
    return [max(0,int(x.min())-pad),max(0,int(y.min())-pad),min(w,int(x.max())+pad+1),min(h,int(y.max())+pad+1)]


def iou(a,b): return float((a&b).sum()/max(1,(a|b).sum()))


def shifted_mask(mask, dx,dy):
    out=np.zeros_like(mask); yy,xx=np.where(mask); xx=xx+int(round(dx));yy=yy+int(round(dy))
    ok=(xx>=0)&(xx<mask.shape[1])&(yy>=0)&(yy<mask.shape[0]);out[yy[ok],xx[ok]]=True
    return out


def align_translation(image, reference_box, offset, radius=20):
    """Local intensity NCC, not a DINO center/physical registration guarantee."""
    g=np.asarray(image,dtype=np.float64).mean(2);x0,y0,x1,y1=map(int,reference_box)
    t=g[y0:y1,x0:x1];th,tw=t.shape;h,w=g.shape
    dx,dy=offset; px=int(round(x0+dx));py=int(round(y0+dy))
    sx=max(0,px-radius);sy=max(0,py-radius);ex=min(w,px+tw+radius);ey=min(h,py+th+radius)
    if ex-sx<tw or ey-sy<th: return np.array(offset,float),float('nan'),True
    a=g[sy:ey,sx:ex];t=t-t.mean(); energy=float((t*t).sum())
    if energy<1e-6: return np.array(offset,float),float('nan'),True
    # scipy correlate in direct mode is costly for large objects; FFT convolution preserves valid coordinates.
    from scipy.signal import fftconvolve
    a=a-a.mean()
    ones=np.ones((th,tw),np.float64);n=th*tw
    sums=fftconvolve(a,ones,mode='valid');squares=fftconvolve(a*a,ones,mode='valid')
    num=fftconvolve(a,t[::-1,::-1],mode='valid')
    variance=squares-sums*sums/n
    valid=variance>max(1e-8,energy*1e-12)
    if not valid.any():return np.array(offset,float),float('nan'),True
    score=np.full(variance.shape,-np.inf)
    score[valid]=np.clip(num[valid]/np.sqrt(variance[valid]*energy),-1.,1.)
    iy,ix=np.unravel_index(score.argmax(),score.shape)
    edge=iy in (0,score.shape[0]-1) or ix in (0,score.shape[1]-1)
    return np.array([sx+ix-x0,sy+iy-y0],float),float(score[iy,ix]),bool(edge)


def joint_boundaries(image, mask, search_px=6, sigma=1., polarity='dark', smooth=.15,
                     thickness=(2,40), min_gradient=.5, parent=None):
    """Ordered upper/lower paths around SAM, for a roughly horizontal, single-valued band.
    Does not bridge missing SAM columns or extrapolate beyond the selected mask.
    Confidence is an engineering threshold, not calibrated probability.
    """
    yy,xx=np.where(mask)
    if len(xx)<4: raise ValueError('Layer mask is empty or too small')
    h,w=mask.shape;cols=np.arange(xx.min(),xx.max()+1)
    runs=[];run=[]
    for x in cols:
        ys=np.flatnonzero(mask[:,x])
        if len(ys): run.append((int(x),int(ys[0]),int(ys[-1])))
        elif run: runs.append(run);run=[]
    if run:runs.append(run)
    gy=np.gradient(gaussian_filter(image.astype(float).mean(2),sigma),axis=0)
    sign=1 if polarity=='dark' else -1
    rows=[]
    for run in runs:
        allstates=[];backs=[];prev=None
        for j,(x,st,sb) in enumerate(run):
            ts=range(max(1,st-search_px),min(h-1,st+search_px+1))
            bs=range(max(1,sb-search_px),min(h-1,sb+search_px+1))
            states=np.array([(t,b) for t in ts for b in bs if thickness[0]<=b-t<=thickness[1]],int)
            if not len(states): raise ValueError('No valid ordered boundary states; change search/thickness limits')
            t,b=states.T;strength=np.minimum(-sign*gy[t,x],sign*gy[b,x])
            cost=sign*(gy[t,x]-gy[b,x])+.02*((t-st)**2+(b-sb)**2)
            if parent is not None: cost += (~parent[t,x] | ~parent[b,x])*1000
            if prev is None: dp=cost;bk=np.full(len(states),-1)
            else:
                delta=states[:,None,:]-prev[None,:,:]
                transition=dp[None,:]+smooth*(delta*delta).sum(2)
                bk=transition.argmin(1);dp=cost+transition[np.arange(len(states)),bk]
            allstates.append(states);backs.append(bk);prev=states
        k=int(dp.argmin());path=[]
        for j in range(len(run)-1,-1,-1):path.append(allstates[j][k]);k=backs[j][k]
        for (x,st,sb),(t,b) in zip(run,path[::-1]):
            s=float(min(-sign*gy[t,x],sign*gy[b,x]));limit=abs(t-st)>=search_px or abs(b-sb)>=search_px
            inside=True if parent is None else bool(parent[t:b+1,x].all())
            rows.append((x,t,b,s,s>=min_gradient and not limit and inside))
    a=np.asarray(rows,float)
    return {'x':a[:,0].astype(int),'top':a[:,1],'bottom':a[:,2],'gradient':a[:,3],'valid':a[:,4].astype(bool)}


def measure_paths(path, nm_per_px=None):
    # Vertical separation is exact for the extracted paths; normal is a local parallel-interface approximation.
    x=path['x'];t=path['top'];b=path['bottom'];v=b-t
    slope=np.gradient((t+b)/2,x) if len(x)>1 else np.zeros_like(v)
    n=v/np.sqrt(1+slope*slope)
    return dict(x=x,top=t,bottom=b,vertical_px=v,normal_approx_px=n,valid=path['valid'],gradient=path['gradient'],
                vertical_nm=v*nm_per_px if nm_per_px else np.full_like(v,np.nan))


def save_overlay(image, masks, paths, output):
    """Original RGB pixels, only raster contour lines added; no contrast change/resizing."""
    from scipy.ndimage import binary_erosion
    a=image.copy()
    for m in masks: a[m ^ binary_erosion(m)]=[0,255,0]
    for p in paths:
        if p is None: continue
        for key,color in [('top',[0,255,255]),('bottom',[255,0,255])]:
            for x,y,ok in zip(p['x'],p[key],p['valid']):a[int(round(y)),int(x)]=color if ok else [255,165,0]
    Image.fromarray(a).save(output)


def export_run(out, image, records, parents, layers, paths, config):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    summaries=[];samples=[]
    for r,pm,lm,path in zip(records,parents,layers,paths):
        ident=r['id'];Image.fromarray(pm.astype('uint8')*255).save(out/f'{ident:03d}_device.png')
        Image.fromarray(lm.astype('uint8')*255).save(out/f'{ident:03d}_layer_sam.png')
        summary=dict(id=ident,status=r.get('status','review'),valid_columns=0,median_vertical_px=None,median_vertical_nm=None)
        if path is not None:
            np.savez_compressed(out/f'{ident:03d}_boundaries.npz',**path)
            m=measure_paths(path,config.get('nm_per_px'));valid=m['valid'];summary['valid_columns']=int(valid.sum())
            if valid.any():
                summary['median_vertical_px']=float(np.median(m['vertical_px'][valid]))
                if config.get('nm_per_px'):summary['median_vertical_nm']=summary['median_vertical_px']*config['nm_per_px']
            for j in range(len(m['x'])):samples.append(dict(id=ident,**{k: v[j].item() for k,v in m.items()}))
        summaries.append(summary)
    for name,rows in [('thickness_summary.csv',summaries),('thickness_per_column.csv',samples)]:
        if rows:
            with (out/name).open('w',newline='',encoding='utf-8-sig') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    reviewed_parents=[m for r,m in zip(records,parents) if r.get('status')!='excluded_by_review']
    save_overlay(image,reviewed_parents,paths,out/'original_with_boundaries.png')
    save_overlay(image,layers,[],out/'original_with_sam_layers.png')
    return summaries
