import io
import os
import tempfile
import unittest
from PIL import Image
import numpy as np
from fastapi.testclient import TestClient

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        os.environ['TEM_PROJECT_DIR']=self.temp.name
        import importlib
        import tem_analyzer.api as api
        self.api=importlib.reload(api)
        self.client=TestClient(self.api.app)
        im=Image.new('RGB',(80,60),'#343434');b=io.BytesIO();im.save(b,format='PNG')
        r=self.client.post('/api/images',files={'file':('synthetic.png',b.getvalue(),'image/png')})
        self.assertEqual(r.status_code,200,r.text)
        self.id=r.json()['image_id']

    def tearDown(self):self.temp.cleanup()

    def test_template_scale_candidates_layers_restart(self):
        c=self.client
        r=c.post('/api/templates',json={'id':'custom','name':'촬영 양식','scale_roi':[0,.7,.3,1],'text_rois':[[.7,0,1,.2]]})
        self.assertEqual(r.status_code,200)
        r=c.post('/api/scale/manual',json={'image_id':self.id,'a':[10,10],'b':[60,10],'length':50,'unit':'nm'})
        self.assertEqual(r.json()['nm_per_px'],1)
        mask=np.zeros((60,80),bool);mask[15:35,20:60]=1
        first=self.api.project.put_candidate(self.id,mask,'test')
        dup=c.post('/api/candidates/duplicate',json={'image_id':self.id,'candidate_id':first['id']}).json()
        self.assertEqual(dup['parent'],first['id'])
        edit=c.post('/api/candidates/brush',json={'image_id':self.id,'candidate_id':dup['id'],'strokes':[{'mode':'remove','radius':3,'points':[[30,25]]}]}).json()
        self.assertLess(edit['area'],dup['area'])
        r=c.post('/api/layers/assign',json={'image_id':self.id,'candidate_id':edit['id'],'layer_id':1,'instance_id':'cell_1','reviewed':True})
        self.assertEqual(r.status_code,200)
        x=c.get(f'/api/coverage/{self.id}/stats').json()
        self.assertGreater(x['unassigned'],0)
        self.assertEqual(x['overlap'],0)
        from tem_analyzer.storage import Project
        restored=Project(self.temp.name)
        self.assertEqual(restored.state['scale'][self.id]['nm_per_px'],1)
        self.assertEqual(restored.candidate(self.id,edit['id'])['instance_id'],'cell_1')
        self.assertTrue(restored.mask(self.id,edit['id']).any())

    def test_empty_template_can_be_created_and_reloaded(self):
        c=self.client
        r=c.post('/api/templates',json={'id':'empty','name':'빈 템플릿','scale_roi':None,'text_rois':[]})
        self.assertEqual(r.status_code,200,r.text)
        self.assertIsNone(r.json()['scale_roi'])
        stats=c.get(f'/api/coverage/{self.id}/stats')
        self.assertEqual(stats.status_code,200,stats.text)
        self.assertEqual(stats.json()['excluded'],0)
        from unittest.mock import patch
        with patch('tem_analyzer.ocr.read_words',return_value=[]):
            r=c.post('/api/scale/detect',json={'image_id':self.id})
        self.assertEqual(r.status_code,200)
        self.assertIsNone(r.json()['nm_per_px'])
        from tem_analyzer.storage import Project
        self.assertIsNone(Project(self.temp.name).state['templates']['empty']['scale_roi'])

    def test_missing_model_and_unimplemented_are_explicit(self):
        r=self.client.post('/api/sam/automatic',json={'image_id':self.id,'grid':16})
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.client.get('/api/state').json()['capabilities']['measurement'],'available')
        self.assertEqual(self.client.get('/').status_code,200)

if __name__=='__main__':unittest.main()

