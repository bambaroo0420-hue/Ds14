import copy,unittest
from unittest.mock import patch
import numpy as np
import test_workflow

class ReviewFixes(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown
    def test_empty_layer_name_generates_number_and_named_layer_remains(self):
        for body,name in [({},'Layer 2'),({'name':'   '},'Layer 3'),({'name':'MgO'},'MgO')]:
            r=self.client.post('/api/layers',json=body);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['name'],name)
        self.assertEqual([x['name'] for x in self.api.project.state['layers']],['Layer 1','Layer 2','Layer 3','MgO'])
    def apply_regions(self):
        self.api.project.state['legacy_templates_enabled']=True
        r=self.client.post('/api/preprocessing/apply',json={'image_ids':[self.id],'template':{'id':'fix','name':'fix','scale_roi':None,'text_rois':[[0,0,.5,.5]]},'apply_regions':True,'apply_scale':False})
        self.assertEqual(r.status_code,200,r.text)
    def test_excluded_points_filtered_before_inference_and_masks_clipped(self):
        self.apply_regions();r=self.client.post('/api/prompts/grid',json={'image_id':self.id,'grid':4});self.assertEqual(r.status_code,200)
        self.assertTrue(all(not(x<40 and y<30) for x,y in r.json()['points']))
        seen=[]
        def auto(im,**kw):
            seen.extend(kw['prepared_points']);return [{'mask':np.ones((60,80),bool),'score':.9,'stability':.99}]
        with patch.object(self.api.model,'automatic',side_effect=auto):
            r=self.client.post('/api/sam/prepared',json={'image_id':self.id,'auto_points':[[10,10],[60,40]],'manual_points':[]})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(seen,[[60,40]]);m=self.api.project.mask(self.id,r.json()['created'][0]['id']);self.assertFalse(m[:30,:40].any());self.assertTrue(m[40,60])
        with patch.object(self.api.model,'prompt') as mocked:
            r=self.client.post('/api/sam/prompt',json={'image_id':self.id,'points':[[10,10,1]]});self.assertEqual(r.status_code,400);mocked.assert_not_called()
    def stage(self):
        p=self.api.project;m=np.zeros((60,80),bool);m[15:40,20:60]=True;c=p.put_candidate(self.id,m,'fixture');before=copy.deepcopy(p.state)
        with patch.object(self.api.model,'in_roi',return_value={'mask':m.copy(),'score':.9}):
            r=self.client.post('/api/sam/prompt',json={'image_id':self.id,'parent':c['id'],'roi':[15,10,65,45],'points':[[30,25,1]],'preview':True})
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['saved']);self.assertEqual(p.state,before);self.assertEqual(len(list((p.root/'masks').glob('*.png'))),1)
        return r.json()['preview_token'],c
    def test_preview_cancel_does_not_save_and_accept_saves_once(self):
        token,c=self.stage();self.assertEqual(self.client.get('/api/roi-previews/'+token+'.png').status_code,200)
        self.assertEqual(self.client.delete('/api/roi-previews/'+token).status_code,200);self.assertEqual(len(self.api.project.state['candidates'][self.id]),1)
        # Fresh preview of the same parent.
        with patch.object(self.api.model,'in_roi',return_value={'mask':self.api.project.mask(self.id,c['id']),'score':.9}):
            r=self.client.post('/api/sam/prompt',json={'image_id':self.id,'parent':c['id'],'roi':[15,10,65,45],'points':[[30,25,1]],'preview':True})
        token=r.json()['preview_token'];r=self.client.post('/api/roi-previews/'+token+'/accept',json={});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['parent'],c['id']);self.assertEqual(len(self.api.project.state['candidates'][self.id]),2)
        self.assertEqual(self.client.post('/api/roi-previews/'+token+'/accept',json={}).status_code,410)
    def test_preview_cannot_save_after_exclusions_change(self):
        token,c=self.stage();self.apply_regions();r=self.client.post('/api/roi-previews/'+token+'/accept',json={});self.assertEqual(r.status_code,409,r.text);self.assertEqual(len(self.api.project.state['candidates'][self.id]),1)
