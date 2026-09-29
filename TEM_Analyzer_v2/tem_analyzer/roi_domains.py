"""Conservative provenance and validity guards for crop-limited predictions."""
import copy
import numpy as np
from scipy import ndimage as ndi


def candidate_domains(candidate):
    if not candidate:return []
    domains=copy.deepcopy(candidate.get('inference_domains',[]))
    # Older ROI-extract candidates predate explicit provenance. Do not reinterpret
    # ROI edits that merged back into a complete parent as cropped predictions.
    if not domains and candidate.get('source') in ('roi-refine','roi-extract','roi-comparison-crop'):
        roi=candidate.get('prompts',{}).get('roi')
        if roi:domains=[list(roi)]
    return domains


def crop_contacts(mask,domains,near=2):
    """Also catch decoder masks stopping 1-2px short of the crop boundary.

    This is deliberately conservative: a natural endpoint very close to a crop
    also needs a wider inference ROI to distinguish it from a truncated output.
    """
    h,w=mask.shape;cut=np.zeros((h,w),bool)
    for roi in domains:
        if len(roi)!=4 or not np.isfinite(roi).all() or any(float(v)!=int(v) for v in roi):raise ValueError('저장된 추론 ROI 좌표가 잘못되었습니다.')
        x0,y0,x1,y1=map(int,roi)
        if not(0<=x0<x1<=w and 0<=y0<y1<=h):raise ValueError('저장된 추론 ROI 범위가 잘못되었습니다.')
        # Only artificial interior crop edges. True image-frame cuts retain
        # their separate existing frame-endpoint policy.
        if x0>0:cut[y0:y1,x0:min(x1,x0+near+1)]|=mask[y0:y1,x0:min(x1,x0+near+1)]
        if x1<w:cut[y0:y1,max(x0,x1-near-1):x1]|=mask[y0:y1,max(x0,x1-near-1):x1]
        if y0>0:cut[y0:min(y1,y0+near+1),x0:x1]|=mask[y0:min(y1,y0+near+1),x0:x1]
        if y1<h:cut[max(y0,y1-near-1):y1,x0:x1]|=mask[max(y0,y1-near-1):y1,x0:x1]
    return cut


def crop_guard(project,iid,candidates,width=2):
    info=project.state['images'][iid];h,w=info['height'],info['width'];cut=np.zeros((h,w),bool)
    for candidate in candidates:
        domains=candidate_domains(candidate)
        if domains:cut |= crop_contacts(project.mask(iid,candidate['id']),domains)
    return ndi.binary_dilation(cut,iterations=width) if cut.any() and width else cut
