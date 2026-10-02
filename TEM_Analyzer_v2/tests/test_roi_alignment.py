import copy,unittest
from unittest.mock import patch
import numpy as np
import test_workflow
from tem_analyzer.algorithms.roi_alignment import prepare,restore
from tem_analyzer.algorithms.metrology import transform_points
from tem_analyzer.sam_service import ModelService


class ROIAlignmentGeometryTests(unittest.TestCase):
    def test_point_roundtrip_support_and_box(self):
        im=np.full((60,90,3),80,np.uint8);points=[[20,20,1],[60,40,1],[40,15,0]]
        rgb,pp,box,support,meta=prepare(im,points,box_margin=6)
        self.assertEqual(rgb.shape[:2],support.shape);self.assertAlmostEqual(meta['angle_deg'],-26.565051177)
        restored=transform_points(np.array(pp)[:,:2],meta['aligned_to_local'])
        np.testing.assert_allclose(restored,np.array(points)[:,:2],atol=1e-10)
        self.assertAlmostEqual(pp[0][1],pp[1][1]);self.assertAlmostEqual(box[3]-box[1],12)
        self.assertTrue(np.all(rgb[~support]==80));self.assertEqual([p[2] for p in pp],[1,1,0])

    def test_identity_probability_and_does_not_clip_to_box(self):
        im=np.full((30,80,3),80,np.uint8);rgb,pp,box,support,meta=prepare(im,[[20,15,1],[50,15,1]],box_margin=2)
        prob=np.ones((30,80),float)*.8;back=restore(prob,support,meta,im.shape)
        np.testing.assert_array_equal(back,prob);self.assertGreater(back[4,4],.5)
        self.assertEqual(box[3]-box[1],4)

    def test_invalid_or_ambiguous_preparation_rejected(self):
        im=np.zeros((50,50,3),np.uint8)
        for pts,box,margin in [([[10,10,1]],None,0),([[10,10,1],[10,10,1]],None,0),([[5,5,1],[40,5,1],[5,40,1],[40,40,1]],None,0),([[10,10,1],[30,30,1]],[5,5,40,40],6),([[10,10,1],[30,30,1]],None,float('nan'))]:
            with self.subTest(pts=pts,margin=margin),self.assertRaises(ValueError):prepare(im,pts,box,margin)

    def test_service_restores_original_coordinates_threshold_and_metadata(self):
        service=ModelService();service.cfg={'mask_threshold':.7};im=np.zeros((80,100,3),np.uint8)
        def infer(rgb,points,box,**kw):
            prob=np.full(rgb.shape[:2],.8);return dict(probability=prob,mask=prob>.5,score=.9,context={},logits=np.zeros((1,256,256)))
        with patch.object(service,'prompt',side_effect=infer):
            item=service.in_roi(im,[10,10,90,70],[[30,30,1],[70,50,1],[40,30,0]],mask_choice=1,align_positive=True,box_margin=6)
        self.assertEqual(item['mask'].shape,(80,100));self.assertFalse(item['mask'][:10].any());self.assertFalse(item['mask'][:,90:].any())
        self.assertTrue(item['mask'][40,50]);self.assertEqual(item['prompt_violations'],[2]);self.assertEqual(item['inference_domains'],[[10,10,90,70]])
        self.assertEqual(item['roi_alignment']['original_roi'],[10,10,90,70]);self.assertNotIn('logits',item)
        with patch.object(service,'prompt',side_effect=infer):
            service.cfg['mask_threshold']=.9;empty=service.in_roi(im,[10,10,90,70],[[30,30,1],[70,50,1]],align_positive=True)
        self.assertFalse(empty['mask'].any())

    def test_prior_and_unaligned_box_option_fail_closed(self):
        service=ModelService();im=np.zeros((50,50,3),np.uint8)
        with self.assertRaises(ValueError):service.in_roi(im,[0,0,50,50],[[10,10,1],[30,30,1]],prior={'mask':np.ones((50,50))},align_positive=True)
        with self.assertRaises(ValueError):service.in_roi(im,[0,0,50,50],[[10,10,1]],box_margin=6)


class ROIAlignmentAPITests(unittest.TestCase):
    setUp=test_workflow.WorkflowTest.setUp
    tearDown=test_workflow.WorkflowTest.tearDown

    def test_independent_preview_accept_and_persisted_provenance(self):
        m=np.zeros((60,80),bool);m[20:30,20:60]=True
        item=dict(mask=m,score=.9,inference_domains=[[10,10,70,50]],roi_alignment={'angle_deg':-30,'method':'positive_line'},prompt_violations=[])
        payload=dict(image_id=self.id,roi=[10,10,70,50],points=[[20,20,1],[40,30,1]],align_positive=True,box_margin=6,preview=True)
        before=copy.deepcopy(self.api.project.state)
        with patch.object(self.api.model,'in_roi',return_value=item) as infer:
            r=self.client.post('/api/sam/prompt',json=payload);self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(infer.call_args.kwargs,{'align_positive':True,'box_margin':6})
        self.assertEqual(self.api.project.state,before);data=r.json();self.assertIn('사전정렬',' '.join(data['warnings']))
        saved=self.client.post('/api/roi-previews/'+data['preview_token']+'/accept',json={}).json()
        self.assertEqual(saved['roi_alignment']['angle_deg'],-30);self.assertTrue(saved['prompts']['align_positive']);self.assertIsNone(saved['layer_id'])

    def test_non_roi_parent_and_disabled_margin_rejected_before_inference(self):
        p=self.api.project;c=p.put_candidate(self.id,np.ones((60,80),bool),'parent')
        for extra in [dict(align_positive=True),dict(align_positive=True,roi=[0,0,80,60],parent=c['id']),dict(box_margin=6,roi=[0,0,80,60])]:
            with patch.object(self.api.model,'in_roi') as infer:
                r=self.client.post('/api/sam/prompt',json=dict(image_id=self.id,points=[[20,20,1],[40,30,1]],**extra))
                self.assertEqual(r.status_code,400,r.text);infer.assert_not_called()


if __name__=='__main__':unittest.main()
