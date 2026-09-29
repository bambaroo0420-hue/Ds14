import io
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_workflow
from tem_analyzer.calibration import bar_candidates
from tem_analyzer.sam_service import ModelService


class CalibrationEditorTest(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def test_both_bar_polarities_and_roi_exclusion(self):
        for bg,fg in [(15,240),(240,15)]:
            im=np.full((100,240,3),bg,np.uint8)
            im[70:74,20:120]=fg
            im[5:8,5:225]=fg  # longer distractor outside specified ROI
            bars=bar_candidates(im,[0,.5,.8,1])
            self.assertEqual(bars[0]['pixel_length'],100)
            self.assertEqual(bars[0]['bar'],[[20.,71.5],[120.,71.5]])
        self.assertEqual(bar_candidates(np.zeros((30,80,3),np.uint8),[0,0,1,1]),[])

    def test_scale_api_per_image_and_restart(self):
        im=np.full((60,80,3),30,np.uint8);im[40:43,10:60]=230
        b=io.BytesIO();Image.fromarray(im).save(b,format='PNG')
        other=self.client.post('/api/images',files={'file':('bar.png',b.getvalue(),'image/png')}).json()['image_id']
        response=self.client.post('/api/scale/bar',json={'image_id':other,'roi':[0,.5,1,1]})
        self.assertEqual(response.status_code,200,response.text)
        bar=response.json()['candidates'][0]['bar']
        r=self.client.post('/api/scale/manual',json={'image_id':other,'a':bar[0],'b':bar[1],'length':.1,'unit':'um'})
        self.assertEqual(r.json()['nm_per_px'],2)
        self.assertEqual(r.json()['px_per_nm'],.5)
        self.assertNotIn(self.id,self.api.project.state['scale'])
        from tem_analyzer.storage import Project
        self.assertEqual(Project(self.temp.name).state['scale'][other]['px_per_nm'],.5)
        bad=self.client.post('/api/scale/manual',json={'image_id':other,'a':[0,0],'b':[1000,0],'length':50})
        self.assertEqual(bad.status_code,400)
        thumb=self.client.get(f'/api/thumbnails/{other}.jpg')
        self.assertEqual(thumb.status_code,200)

    def test_roi_coordinates_parent_clip_and_name_persistence(self):
        parent=np.zeros((60,80),bool);parent[10:40,20:50]=True
        c=self.api.project.put_candidate(self.id,parent,'test')
        # Real ROI transform, mocked SAM only: crop coords returned to original canvas.
        def fake_predict(crop,points,box):
            self.assertEqual(crop.shape[:2],(40,40))
            self.assertEqual(points,[[15,15,1],[30,30,0]])
            self.assertEqual(box,[5,5,35,35])
            return {'mask':np.ones(crop.shape[:2],bool),'score':.9}
        with patch.object(self.api.model,'prompt',side_effect=fake_predict):
            r=self.client.post('/api/sam/prompt',json={'image_id':self.id,'parent':c['id'],'roi':[10,5,50,45],'points':[[25,20,1],[40,35,0]],'box':[15,10,45,40]})
        self.assertEqual(r.status_code,200,r.text)
        new=r.json();self.assertEqual(new['area'],int(parent.sum()));self.assertEqual(new['parent'],c['id'])
        np.testing.assert_array_equal(self.api.project.mask(self.id,new['id']),parent)
        bad=self.client.post('/api/sam/prompt',json={'image_id':self.id,'parent':c['id'],'roi':[10,5,50,45],'points':[[1,1,1]]})
        self.assertEqual(bad.status_code,400)
        r=self.client.post('/api/candidates/name',json={'image_id':self.id,'candidate_id':new['id'],'name':'Passivation'})
        self.assertEqual(r.status_code,200)
        from tem_analyzer.storage import Project
        self.assertEqual(Project(self.temp.name).candidate(self.id,new['id'])['name'],'Passivation')

