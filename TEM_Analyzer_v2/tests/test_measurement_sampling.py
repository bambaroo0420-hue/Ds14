import unittest
import numpy as np
from tem_analyzer.algorithms.metrology import measure,rotation_transform


class MeasurementSamplingTests(unittest.TestCase):
    def run_mask(self,m,axis='thickness',start=0,stop=None,step=10,**sampling):
        bound=m.shape[1 if axis=='thickness' else 0]-1
        return measure(m,np.ones_like(m),rotation_transform(m.shape,0),axis,start,bound if stop is None else stop,step,2,sampling)

    def test_each_component_has_own_center_window_and_raw_rows_preserved(self):
        m=np.zeros((100,220),bool);m[20:40,10:100]=1;m[50:70,120:210]=1
        full=self.run_mask(m);central=self.run_mask(m,mode='component_center',center_fraction=.6)
        self.assertEqual(full['summary']['count'],18);self.assertEqual(central['summary']['count'],12)
        self.assertEqual(len(full['rows']),len(central['rows']))
        self.assertEqual(central['summary']['mean'],40)
        self.assertEqual([c['accepted_count'] for c in central['components']],[6,6])
        for row in central['rows']:
            if row['status']=='outside_component_window':
                self.assertIsNone(row['length_nm']);self.assertEqual(row['raw_length_nm'],40)
                self.assertEqual(len(row['original_endpoints']),2)

    def test_hole_flag_is_not_automatic_value_filter(self):
        m=np.zeros((100,100),bool);m[20:80,10:90]=1;m[40:50,30:70]=0
        raw=self.run_mask(m,start=50,stop=50)
        self.assertEqual(raw['summary']['count'],2)
        self.assertTrue(all('multiple_intervals' in r['quality_flags'] for r in raw['rows']))
        strict=self.run_mask(m,start=50,stop=50,single_interval_only=True)
        self.assertEqual(strict['summary']['count'],0)
        self.assertTrue(all(r['status']=='multiple_intervals' and r['raw_length_nm']>0 for r in strict['rows']))

    def test_separate_layers_at_same_x_are_not_multiple_interval_in_one_object(self):
        m=np.zeros((100,100),bool);m[20:40,10:90]=1;m[60:80,10:90]=1
        r=self.run_mask(m,start=50,stop=50,single_interval_only=True)
        self.assertEqual(r['summary']['count'],2);self.assertFalse(any(r['quality_flags'] for r in r['rows']))

    def test_frame_policy_is_optional_and_cd_uses_y_windows(self):
        m=np.zeros((100,100),bool);m[20:80,:80]=1
        raw=self.run_mask(m,axis='cd',start=0,step=10)
        self.assertEqual(raw['summary']['count'],6);self.assertIn('frame_endpoint',raw['rows'][2]['quality_flags'])
        strict=self.run_mask(m,axis='cd',mode='component_center',center_fraction=.5,reject_frame_endpoints=True)
        self.assertEqual(strict['summary']['count'],0)
        self.assertTrue(any('frame_endpoint' in r.get('exclusion_reasons',[]) for r in strict['rows']))

    def test_tiny_components_are_not_silently_dropped(self):
        m=np.zeros((20,20),bool);m[10,10]=1
        r=self.run_mask(m,start=10,stop=10,step=1)
        self.assertEqual(r['summary']['count'],1);self.assertEqual(r['rows'][0]['length_px'],1)
        r=self.run_mask(m,start=10,stop=10,min_length_px=2)
        self.assertEqual(r['rows'][0]['status'],'below_min_length');self.assertEqual(r['rows'][0]['raw_length_nm'],2)

    def test_invalid_policies_rejected(self):
        m=np.ones((10,10),bool)
        for policy in ({'center_fraction':0},{'center_fraction':float('nan')},{'mode':'auto_best'},{'min_length_px':-1},{'single_interval_only':'false'}):
            with self.assertRaises(ValueError):self.run_mask(m,**policy)


if __name__=='__main__':unittest.main()
