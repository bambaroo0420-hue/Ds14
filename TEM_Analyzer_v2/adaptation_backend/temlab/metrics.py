import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment


def overlap(pred,gt,valid):
    p=pred&valid; g=gt&valid
    inter=(p&g).sum(); union=(p|g).sum()
    return dict(iou=float(inter/union) if union else 1.,
                dice=float(2*inter/(p.sum()+g.sum())) if p.sum()+g.sum() else 1.)


def boundary_metrics(pred,gt,valid,tolerance=2.):
    # Ignore outer image edge and a 1px band around unlabelled pixels.
    safe=ndi.binary_erosion(valid,structure=np.ones((3,3)),border_value=0)
    p=(pred&~ndi.binary_erosion(pred))&safe
    g=(gt&~ndi.binary_erosion(gt))&safe
    if not p.any() or not g.any():
        return dict(boundary_f1=0.,mean_boundary_distance_px=None)
    dg=ndi.distance_transform_edt(~g); dp=ndi.distance_transform_edt(~p)
    precision=float((dg[p]<=tolerance).mean()); recall=float((dp[g]<=tolerance).mean())
    f=2*precision*recall/(precision+recall) if precision+recall else 0.
    return dict(boundary_f1=float(f),mean_boundary_distance_px=float((dg[p].mean()+dp[g].mean())/2))


def filter_candidates(probabilities,cfg):
    candidates=[]
    threshold=cfg['mask_threshold']; delta=cfg['stability_delta']
    for index,p in enumerate(probabilities):
        mask=p>=threshold
        if mask.sum()<cfg['min_pred_area']: continue
        lo=(p>=max(0.,threshold-delta)).sum(); hi=(p>=min(1.,threshold+delta)).sum()
        stability=float(hi/max(lo,1))
        if stability<cfg['min_stability']: continue
        candidates.append(dict(mask=mask,stability=stability,prompt_index=index))
    candidates.sort(key=lambda c:(-c['stability'],c['prompt_index']))
    kept=[]
    # Mask-IoU NMS rather than box NMS: nested thin layers may share bounding boxes.
    for c in candidates:
        duplicate=False
        for k in kept:
            a,b=c['mask'],k['mask']; union=(a|b).sum()
            if (a&b).sum()/max(union,1)>cfg['nms_iou']: duplicate=True; break
        if not duplicate: kept.append(c)
    return kept


def candidate_metrics(candidates,gt_targets,valid,cfg):
    n,m=len(candidates),len(gt_targets)
    matrix=np.zeros((n,m),np.float64)
    for i,c in enumerate(candidates):
        for j,(_,gt) in enumerate(gt_targets): matrix[i,j]=overlap(c['mask'],gt,valid)['iou']
    threshold=cfg['match_iou']
    matches={}
    if n and m:
        # Maximize number of passing matches first, then IoU as tie-break.
        rr,cc=linear_sum_assignment(-((matrix>=threshold)*(min(n,m)+1)+matrix))
        matches={int(j):int(i) for i,j in zip(rr,cc) if matrix[i,j]>=threshold}
    tp=len(matches); fp=n-tp; fn=m-tp
    details=[]
    for j,(cls,gt) in enumerate(gt_targets):
        best=int(matrix[:,j].argmax()) if n else None
        i=matches.get(j)
        row=dict(class_id=int(cls),gt_index=j,area_px=int(gt.sum()),matched=i is not None,
                 best_iou=float(matrix[best,j]) if n else 0.,matched_iou=float(matrix[i,j]) if i is not None else 0.)
        if i is not None: row.update(boundary_metrics(candidates[i]['mask'],gt,valid,cfg['boundary_tolerance_px']))
        else: row.update(boundary_f1=0.,mean_boundary_distance_px=None)
        details.append(row)
    summary=dict(tp=tp,fp=fp,fn=fn,gt_regions=m,candidates=n,
                 region_precision=tp/n if n else None,region_recall=tp/m if m else None,
                 region_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                 mean_best_iou=float(np.mean([x['best_iou'] for x in details])) if details else None,
                 boundary_f1_all_gt=float(np.mean([x['boundary_f1'] for x in details])) if details else None)
    small=[x for x in details if x['area_px']<=cfg['small_region_area_px']]
    summary['small_region_recall']=sum(x['matched'] for x in small)/len(small) if small else None
    d=[x['mean_boundary_distance_px'] for x in details if x['mean_boundary_distance_px'] is not None]
    summary['boundary_distance_matched_px']=float(np.mean(d)) if d else None
    return summary,details
