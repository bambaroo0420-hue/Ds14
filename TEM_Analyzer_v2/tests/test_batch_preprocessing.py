import io
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_workflow
from tem_analyzer.preprocessing import model_input


class BatchPreprocessingTest(unittest.TestCase):
    def setUp(self):
        test_workflow.WorkflowTest.setUp(self)
        self.api.project.state['legacy_templates_enabled']=True
    tearDown=test_workflow.WorkflowTest.tearDown

    def add_bar(self,width):
        im=np.full((60,80,3),40,np.uint8);im[40:43,10:10+width]=240
        im[2:8,55:75]=210
        out=io.BytesIO();Image.fromarray(im).save(out,format='PNG')
        return self.client.post('/api/images',files={'file':('bar.png',out.getvalue(),'image/png')}).json()['image_id']

    def payload(self):
        return {'template':{'id':'batch','name':'batch','scale_roi':[0,.5,1,.9],'text_rois':[[.6,0,1,.2]]},'apply_regions':True,'apply_scale':True,'length':50,'unit':'nm'}

    def test_batch_individual_scale_failure_review_and_original_preserved(self):
        a,b=self.add_bar(40),self.add_bar(20)
        originals={id:self.api.project.image(id).copy() for id in [a,b,self.id]}
        # Existing scale survives a failed detection, but cannot silently pass review.
        self.client.post('/api/scale/manual',json={'image_id':self.id,'a':[0,0],'b':[50,0],'length':50})
        r=self.client.post('/api/preprocessing/apply',json=self.payload())
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['count'],3)
        self.assertEqual(self.api.project.state['scale'][a]['nm_per_px'],1.25)
        self.assertEqual(self.api.project.state['scale'][b]['nm_per_px'],2.5)
        self.assertFalse(self.api.project.state['scale'][a]['confirmed'])
        self.assertEqual(r.json()['results'][self.id]['scale_status'],'failed')
        self.assertEqual(self.api.project.state['scale'][self.id]['nm_per_px'],1)
        self.assertEqual(self.client.post('/api/preprocessing/confirm',json={'image_id':self.id}).status_code,400)
        for id in originals:
            np.testing.assert_array_equal(self.api.project.image(id),originals[id])
            cleaned=model_input(self.api.project,id)
            self.assertTrue((cleaned[0:12,48:80]==originals[id][20,20]).all())
            np.testing.assert_array_equal(cleaned[20,20],originals[id][20,20])
        for mode in ['original','overlay','processed']:
            r=self.client.get(f'/api/preprocessing/{a}/preview.png?mode={mode}')
            self.assertEqual(r.status_code,200)
            arr=np.asarray(Image.open(io.BytesIO(r.content)))
            if mode=='processed':np.testing.assert_array_equal(arr[5,60],originals[a][20,20])
            if mode=='original':np.testing.assert_array_equal(arr,originals[a])
        self.assertEqual(self.client.post('/api/preprocessing/confirm',json={'image_id':a}).status_code,200)
        self.assertTrue(self.api.project.state['scale'][a]['confirmed'])
        self.client.post('/api/scale/manual',json={'image_id':self.id,'a':[0,0],'b':[50,0],'length':50})
        self.assertEqual(self.client.post('/api/preprocessing/confirm',json={'image_id':self.id}).status_code,200)
        from tem_analyzer.storage import Project
        restored=Project(self.temp.name)
        self.assertTrue(restored.state['preprocessing'][a]['reviewed'])

    def test_snapshot_used_by_sam_after_template_changes_and_subset_update(self):
        a=self.add_bar(40);body=self.payload();body['image_ids']=[a]
        self.client.post('/api/preprocessing/apply',json=body)
        self.assertFalse(self.api.project.state['preprocessing'][self.id]['regions_applied'])
        self.client.post('/api/templates',json={'id':'empty','name':'empty','scale_roi':None,'text_rois':[]})
        def predict(im,points,box):
            self.assertTrue((im[5,60]==40).all())
            return {'mask':np.ones((60,80),bool),'score':.9}
        with patch.object(self.api.model,'prompt',side_effect=predict):
            r=self.client.post('/api/sam/prompt',json={'image_id':a,'points':[[20,20,1]]})
        self.assertEqual(r.status_code,200,r.text)
        mask=self.api.project.mask(a,r.json()['id'])
        self.assertFalse(mask[5,60]);self.assertTrue(mask[20,20])
        self.client.delete('/api/images/'+a)
        self.assertNotIn(a,self.api.project.state['preprocessing'])

    def test_regions_only_and_invalid_length(self):
        body=self.payload();body['length']=0
        self.assertEqual(self.client.post('/api/preprocessing/apply',json=body).status_code,400)
        self.assertFalse(self.api.project.state['preprocessing'][self.id]['regions_applied'])
        self.assertNotIn('batch',self.api.project.state['templates'])
        body['apply_scale']=False
        self.assertEqual(self.client.post('/api/preprocessing/apply',json=body).status_code,200)
        self.assertNotIn(self.id,self.api.project.state['scale'])
        self.assertEqual(self.client.post('/api/preprocessing/confirm',json={'image_id':self.id}).status_code,200)

    def test_all_region_types_and_clear_images(self):
        a=self.add_bar(40)
        body=self.payload()
        body['template']['text_rois']=[[0,0,.2,.2],[.6,0,1,.2],[.7,.3,.9,.45]]
        self.assertEqual(self.client.post('/api/preprocessing/apply',json=body).status_code,200)
        for image_id in [self.id,a]:
            im=model_input(self.api.project,image_id)
            for y,x in [(5,5),(5,65),(20,60),(40,30)]:np.testing.assert_array_equal(im[y,x],self.api.project.image(image_id)[20,25])
            self.assertTrue(im[20,25].any())
            self.assertEqual(len(self.api.project.state['preprocessing'][image_id]['template']['text_rois']),3)
        self.api.project.state['prepared_prompts']={a:{'points':[[10,10]]}}
        templates=self.api.project.state['templates'].copy()
        r=self.client.delete('/api/images')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['count'],2)
        self.assertEqual(self.api.project.state['images'],{})
        self.assertEqual(self.api.project.state['scale'],{})
        self.assertEqual(self.api.project.state['preprocessing'],{})
        self.assertEqual(self.api.project.state['prepared_prompts'],{})
        self.assertEqual(self.api.project.state['templates'],templates)
        self.assertEqual(list((self.api.project.root/'images').glob('*.png')),[])

