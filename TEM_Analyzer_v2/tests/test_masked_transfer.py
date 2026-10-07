import unittest
from unittest.mock import patch
import cv2
import numpy as np
from tem_analyzer.services.prompt_transfer import transfer_matrix
from tem_analyzer.algorithms.metrology import transform_points


class MaskedTransferTests(unittest.TestCase):
    def fixture(self,angle=7,dx=9,dy=-5):
        rng=np.random.default_rng(223)
        gray=cv2.GaussianBlur(rng.uniform(0,255,(240,320)).astype('float32'),(0,0),1)
        source=np.repeat(gray[:,:,None],3,2).astype('uint8')
        known=cv2.getRotationMatrix2D((159.5,119.5),angle,1);known[:,2]+=[dx,dy]
        target=cv2.warpAffine(source,known,(320,240),borderValue=(127,127,127))
        # Different fixed annotation positions must not dominate registration.
        se=np.zeros((240,320),bool);te=se.copy();se[110:130,150:170]=True;te[70:110,190:230]=True
        source[se]=255;target[te]=0
        return source,target,se,te,np.vstack([known,[0,0,1]])

    @unittest.skipUnless(hasattr(cv2,'findTransformECCWithMask'),'optional paired-mask API unavailable')
    def test_known_rotation_translation_with_different_exclusions(self):
        for angle in (-12,0,7,15):
            a,b,se,te,known=self.fixture(angle)
            m,score=transfer_matrix(a,b,'ecc_masked',se,te)
            pts=[[60,60],[160,120],[250,170]]
            self.assertGreater(score,.95)
            self.assertLess(np.linalg.norm(transform_points(pts,m)-transform_points(pts,known),axis=1).max(),.4)

    @unittest.skipUnless(hasattr(cv2,'findTransformECCWithMask'),'optional paired-mask API unavailable')
    def test_insufficient_valid_region_and_unrelated_texture_are_rejected(self):
        a,b,se,te,_=self.fixture()
        with self.assertRaisesRegex(ValueError,'유효 영역'):transfer_matrix(a,b,'ecc_masked',np.ones_like(se),te)
        other=np.random.default_rng(934).integers(0,255,a.shape,dtype='uint8')
        with self.assertRaises(ValueError):transfer_matrix(a,other,'ecc_masked',se,te)

    def test_unsupported_api_is_explicit_no_legacy_fallback(self):
        a,b,se,te,_=self.fixture()
        actual=hasattr
        with patch('builtins.hasattr',side_effect=lambda obj,key:False if obj is cv2 and key=='findTransformECCWithMask' else actual(obj,key)):
            with self.assertRaisesRegex(ValueError,'OpenCV'):transfer_matrix(a,b,'ecc_masked',se,te)


if __name__=='__main__':unittest.main()
