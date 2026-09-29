"""Scale-bar proposals in original pixels. Proposals always require inspection."""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from .operations import roi_pixels


def bar_candidates(image, roi):
    h, w = image.shape[:2]
    if roi is None or len(roi) != 4 or not all(np.isfinite(roi)) or not (0 <= roi[0] < roi[2] <= 1 and 0 <= roi[1] < roi[3] <= 1):
        raise ValueError('스케일 ROI를 드래그하세요.')
    x0, y0, x1, y1 = roi_pixels(roi, w, h)
    gray = np.asarray(Image.fromarray(image).convert('L'))[y0:y1, x0:x1]
    if gray.size == 0 or np.ptp(gray) < 10:
        return []
    lo, hi = float(gray.min()), float(gray.max())
    result = []
    # Both white-on-black and black-on-white bars. Connected rectangular runs
    # reject text glyphs and the full ROI background; no fabricated fallback.
    for polarity, binary in [('bright', gray >= lo + .75*(hi-lo)), ('dark', gray <= lo + .25*(hi-lo))]:
        labels, _ = ndi.label(binary)
        for label, region in enumerate(ndi.find_objects(labels), 1):
            if region is None:
                continue
            sy, sx = region
            width, height = sx.stop-sx.start, sy.stop-sy.start
            if width < 8 or width < 2*height:
                continue
            if sx.start == 0 and sx.stop == gray.shape[1]:
                continue
            ys,xs=np.nonzero(labels[region]==label)
            pts=np.column_stack([xs,ys]).astype(float);center=pts.mean(axis=0)
            eig,vec=np.linalg.eigh(np.cov(pts.T));axis=vec[:,-1]
            if axis[0]<0:axis=-axis
            if abs(np.degrees(np.arctan2(axis[1],axis[0])))>20:continue
            normal=np.array([-axis[1],axis[0]]);along=(pts-center)@axis;across=(pts-center)@normal
            length=float(np.ptp(along)+np.abs(axis).sum())
            thickness=float(np.ptp(across)+np.abs(normal).sum())
            fill=float(len(pts)/(length*thickness))
            if length<5*thickness or thickness>max(12,gray.shape[0]*.04) or fill<.55:continue
            center+=np.array([x0+sx.start,y0+sy.start])
            # Horizontal bounds retain the original pixel-interval convention.
            if abs(axis[1])<1e-8:
                bar=[[float(x0+sx.start),float(center[1])],[float(x0+sx.stop),float(center[1])]];length=float(width)
            else:
                bar=[(center+axis*(float(along.min())-.5)).tolist(),(center+axis*(float(along.max())+.5)).tolist()]
                length=float(np.linalg.norm(np.array(bar[1])-bar[0]))
            result.append(dict(bar=bar,pixel_length=length,polarity=polarity,fill=fill,
                               box=[float(x0+sx.start),float(y0+sy.start),float(x0+sx.stop),float(y0+sy.stop)]))
    return sorted(result, key=lambda c: c['pixel_length']*c['fill'], reverse=True)[:20]

