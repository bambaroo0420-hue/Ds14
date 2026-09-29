"""Versioned metadata, immutable masks, persistent undo and recoverable deletion."""
import copy, json, os, tempfile, uuid, shutil, time
from pathlib import Path
import numpy as np
from PIL import Image

SCHEMA_VERSION=2
DEFAULT_TEMPLATE={'id':'default','name':'기본 템플릿','scale_roi':[.02,.79,.36,.99],'text_rois':[[.63,0,1,.15]]}

def atomic_json(path,value):
    path=Path(path);fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

class Project:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        for d in ('images','masks','logits','trash'):(self.root/d).mkdir(exist_ok=True)
        self.path=self.root/'project.json'
        if self.path.exists():
            self.state=json.loads(self.path.read_text(encoding='utf8'))
            if self.state.get('schema_version')==1:
                shutil.copy2(self.path,self.root/f'project.v1.backup.{time.time_ns()}.json')
                self.state['schema_version']=2
            elif self.state.get('schema_version')!=2:raise ValueError('지원하지 않는 프로젝트 버전')
        else:
            self.state=dict(schema_version=2,images={},templates={'default':copy.deepcopy(DEFAULT_TEMPLATE)},selected_template='default',layers=[dict(id=1,name='Layer 1',color='#28dc82',locked=False)],candidates={},next_candidate=1,scale={})
        for key,default in [('preprocessing',{}),('prepared_prompts',{}),('runs',[]),('history',[]),('future',[]),('revision',0),('protected',{}),('annotations',{}),('mask_scopes',{})]:self.state.setdefault(key,default)
        self.state.setdefault('legacy_templates_enabled',False)
        for iid,items in self.state['candidates'].items():
            for c in items:c.setdefault('active',True);c.setdefault('deleted',False)
            self.state['preprocessing'].setdefault(iid,{'template':copy.deepcopy(self.state['templates'][self.state['selected_template']]),'reviewed':False})
        self.recover_deletions();self.save()
    def save(self):atomic_json(self.path,self.state)
    def snapshot(self):return copy.deepcopy({k:v for k,v in self.state.items() if k not in ('history','future','runs','jobs')})
    def checkpoint(self,action):
        self.state['history'].append({'action':action,'state':self.snapshot()});self.state['history']=self.state['history'][-20:];self.state['future']=[]
        self.state['revision']+=1
    def undo(self,redo=False):
        src='future' if redo else 'history';dst='history' if redo else 'future'
        if not self.state[src]:raise ValueError('되돌릴 작업이 없습니다.')
        before=self.snapshot();entry=self.state[src].pop();self.state[dst].append({'action':entry['action'],'state':before})
        keep={k:self.state[k] for k in ('history','future','runs','jobs') if k in self.state};next_id=self.state['next_candidate'];revision=self.state['revision']+1
        self.state=entry['state'];self.state.update(keep,next_candidate=max(next_id,self.state['next_candidate']),revision=revision);self.save()
        return {'action':entry['action'],'revision':revision}
    def add_image(self,data,name):
        import io
        with Image.open(io.BytesIO(data)) as src:
            if src.width*src.height>32_000_000:raise ValueError('32 MP 이하만 지원합니다.')
            if src.mode not in ('RGB','RGBA','L','P'):raise ValueError('8-bit RGB/회색 이미지를 사용하세요. 고비트 원본은 명시적으로 변환하세요.')
            im=src.convert('RGB');iid=uuid.uuid4().hex[:12];im.save(self.root/'images'/f'{iid}.png')
            self.state['images'][iid]=dict(name=Path(name).name,width=im.width,height=im.height)
        self.state['candidates'][iid]=[]
        self.state['preprocessing'][iid]={'template':{'scale_roi':None,'text_rois':[]},'reviewed':False,'regions_applied':False}
        self.state['history']=[];self.state['future']=[];self.state['revision']+=1;self.save();return iid
    def require_image(self,iid):
        if iid not in self.state['images']:raise KeyError('존재하지 않는 이미지')
    def image(self,iid):
        self.require_image(iid)
        with Image.open(self.root/'images'/f'{iid}.png') as im:return np.array(im.convert('RGB'),copy=True)
    def recover_deletions(self):
        for journal in (self.root/'trash').glob('*/journal.json'):
            info=json.loads(journal.read_text())
            if info['image_id'] in self.state['images']:
                for rel in info['files']:
                    src=journal.parent/rel;dst=self.root/rel
                    if src.exists():dst.parent.mkdir(parents=True,exist_ok=True);os.replace(src,dst)
                journal.unlink()
    def delete_image(self,iid):
        self.require_image(iid);before=copy.deepcopy(self.state)
        paths=[self.root/'images'/f'{iid}.png']
        for folder in ('masks','logits'):paths+=list((self.root/folder).glob(f'{iid}_*'))
        paths=[p for p in paths if p.exists()];trash=self.root/'trash'/uuid.uuid4().hex;trash.mkdir()
        metadata={k:copy.deepcopy(self.state.get(k,{}).get(iid)) for k in ('images','candidates','scale','preprocessing','prepared_prompts','protected','annotations','alignments','measurements','annotation_proposals','gt_reviews','mask_scopes','prompt_transfers')}
        atomic_json(trash/'journal.json',{'image_id':iid,'files':[str(p.relative_to(self.root)) for p in paths],'metadata':metadata,'created':time.time()})
        moved=[]
        try:
            for p in paths:
                dst=trash/p.relative_to(self.root);dst.parent.mkdir(parents=True,exist_ok=True);os.replace(p,dst);moved.append((p,dst))
            for key in metadata:self.state.get(key,{}).pop(iid,None)
            self.state['history']=[];self.state['future']=[];self.state['revision']+=1;self.save()
        except Exception:
            self.state=before
            for p,dst in reversed(moved):
                if dst.exists():os.replace(dst,p)
            raise
    def restore_deleted(self,trash_id):
        if not str(trash_id).isalnum():raise ValueError('잘못된 휴지통 ID')
        folder=self.root/'trash'/trash_id
        info=json.loads((folder/'journal.json').read_text(encoding='utf8'))
        iid=info['image_id']
        if iid in self.state['images']:raise ValueError('이미 복원한 이미지입니다.')
        if not info.get('metadata'):raise ValueError('구버전 휴지통은 수동 복원이 필요합니다.')
        for rel in info['files']:
            src=(folder/rel).resolve();dst=(self.root/rel).resolve()
            if not src.is_relative_to(folder.resolve()) or not dst.is_relative_to(self.root):raise ValueError('휴지통 경로 오류')
            if not src.is_file() or dst.exists():raise ValueError('복원 파일 누락 또는 대상 충돌')
        # Copy first, then atomically publish metadata; trash remains a recovery source.
        for rel in info['files']:shutil.copy2(folder/rel,self.root/rel)
        for key,value in info['metadata'].items():
            if value is not None:self.state.setdefault(key,{})[iid]=value
        self.state['history']=[];self.state['future']=[];self.state['revision']+=1;self.save()
        (folder/'journal.json').unlink()
        return iid
    def mask_path(self,iid,cid):
        self.require_image(iid)
        if not str(cid).isdigit():raise ValueError('잘못된 후보 ID')
        return self.root/'masks'/f'{iid}_{cid}.png'
    def put_candidate(self,iid,mask,source,score=None,parent=None,prompts=None,**extra):
        self.require_image(iid);info=self.state['images'][iid];m=np.asarray(mask,bool)
        if m.shape!=(info['height'],info['width']):raise ValueError('마스크 크기가 원본과 다릅니다.')
        cid=self.state['next_candidate'];self.state['next_candidate']+=1
        Image.fromarray(m.astype('uint8')*255).save(self.mask_path(iid,cid))
        item=dict(id=cid,source=source,predicted_iou=score,parent=parent,prompts=prompts or {},layer_id=None,instance_id=None,reviewed=False,visible=True,active=True,deleted=False,area=int(m.sum()),**extra)
        self.state['candidates'][iid].append(item);self.save();return item
    def candidate(self,iid,cid):
        self.require_image(iid)
        return next((c for c in self.state['candidates'][iid] if c['id']==int(cid) and not c.get('deleted')),None)
    def mask(self,iid,cid):
        if self.candidate(iid,cid) is None:raise KeyError('존재하지 않는 후보')
        with Image.open(self.mask_path(iid,cid)) as im:return np.array(im.convert('L'))>0
    def locked(self,lid):return bool(next((x.get('locked',False) for x in self.state['layers'] if x['id']==lid),False))
    def assert_editable(self,item):
        if item and self.locked(item.get('layer_id')):raise ValueError('잠긴 레이어는 수정할 수 없습니다.')
    def invalidate(self,iid,reason):
        for c in self.state['candidates'][iid]:c.update(reviewed=False,stale_reason=reason)
        self.state['preprocessing'].setdefault(iid,{})['reviewed']=False
        self.state['revision']+=1
    def update_template(self,item):
        tid=str(item.get('id','')).strip()
        if not tid or not tid.replace('_','').replace('-','').isalnum():raise ValueError('템플릿 ID 오류')
        def roi(r):
            if len(r)!=4 or not all(np.isfinite(v) and 0<=v<=1 for v in r) or r[0]>=r[2] or r[1]>=r[3]:raise ValueError('정규화 ROI 오류')
            return list(map(float,r))
        clean=dict(id=tid,name=str(item.get('name') or tid),scale_roi=roi(item['scale_roi']) if item.get('scale_roi') else None,text_rois=[roi(r) for r in item.get('text_rois',[])])
        for k in ('scale_text_roi','sample_roi','magnification_roi'):
            if item.get(k):clean[k]=roi(item[k])
        self.state['templates'][tid]=clean;self.state['selected_template']=tid;self.save();return clean
