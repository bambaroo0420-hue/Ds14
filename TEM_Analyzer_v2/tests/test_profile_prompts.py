import unittest
import numpy as np
from tem_analyzer.feature_prompts import FeatureConfig,propose


class ProfilePromptTests(unittest.TestCase):
    def make_image(self,angle=0):
        yy,xx=np.mgrid[:256,:384];phase=(yy-128)*np.cos(np.deg2rad(angle))-(xx-192)*np.sin(np.deg2rad(angle))
        image=np.full((256,384,3),80,np.uint8);masks=[]
        for level,width,value in [(-50,4,210),(-25,6,20),(0,10,200),(35,5,15)]:
            m=(phase>=level)&(phase<level+width);image[m]=value;masks.append(m)
        return image,masks

    def test_narrow_band_coverage_and_automatic_angle(self):
        for angle in (0,25,-45):
            image,masks=self.make_image(angle)
            cfg=dict(method='profile',count=20,edge_clearance=1,min_distance=8,profile_max_width=16)
            r=propose(image,np.zeros(image.shape[:2],bool),config=cfg)
            self.assertGreater(r['count'],0)
            self.assertLess(abs((r['diagnostics']['angle_deg']-angle+90)%180-90),2)
            self.assertTrue(all(any(m[int(y),int(x)] for x,y in r['points']) for m in masks),r['points'])
            self.assertEqual(r['points'],propose(image,np.zeros(image.shape[:2],bool),config=cfg)['points'])

    def test_exclusion_and_existing_points_are_respected(self):
        image,_=self.make_image();ex=np.zeros(image.shape[:2],bool);ex[:,:170]=1
        cfg=dict(method='profile',profile_angle=0,count=12,edge_clearance=1,min_distance=15)
        r=propose(image,ex,[[200,80]],cfg,True);previous=[[200,80]]
        for x,y in r['points']:
            self.assertFalse(ex[int(y),int(x)]);self.assertTrue(all(np.hypot(x-a,y-b)>=15 for a,b in previous));previous.append([x,y])
        self.assertFalse(r['inference_run']);self.assertIn('proposal_preview',r)

    def test_uniform_automatic_has_no_silent_grid_fallback(self):
        image=np.full((100,200,3),100,np.uint8)
        r=propose(image,np.zeros((100,200),bool),config=dict(method='profile'))
        self.assertEqual(r['count'],0);self.assertTrue(r['warnings']);self.assertIsNone(r['diagnostics']['angle_deg'])

    def test_resolution_and_configuration(self):
        image,_=self.make_image();im=np.repeat(np.repeat(image,3,0),3,1)
        r=propose(im,np.zeros(im.shape[:2],bool),config=dict(method='profile',analysis_side=1024,edge_clearance=1,count=10,profile_angle=0))
        self.assertEqual(max(r['analysis_shape']),1024)
        self.assertTrue(all(0<=x<im.shape[1] and 0<=y<im.shape[0] for x,y in r['points']))
        self.assertTrue(any(x>512 for x,y in r['points']))
        for c in ({'profile_min_width':20,'profile_max_width':10},{'profile_angle':float('nan')},{'analysis_side':4096}):
            with self.assertRaises(ValueError):FeatureConfig(**c)

    def test_empty_and_single_pixel_profiles(self):
        from tem_analyzer.algorithms.profile_prompts import profile_proposals
        cfg=FeatureConfig(method='profile',profile_angle=0)
        for shape in ((1,1),(20,20)):
            p,edges,meta,warnings=profile_proposals(np.zeros(shape),np.zeros(shape,bool),cfg,1)
            self.assertEqual(p,[]);self.assertTrue(warnings);self.assertEqual(edges.shape,shape)


if __name__=='__main__':unittest.main()
