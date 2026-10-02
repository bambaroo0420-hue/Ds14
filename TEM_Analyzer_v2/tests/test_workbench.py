import copy
import io
from unittest.mock import patch
import numpy as np
from PIL import Image
from test_workflow import WorkflowTest
from tem_analyzer.services.prompt_transfer import save_preset,preview_preset
from tem_analyzer.services.prompt_batches import prepare_transfer,confirm_transfers,transfer_signature,run_transferred


class WorkbenchTests(WorkflowTest):
    def test_roi_automatic_staging_accept_and_stale_guard(self):
        mask=np.zeros((40,50),bool);mask[5:35,5:45]=1;item=dict(mask=mask,score=.9,stability=.99)
        with patch.object(self.api.model,'automatic',return_value=[item]):
            r=self.client.post('/api/sam/roi-auto/preview',json=dict(image_id=self.id,roi=[10,10,60,50],grid=2));self.assertEqual(r.status_code,200,r.text)
        token=r.json()['token'];self.assertEqual(len(self.api.project.state['candidates'][self.id]),0)
        r=self.client.get('/api/roi-auto/'+token+'.png');self.assertEqual(r.status_code,200)
        r=self.client.post('/api/sam/roi-auto/accept',json={'image_id':'wrong','token':token,'indices':[0]});self.assertEqual(r.status_code,400)
        self.assertEqual(len(self.api.project.state['candidates'][self.id]),0)
        r=self.client.post('/api/sam/roi-auto/accept',json={'image_id':self.id,'token':token,'indices':[0]});self.assertEqual(r.status_code,200,r.text)
        mask=self.api.project.mask(self.id,r.json()['created'][0]['id']);self.assertEqual(int(mask.sum()),1200);self.assertFalse(mask[:10].any())
        r=self.client.post('/api/sam/roi-auto/accept',json={'token':token,'indices':[0]});self.assertEqual(r.status_code,400)
        self.api.project.state['preprocessing'][self.id]['sam_filter']={'enabled':True}
        self.assertEqual(self.client.get('/api/roi-auto/'+token+'.png').status_code,400)

    def test_local_ocr_retry_maps_to_original_and_manual_box(self):
        words=[dict(text='5 nm',box=[2,3,15,10],confidence=.9)]
        with patch('tem_analyzer.ocr.read_words',return_value=words):
            r=self.client.post('/api/workflow/annotations/detect',json={'image_id':self.id,'retry_roi':[.25,.5,.75,1]});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['words'][0]['box'],[22,33,35,40])
        r=self.client.post('/api/workflow/annotations/manual-box',json={'image_id':self.id,'roi':[.1,.1,.3,.3],'kind':'scale'});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['regions'][-1]['box'],[8,6,24,18]);self.assertNotIn(self.id,self.api.project.state['scale'])

    def groups(self):return [dict(name='Manual 1',points=[[25,25,1]],box=None,roi=None),dict(name='Manual 2',points=[[50,35,1],[55,40,0]],box=[40,25,65,50],roi=[.4,.3,.9,.9])]

    def test_layer_auto_color_and_rename_preserves_color(self):
        c=self.client;p=self.api.project
        c.post('/api/layers',json={});self.assertNotEqual(p.state['layers'][0]['color'],p.state['layers'][1]['color'])
        r=c.post('/api/layers',json={'id':2,'color':'#112233'});self.assertEqual(r.status_code,200,r.text)
        c.post('/api/layers',json={'id':2,'name':'changed'});self.assertEqual(p.state['layers'][1]['color'],'#112233')

    def test_groups_save_lock_and_restart(self):
        c=self.client;groups=self.groups();groups[0]['locked']=True
        r=c.post('/api/workbench/groups',json={'image_id':self.id,'groups':groups});self.assertEqual(r.status_code,200,r.text)
        groups=r.json()['groups'];groups[0]['points']=[[26,25,1]]
        r=c.post('/api/workbench/groups',json={'image_id':self.id,'groups':groups});self.assertEqual(r.status_code,400,r.text)
        groups[0]['points']=[[25,25,1]];groups[0]['locked']=False
        self.assertEqual(c.post('/api/workbench/groups',json={'image_id':self.id,'groups':groups}).status_code,200)
        from tem_analyzer.storage import Project
        self.assertEqual(len(Project(self.temp.name).state['manual_groups'][self.id]),2)

    def test_prepared_groups_are_independent_and_roi_in_pixels(self):
        mask=np.zeros((60,80),bool);mask[20:40,20:60]=1;item=dict(mask=mask,score=.9,stability=.99)
        with patch.object(self.api.model,'prompt',return_value=item) as manual,patch.object(self.api.model,'in_roi',return_value=item) as roi:
            r=self.client.post('/api/sam/prepared',json={'image_id':self.id,'manual_groups':self.groups()})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['count'],2)
            self.assertEqual(manual.call_count,1);self.assertEqual(roi.call_count,1)
            np.testing.assert_allclose(roi.call_args.args[1],[32,18,72,54])
        self.assertTrue(all(c['layer_id'] is None for c in self.api.project.state['candidates'][self.id]))

    def test_recipe_v2_groups_and_regeneration(self):
        p=self.api.project;draft=dict(auto_points=[[1,1]],manual_points=[],box=None,manual_groups=self.groups(),auto_policy='grid',grid=2)
        save_preset(p,self.id,'v2',draft);v=preview_preset(p,self.id,'v2')
        self.assertEqual(len(v['draft']['auto_points']),4);self.assertEqual(len(v['draft']['manual_groups']),2)
        self.assertEqual(v['draft']['auto_policy'],'grid');self.assertEqual(v['draft']['grid'],2)
        value=prepare_transfer(p,self.id,'v2','normalized');confirm_transfers(p,[dict(image_id=self.id,signature=transfer_signature(value))])
        mask=np.zeros((60,80),bool);mask[20:40,20:60]=1;item=dict(mask=mask,score=.9,stability=.99)
        with patch.object(self.api.model,'automatic',return_value=[item]),patch.object(self.api.model,'prompt',return_value=item),patch.object(self.api.model,'in_roi',return_value=item):
            r=run_transferred(p,self.api.model,self.id,[.5,.5,.8]);self.assertEqual(r['count'],3)
        self.assertEqual(self.client.get(f'/api/workflow/prompt-transfers/{self.id}/preview.png').status_code,200)

    def test_overlay_and_full_semantic_audit(self):
        p=self.api.project;a=np.zeros((60,80),bool);a[10:30,10:50]=1;b=np.zeros_like(a);b[20:40,10:50]=1
        ca=p.put_candidate(self.id,a,'a');ca.update(layer_id=1,reviewed=True);self.client.post('/api/layers',json={})
        cb=p.put_candidate(self.id,b,'b');cb.update(layer_id=2)
        r=self.client.get(f'/api/workbench/{self.id}/audit').json();self.assertEqual(r['overlap_pixels'],400);self.assertFalse(r['full_semantic_ready'])
        r=self.client.get(f'/api/workbench/{self.id}/overlay.png?ids={ca["id"]},{cb["id"]}');self.assertEqual(r.status_code,200)
        rgba=np.array(Image.open(io.BytesIO(r.content)));self.assertGreater(rgba[12,12,3],0);self.assertGreater(rgba[35,12,3],0);self.assertEqual(rgba[1,1,3],0)

    def test_annotation_apply_does_not_destroy_calibration(self):
        from tem_analyzer.services.layers import fingerprint
        p=self.api.project;iid=self.id
        self.client.post('/api/scale/manual',json=dict(image_id=iid,a=[5,55],b=[55,55],length=50,unit='nm'))
        before=copy.deepcopy(p.state['scale'][iid]);record=copy.deepcopy(p.state['preprocessing'][iid])
        p.state['annotation_proposals'][iid]=dict(input_hash=fingerprint(p,iid),scale={'nm_per_px':None},regions=[],template={'scale_roi':None,'text_rois':[]})
        r=self.client.post('/api/workflow/annotations/apply',json={'image_id':iid});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(p.state['scale'][iid],before);self.assertEqual(p.state['preprocessing'][iid].get('scale_status'),record.get('scale_status'))

    def test_measurement_and_rotation_evidence(self):
        p=self.api.project;mask=np.zeros((60,80),bool);mask[20:40,10:70]=1;c=p.put_candidate(self.id,mask,'a');c.update(layer_id=1)
        r=self.client.post('/api/workflow/rotation/preview',json={'image_id':self.id,'config':{'layer_id':1,'mode':'edge','edge':'bottom'}});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.get(f'/api/workbench/{self.id}/rotation.png').status_code,200)
        self.client.post('/api/workflow/rotation/confirm',json={'image_id':self.id})
        self.client.post('/api/scale/manual',json=dict(image_id=self.id,a=[5,55],b=[55,55],length=50,unit='nm'))
        r=self.client.post('/api/workflow/measurement',json={'image_id':self.id,'config':{'layer_id':1,'axis':'thickness','start':20,'stop':60,'step':10}});self.assertEqual(r.status_code,200,r.text)
        for suffix in ('?aligned=true','?aligned=false&row=0'):
            r=self.client.get(f'/api/workbench/{self.id}/measurement.png'+suffix);self.assertEqual(r.status_code,200,r.text[:200])
