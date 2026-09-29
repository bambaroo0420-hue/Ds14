import io
import tempfile
import unittest
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from tem_analyzer.storage import Project
from tem_analyzer.services.prompt_transfer import save_preset,preview_preset,transfer_matrix
from tem_analyzer.algorithms.metrology import transform_points
from tem_analyzer.algorithms.annotations import propose_annotations
from tem_analyzer.algorithms.orientation import image_direction
from tem_analyzer.services.measurement import alignment
from tem_analyzer.services.scopes import save_scope


class ImprovementsTests(unittest.TestCase):
    def test_image_direction_checkerboard_not_reliable(self):
        from tem_analyzer.algorithms.orientation import image_direction
        yy,xx=np.mgrid[:512,:512];gray=np.uint8(50+140*((xx//64+yy//64)%2))
        r=image_direction(np.repeat(gray[...,None],3,2),np.zeros_like(gray,bool))
        self.assertFalse(r['reliable_proposal']);self.assertLess(r['tensor_coherence'],.15)

    def test_merged_scale_text_box_and_material_label_not_scale(self):
        image=np.full((200,400,3),25,np.uint8);image[165:173,20:90]=255
        words=[dict(text='5 nm',box=[15,134,91,176],confidence=.9)]
        p=propose_annotations(image,words);self.assertAlmostEqual(p['scale']['nm_per_px'],5/70)
        self.assertEqual(p['regions'][0]['kind'],'scale')
        words[0]['text']='TaOx ~ 5 nm'
        self.assertIsNone(propose_annotations(image,words)['scale']['nm_per_px'])

    def test_oversized_ocr_not_automatically_excluded(self):
        image=np.full((400,400,3),40,np.uint8)
        p=propose_annotations(image,[dict(text='FE',box=[-5,63,305,353],confidence=.67)])
        self.assertFalse(p['regions'][0]['recommended']);self.assertFalse(p['template']['text_rois'])

    def test_normalized_prompts_and_missing_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Project(d)
            def add(size):
                b=io.BytesIO();Image.new('RGB',size).save(b,format='PNG');return p.add_image(b.getvalue(),'test.png')
            a=add((80,60));b=add((160,120))
            save_preset(p,a,'sample',dict(auto_points=[[10,10]],manual_points=[[20,20,1],[30,30,0]],box=[0,0,80,60]))
            result=preview_preset(p,b,'sample')
            self.assertFalse(result['inference_run']);self.assertEqual(result['draft']['auto_points'],[[20.5,20.5]])
            self.assertEqual(result['draft']['box'],[0,0,160,120]);self.assertEqual(result['draft']['manual_points'][1][2],0)
            self.assertFalse(p.state['candidates'][b]);p.delete_image(a)
            with self.assertRaises(KeyError):preview_preset(p,b,'sample')

    def test_ecc_translation_coordinate_direction_and_flat_failure(self):
        rng=np.random.default_rng(7);gray=ndi.gaussian_filter(rng.random((120,160)),2)
        gray=np.uint8((gray-gray.min())/np.ptp(gray)*255);a=np.repeat(gray[...,None],3,axis=2)
        b=ndi.shift(a,(3,5,0),order=1,mode='reflect')
        matrix,score=transfer_matrix(a,b,'ecc');point=transform_points([[70,50]],matrix)[0]
        np.testing.assert_allclose(point,[75,53],atol=.5);self.assertGreater(score,.9)
        with self.assertRaises(ValueError):transfer_matrix(np.zeros_like(a),b,'ecc')

    def test_frame_edge_not_returned_as_perfect_zero_degree(self):
        with tempfile.TemporaryDirectory() as d:
            p=Project(d);b=io.BytesIO();Image.new('RGB',(100,100)).save(b,format='PNG');iid=p.add_image(b.getvalue(),'frame.png')
            mask=np.zeros((100,100),bool);mask[:60]=True;c=p.put_candidate(iid,mask,'frame')
            save_scope(p,iid,'target',[c['id']])
            with self.assertRaises(ValueError):alignment(p,iid,dict(scope_id='target',mode='edge',edge='top'))
            r=alignment(p,iid,dict(scope_id='target',mode='auto',edge='top'))
            self.assertEqual(r['used_edge'],'bottom');self.assertTrue(r['warnings']);self.assertTrue(r['needs_review'])

    def test_image_direction_empty_rejected(self):
        with self.assertRaises(ValueError):image_direction(np.zeros((200,200,3),np.uint8),np.zeros((200,200),bool))
        y,x=np.indices((256,256));gray=np.uint8(40+180*((x+y)//28%2))
        result=image_direction(np.repeat(gray[...,None],3,axis=2),np.zeros_like(gray,bool))
        self.assertAlmostEqual(result['angle_deg'],-45,delta=1)
        self.assertIsNone(result['residual_px']);self.assertTrue(result['reliable_proposal'])


if __name__=='__main__':unittest.main()
