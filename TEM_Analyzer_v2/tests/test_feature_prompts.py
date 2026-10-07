import base64
import io
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from tem_analyzer.feature_prompts import FeatureConfig, propose
from tem_analyzer.preprocessing import filtered, filter_support
from test_workflow import WorkflowTest


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.image=np.full((160,240,3),40,np.uint8)
        self.image[20:60,20:220]=180;self.image[90:135,20:220]=230
        self.ex=np.zeros((160,240),bool);self.ex[:,:12]=True

    def test_all_methods_are_deterministic_inside_and_spaced(self):
        for method in ('kmeans','canny','sobel','scharr','hybrid'):
            with self.subTest(method=method):
                cfg={'method':method,'count':8,'min_distance':15,'edge_clearance':3}
                result=propose(self.image,self.ex,[[120,40]],cfg,True)
                self.assertEqual(result['points'],propose(self.image,self.ex,[[120,40]],cfg)['points'])
                self.assertGreater(result['count'],0);self.assertLessEqual(result['count'],8)
                self.assertFalse(result['inference_run'])
                previous=[[120,40]]
                for x,y in result['points']:
                    self.assertFalse(self.ex[int(y),int(x)])
                    self.assertTrue(all(np.hypot(x-a,y-b)>=15 for a,b in previous));previous.append([x,y])
                    if method!='kmeans':self.assertGreater(min(abs(y-v) for v in (20,60,90,135)),2)
                raw=base64.b64decode(result['proposal_preview'].split(',')[1])
                self.assertEqual(Image.open(io.BytesIO(raw)).size,(240,160))

    def test_filter_variants_preserve_original_geometry_and_disabled_identity(self):
        rng=np.random.default_rng(42);im=np.uint8(np.clip(120+rng.normal(0,12,(64,80,3)),0,255));original=im.copy()
        for method in ('gaussian','median','bilateral','nlm'):
            out=filtered(im,{'enabled':True,'method':method})
            self.assertEqual(out.shape,im.shape);self.assertEqual(out.dtype,np.uint8)
            self.assertLess(float(out.var()),float(im.var()))
            np.testing.assert_array_equal(filtered(im,{'enabled':False,'method':method}),im)
        np.testing.assert_array_equal(im,original)
        self.assertEqual(filter_support({'enabled':True,'method':'nlm'}),13)

    def test_empty_edges_and_full_exclusion_are_explicit(self):
        result=propose(np.zeros_like(self.image),self.ex,config={'method':'canny'})
        self.assertEqual(result['count'],0);self.assertTrue(result['warnings'])
        self.assertEqual(propose(self.image,np.ones_like(self.ex))['count'],0)
        with self.assertRaises(ValueError):FeatureConfig(canny_low=120,canny_high=20)
        with self.assertRaises(ValueError):FeatureConfig(method='unknown')

    def test_downsampling_returns_original_coordinates(self):
        im=np.repeat(np.repeat(self.image,5,axis=0),5,axis=1)
        ex=np.repeat(np.repeat(self.ex,5,axis=0),5,axis=1)
        result=propose(im,ex,config={'method':'sobel','min_distance':80})
        self.assertEqual(max(result['analysis_shape']),512)
        self.assertTrue(any(x>512 for x,y in result['points']))
        self.assertTrue(all(not ex[int(y),int(x)] for x,y in result['points']))


class FeatureApiTests(WorkflowTest):
    def test_preview_never_infers_or_saves_candidates(self):
        before=self.api.project.image(self.id).copy()
        with patch.object(self.api.model,'automatic',side_effect=AssertionError('inference')):
            for method in ('kmeans','canny','sobel','scharr','hybrid','profile'):
                r=self.client.post('/api/prompts/ml',json={'image_id':self.id,'method':method,'denoise':'median','preview':True})
                self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['inference_run'])
        np.testing.assert_array_equal(before,self.api.project.image(self.id))
        self.assertFalse(self.api.project.state['candidates'][self.id])
        self.assertEqual(self.client.post('/api/prompts/ml',json={'image_id':self.id,'method':'bad'}).status_code,422)
        self.assertEqual(self.client.post('/api/prompts/ml',json={'image_id':self.id,'canny_low':200,'canny_high':10}).status_code,422)

    def test_batch_features_generate_unassigned_masks_and_store_recipe(self):
        im=self.api.project.root/'images'/f'{self.id}.png'
        a=np.full((60,80,3),20,np.uint8);a[15:40,10:65]=200;Image.fromarray(a).save(im)
        mask=a[:,:,0]>100
        with patch.object(self.api.model,'automatic',return_value=[{'mask':mask,'score':.9,'stability':.99}]) as auto:
            result=self.api.app.state.workflow_jobs.execute(self.id,'sam',{'sam':{'prompt_source':'features','features':{'method':'canny','count':3}}})
            self.assertGreater(result['prompt_count'],0)
            self.assertTrue(auto.call_args.kwargs['prepared_points'])
        self.assertEqual(self.api.project.state['prepared_prompts'][self.id]['settings']['method'],'canny')
        self.assertTrue(all(c['layer_id'] is None for c in self.api.project.state['candidates'][self.id]))


if __name__=='__main__':unittest.main()
