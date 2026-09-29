"""Per-image region snapshots; original files are never overwritten."""
from copy import deepcopy
import numpy as np
from .operations import excluded, scale_from_points
from .calibration import bar_candidates


def effective_template(project, image_id):
    record=project.state.get('preprocessing',{}).get(image_id,{})
    return record.get('template') or project.state['templates'][project.state['selected_template']]


def model_input(project, image_id):
    image=project.image(image_id)
    record=project.state.get('preprocessing',{}).get(image_id,{})
    if record.get('template') is not None:
        image=image.copy()
        image[excluded(image.shape[:2],record['template'])]=0
    return image


def restrict_mask(project, image_id, mask):
    mask=np.asarray(mask,bool).copy()
    mask[excluded(mask.shape,effective_template(project,image_id))]=False
    return mask


def apply_one(project, image_id, template, regions, scale, length, unit):
    image=project.image(image_id)
    records=project.state.setdefault('preprocessing',{})
    previous=records.get(image_id,{})
    record=deepcopy(previous)
    record.update(reviewed=False,scale_requested=scale,last_error=None)
    if regions:
        record['template']=deepcopy(template)
        record['excluded_pixels']=int(excluded(image.shape[:2],template).sum())
    record['regions_applied']=record.get('template') is not None
    if scale:
        bars=bar_candidates(image,template.get('scale_roi'))
        record.update(scale_status='failed',bar_candidates=bars)
        if bars:
            chosen=bars[0];nm=scale_from_points(*chosen['bar'],length,unit)
            project.state['scale'][image_id]=dict(bar=chosen['bar'],nm_per_px=nm,px_per_nm=1/nm,pixel_length=chosen['pixel_length'],length=length,unit=unit,confirmed=False,source='batch-proposal')
            record['scale_status']='proposed'
        else:
            record['last_error']='바 검출 실패: 양 끝을 직접 지정하고 스케일을 저장하세요. 이전 스케일은 보존했습니다.'
    else:
        record.update(scale_status='not_requested',bar_candidates=[])
    records[image_id]=record
    return record
