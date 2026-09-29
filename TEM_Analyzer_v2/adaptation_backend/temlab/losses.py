import torch
from torch.nn import functional as F
from .abl import ABL


def segmentation_loss(logits, target, valid, abl=None, weight=0.):
    """Input logits Bx1xHxW; target BxHxW bool; valid excludes unannotated pixels."""
    logits=logits.float()
    target=target.float(); valid=valid.bool()
    if not valid.any(): raise ValueError('No valid training pixels')
    bce=F.binary_cross_entropy_with_logits(logits[:,0],target,reduction='none')[valid].mean()
    p=logits[:,0].sigmoid()*valid; t=target*valid
    dice=1-(2*(p*t).sum()+1)/(p.sum()+t.sum()+1)
    edge=logits.sum()*0
    if abl is not None and weight>0 and t.any():
        # softmax([0,z]) == sigmoid(z). One-channel softmax would be invalid.
        two=torch.cat([torch.zeros_like(logits),logits],dim=1)
        labels=target.long().masked_fill(~valid,255)
        edge=abl(two,labels,valid=valid)
    total=bce+dice+weight*edge
    return total,dict(bce=float(bce.detach()),dice_loss=float(dice.detach()),abl=float(edge.detach()),total=float(total.detach()))
