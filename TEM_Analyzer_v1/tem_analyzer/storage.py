"""Versioned project state, atomic metadata writes, and lossless masks."""
import json
import os
import tempfile
import uuid
from pathlib import Path
import numpy as np
from PIL import Image

SCHEMA_VERSION = 1
DEFAULT_TEMPLATE = {"id": "default", "name": "기본 템플릿", "scale_roi": [0.02, 0.79, 0.36, 0.99], "text_rois": [[0.63, 0.0, 1.0, 0.15]]}

class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for d in ('images', 'masks'):
            (self.root / d).mkdir(exist_ok=True)
        self.path = self.root / 'project.json'
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding='utf8'))
            if self.state.get('schema_version') != SCHEMA_VERSION:
                raise ValueError('프로젝트 버전이 맞지 않습니다. 마이그레이션이 필요합니다.')
        else:
            self.state = dict(schema_version=SCHEMA_VERSION, images={}, templates={'default': DEFAULT_TEMPLATE.copy()}, selected_template='default', layers=[dict(id=1, name='Layer 1', color='#28dc82')], candidates={}, next_candidate=1, scale={})
            self.save()

    def save(self):
        fd, temp = tempfile.mkstemp(dir=self.root, prefix='project-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def add_image(self, data, name):
        import io
        with Image.open(io.BytesIO(data)) as im:
            im.load(); im = im.convert('RGB')
            if im.width * im.height > 32_000_000: raise ValueError('32 MP 이하의 이미지만 지원합니다.')
            image_id = uuid.uuid4().hex[:12]
            im.save(self.root / 'images' / f'{image_id}.png')
            self.state['images'][image_id] = dict(name=Path(name).name, width=im.width, height=im.height)
            self.state['candidates'][image_id] = []
            self.save()
        return image_id

    def image(self, image_id):
        self.require_image(image_id)
        return np.asarray(Image.open(self.root / 'images' / f'{image_id}.png').convert('RGB'))

    def require_image(self, image_id):
        if image_id not in self.state['images']: raise KeyError('존재하지 않는 이미지')

    def delete_image(self, image_id):
        self.require_image(image_id)
        self.state['images'].pop(image_id)
        self.state['candidates'].pop(image_id, None)
        self.state['scale'].pop(image_id, None)
        self.state.get('preprocessing', {}).pop(image_id, None)
        self.state.get('prepared_prompts', {}).pop(image_id, None)
        (self.root / 'images' / f'{image_id}.png').unlink(missing_ok=True)
        for path in (self.root / 'masks').glob(f'{image_id}_*.png'): path.unlink()
        self.save()

    def mask_path(self, image_id, candidate_id):
        self.require_image(image_id)
        if not str(candidate_id).isdigit(): raise ValueError('잘못된 후보 ID')
        return self.root / 'masks' / f'{image_id}_{candidate_id}.png'

    def put_candidate(self, image_id, mask, source, score=None, parent=None, prompts=None):
        h,w = self.image(image_id).shape[:2]
        mask=np.asarray(mask,bool)
        if mask.shape != (h,w): raise ValueError('마스크 크기가 원본과 다릅니다.')
        candidate_id=self.state['next_candidate'];self.state['next_candidate']+=1
        Image.fromarray(mask.astype('uint8')*255).save(self.mask_path(image_id,candidate_id))
        item=dict(id=candidate_id, source=source, predicted_iou=score, parent=parent, prompts=prompts or {}, layer_id=None, instance_id=None, reviewed=False, visible=True, area=int(mask.sum()))
        self.state['candidates'][image_id].append(item);self.save()
        return item

    def candidate(self,image_id,candidate_id):
        self.require_image(image_id)
        return next((c for c in self.state['candidates'][image_id] if c['id']==int(candidate_id)),None)

    def mask(self,image_id,candidate_id):
        if self.candidate(image_id,candidate_id) is None: raise KeyError('존재하지 않는 후보')
        return np.asarray(Image.open(self.mask_path(image_id,candidate_id)).convert('L'))>0

    def update_template(self,item):
        tid=str(item.get('id','')).strip()
        if not tid or not tid.replace('_','').replace('-','').isalnum(): raise ValueError('템플릿 ID는 영문·숫자·_·-만 사용하세요.')
        def roi(r):
            if len(r)!=4 or not all(isinstance(v,(int,float)) and 0<=v<=1 for v in r) or r[0]>=r[2] or r[1]>=r[3]: raise ValueError('ROI는 정규화 좌표 [x0,y0,x1,y1]이어야 합니다.')
            return [float(v) for v in r]
        clean=dict(id=tid,name=str(item.get('name') or tid),scale_roi=roi(item['scale_roi']) if item.get('scale_roi') is not None else None,text_rois=[roi(r) for r in item.get('text_rois',[])])
        self.state['templates'][tid]=clean;self.state['selected_template']=tid;self.save()
        return clean
