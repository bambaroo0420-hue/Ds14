import unittest
from unittest.mock import patch
import numpy as np
from tem_analyzer.algorithms.orientation import image_direction


class OrientationFallbackTests(unittest.TestCase):
    def test_disagreeing_fallback_is_not_upgraded(self):
        yy,xx=np.mgrid[:256,:384]
        image=np.repeat(np.uint8(40+150*((yy//35)%2))[...,None],3,2)
        wrong=np.array([[[40,40,140,140]],[[70,40,170,140]],[[100,40,200,140]]])
        weak=np.array([[[40,40,240,54]],[[40,80,240,94]],[[40,120,240,134]]])
        with patch('cv2.HoughLinesP',side_effect=[wrong]+[weak]*6):
            fit=image_direction(image,np.zeros(image.shape[:2],bool))
        self.assertTrue(fit['adaptive_fallback'])
        self.assertFalse(fit['reliable_proposal'])
        self.assertGreater(fit['agreement_deg'],2)

    def test_consistent_first_pass_does_not_try_extra_recipes(self):
        yy,xx=np.mgrid[:256,:384]
        image=np.repeat(np.uint8(40+150*((yy//35)%2))[...,None],3,2)
        lines=np.array([[[40,40,240,40]],[[40,80,240,80]],[[40,120,240,120]]])
        with patch('cv2.HoughLinesP',return_value=lines) as hough:
            fit=image_direction(image,np.zeros(image.shape[:2],bool))
        self.assertTrue(fit['reliable_proposal']);self.assertFalse(fit['adaptive_fallback'])
        self.assertEqual(hough.call_count,1)


if __name__=='__main__':unittest.main()
