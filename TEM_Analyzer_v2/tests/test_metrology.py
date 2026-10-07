import unittest
import numpy as np
from tem_analyzer.algorithms.metrology import rotation_transform,transform_points,robust_line,measure,warp,edge_points


class MetrologyTests(unittest.TestCase):
    def test_transform_round_trip_and_non_clipping(self):
        points=np.array([[0,0],[99,0],[99,59],[0,59],[23.7,19.2]])
        for angle in (-45,-7,0,13,90):
            t=rotation_transform((60,100),angle);q=transform_points(points,t['matrix'])
            np.testing.assert_allclose(transform_points(q,t['inverse']),points,atol=1e-10)
            self.assertTrue((q>=-.5).all());self.assertTrue((q[:,0]<t['width']).all());self.assertTrue((q[:,1]<t['height']).all())

    def test_known_horizontal_thickness_cd_hole_and_multiple_objects(self):
        m=np.zeros((80,120),bool);m[20:40,10:100]=True;m[50:60,10:100]=True
        t=rotation_transform(m.shape,0);valid=np.ones_like(m)
        r=measure(m,valid,t,'thickness',50,50,1,2)
        self.assertEqual([x['length_nm'] for x in r['rows']],[40,20])
        cd=measure(m,valid,t,'cd',30,30,1,.5)
        self.assertAlmostEqual(cd['rows'][0]['length_nm'],45)
        m[25:30,40:60]=False
        r=measure(m,valid,t,'thickness',50,50,1,1)
        np.testing.assert_allclose([x['length_px'] for x in r['rows']],[5,10,10])

    def test_known_tilt_and_aligned_thickness(self):
        yy,xx=np.mgrid[:180,:200];slope=.12
        m=(yy>=40+slope*xx)&(yy<60+slope*xx)
        fit=robust_line(edge_points(m,'top',[.1,0,.9,1]))
        self.assertAlmostEqual(fit['angle_deg'],np.degrees(np.arctan(slope)),delta=.05)
        t=rotation_transform(m.shape,-fit['angle_deg'])
        r=measure(m,np.ones_like(m),t,'thickness',70,130,5,1)
        expected=20/np.sqrt(1+slope*slope)
        self.assertAlmostEqual(r['summary']['mean'],expected,delta=.25)

    def test_invalid_region_is_not_a_number(self):
        m=np.zeros((80,100),bool);m[20:60,10:90]=1;valid=np.ones_like(m);valid[30:35,40:50]=0
        r=measure(m,valid,rotation_transform(m.shape,0),'thickness',45,45,1,1)
        self.assertEqual(r['rows'][0]['status'],'invalid_region');self.assertIsNone(r['rows'][0]['length_nm'])

    def test_roi_does_not_create_artificial_boundary(self):
        m=np.zeros((100,100),bool);m[20:80,10:90]=1
        self.assertEqual(edge_points(m,'top',[.2,.4,.8,.7]),[])
        with self.assertRaises(ValueError):robust_line([[1,1],[1,1]])

    def test_label_warp_preserves_codes(self):
        a=np.zeros((20,30),np.uint16);a[5:10]=65535;a[11:14]=7
        rotated=warp(a,rotation_transform(a.shape,12),0,65533)
        self.assertTrue(set(np.unique(rotated)).issubset({0,7,65535,65533}))


if __name__=='__main__':unittest.main()
