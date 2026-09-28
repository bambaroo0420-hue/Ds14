"""Training-side usage; torch is optional and not needed by the core UI."""
import torch
import torch.nn.functional as F

def masked_losses(semantic_logits,edge_logits,semantic_gt,edge_gt,valid_semantic,valid_edge):
    """Shapes: semantic logits B,C,H,W; all others B,H,W (edge logits can B,1,H,W).
    Read GT and valid PNGs without dividing integer values by 255.
    Apply identical geometric transforms to images, labels, valid masks.
    """
    sem_valid=valid_semantic.bool()
    targets=semantic_gt.long().clone(); targets[~sem_valid]=-100
    sem=F.cross_entropy(semantic_logits,targets,ignore_index=-100,reduction='none')
    sem_loss=sem.sum()/sem_valid.sum().clamp_min(1)
    if edge_logits.ndim==4: edge_logits=edge_logits[:,0]
    edge=F.binary_cross_entropy_with_logits(edge_logits,edge_gt.float(),reduction='none')
    v=valid_edge.to(edge.dtype)
    edge_loss=(edge*v).sum()/v.sum().clamp_min(1)
    return sem_loss,edge_loss
