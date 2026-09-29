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
            fill = float((labels[region] == label).mean())
            if width < 8 or width < 5*height or height > max(12, gray.shape[0]*.15) or fill < .8:
                continue
            if sx.start == 0 and sx.stop == gray.shape[1]:
                continue
            y = y0 + (sy.start+sy.stop-1)/2
            # Edges bound the occupied pixel intervals, so a 100-pixel bar is 100 px.
            bar = [[float(x0+sx.start), float(y)], [float(x0+sx.stop), float(y)]]
            result.append(dict(bar=bar, pixel_length=width, polarity=polarity, fill=fill))
    return sorted(result, key=lambda c: c['pixel_length']*c['fill'], reverse=True)[:20]
