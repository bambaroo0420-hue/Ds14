import unittest
import numpy as np
from tem_analyzer.algorithms.metrology import measure,rotation_transform,interval_coverage


class ContourValidityTests(unittest.TestCase):
    def band(self,width=3,angle=30):
        yy,xx=np.mgrid[:96,:128];q=(yy-48)*np.cos(np.deg2rad(angle))-(xx-64)*np.sin(np.deg2rad(angle))
        return (q>=0)&(q<width),rotation_transform(q.shape,-angle)

    def measured(self,m,valid,t,axis='thickness'):
        mid=t['width' if axis=='thickness' else 'height']//2
        return measure(m,valid,t,axis,mid-10,mid+10,1,1)

    def test_valid_target_never_rejects_its_own_interpolated_contour(self):
        for width in (1,3,10):
            for angle in (-30,0,7,30,45,89):
                with self.subTest(width=width,angle=angle):
                    m,t=self.band(width,angle);r=self.measured(m,m,t);control=self.measured(m,np.ones_like(m),t)
                    self.assertEqual(r['rows'],control['rows'])
                    self.assertNotIn('invalid_region',r['summary']['status_counts'])

    def test_explicit_invalid_stripe_and_all_invalid_are_not_filled(self):
        for angle in (-30,0,30,45):
            m,t=self.band(10,angle);v=m.copy();v[:,60:68]=False
            r=self.measured(m,v,t);bad=[x for x in r['rows'] if x['status']=='invalid_region']
            self.assertTrue(bad)
            for row in bad:
                self.assertIsNone(row['length_nm']);self.assertGreater(row['invalid_coverage_px'],0)
                self.assertAlmostEqual(row['valid_coverage_px']+row['invalid_coverage_px'],row['length_px'])
            r=self.measured(m,np.zeros_like(m),t)
            self.assertEqual(r['summary']['count'],0)

    def test_internal_invalid_single_pixel_cannot_be_skipped(self):
        m=np.zeros((20,20),bool);m[4:16,4:16]=True;v=m.copy();v[10,10]=False
        t=rotation_transform(m.shape,0)
        # A near-tangent cut shorter than the old 0.5px sampling spacing.
        r=measure(m,v,t,'thickness',10.49,10.49,1,1)
        self.assertEqual(r['rows'][0]['status'],'invalid_region')
        self.assertAlmostEqual(r['rows'][0]['invalid_coverage_px'],.02,places=8)

    def test_holes_components_axes_keep_geometry_and_unknown(self):
        m=np.zeros((50,80),bool);m[10:35,10:45]=True;m[18:25,22:30]=False;m[10:35,60:70]=True
        v=m.copy();v[28:31,12:17]=False;t=rotation_transform(m.shape,13)
        for axis in ('thickness','cd'):
            r=self.measured(m,v,t,axis);control=self.measured(m,m,t,axis)
            self.assertEqual([x.get('raw_length_nm') for x in r['rows']],[x.get('raw_length_nm') for x in control['rows']])
            self.assertEqual([x.get('original_endpoints') for x in r['rows']],[x.get('original_endpoints') for x in control['rows']])

    def test_interval_coverage_and_bad_shapes(self):
        self.assertEqual(interval_coverage(0,10,[[-2,2],[4,7],[9,12]]),6)
        with self.assertRaises(ValueError):measure(np.ones((3,4)),np.ones((4,3)),rotation_transform((3,4),0),'thickness',0,2,1,1)


if __name__=='__main__':unittest.main()
