"""Optional human-assisted straight-layer ROI preparation in pixel coordinates.

Not an automatic material classifier or the final metrology rotation. Probability
is inverse-resampled before thresholding; no hard clipping to the prompt box.
"""
import numpy as np
from .metrology import robust_line,rotation_transform,transform_points,warp


def prepare(image,points,box=None,box_margin=0):
    positive=np.asarray([p[:2] for p in points if p[2]==1],float)
    if len(positive)<2:raise ValueError('사전정렬에는 같은 직선층을 따라 양성점 2개 이상이 필요합니다.')
    if not np.isfinite(box_margin) or not 0<=box_margin<=200:raise ValueError('box 여백은 0~200 px입니다. 0이면 자동 box를 만들지 않습니다.')
    if box_margin and box is not None:raise ValueError('수동 box와 자동 좁은 box를 동시에 사용할 수 없습니다. box를 지우거나 여백을 0으로 설정하세요.')
    fit=robust_line(positive)
    if fit['residual_px']>3 or fit['anisotropy']<10:raise ValueError('양성점이 직선층 방향으로 충분히 모이지 않습니다. 점을 재배치하거나 사전정렬을 끄세요.')
    tr=rotation_transform(image.shape,-fit['angle_deg'])
    moved=transform_points([p[:2] for p in points],tr['matrix']);prompt=np.c_[moved,[p[2] for p in points]].tolist()
    aligned_box=None
    if box is not None:
        x0,y0,x1,y1=box;corners=transform_points([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],tr['matrix'])
        aligned_box=np.r_[corners.min(axis=0),corners.max(axis=0)].tolist()
    if box_margin:
        pos=np.asarray([p[:2] for p in prompt if p[2]==1]);aligned_box=np.r_[pos.min(axis=0)-[30,box_margin],pos.max(axis=0)+[30,box_margin]].tolist()
    if aligned_box:
        aligned_box=np.clip(aligned_box,[0,0,0,0],[tr['width'],tr['height'],tr['width'],tr['height']]).tolist()
    rotated=warp(image,tr,order=1,fill=int(np.median(image)))
    support=warp(np.ones(image.shape[:2],np.uint8),tr,order=0)>0
    metadata=dict(method='positive_line',angle_deg=tr['angle_deg'],local_to_aligned=tr['matrix'],aligned_to_local=tr['inverse'],
                  aligned_size=[tr['width'],tr['height']],aligned_box=aligned_box,box_margin_px=float(box_margin),along_margin_px=30 if box_margin else None,
                  fit={k:v for k,v in fit.items() if k!='points'},inverse_sampling='bilinear probability, then model threshold; no prompt-box clipping')
    return rotated,prompt,aligned_box,support,metadata


def restore(probability,support,metadata,original_shape):
    if probability.shape!=support.shape:raise ValueError('사전정렬 확률/지원 영역 크기 불일치')
    prob=np.asarray(probability,float).copy();prob[~support]=0
    # warp expects destination->source; original pixels are the destination here.
    back=dict(inverse=metadata['local_to_aligned'],height=original_shape[0],width=original_shape[1])
    return warp(prob,back,order=1)
