"""Diagnostic ECC alternatives for known 19.jpg rotation fixtures (not GT)."""
import numpy as np
from PIL import Image
import cv2
from pathlib import Path
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--fixture-dir',required=True);args=parser.parse_args()
p=Path(args.fixture_dir)
a=np.array(Image.open(p/'19_crop_1cell_+00deg.png').convert('L'),np.float32)/255
b=np.array(Image.open(p/'19_crop_1cell_+07deg.png').convert('L'),np.float32)/255
h,w=b.shape;ha,wa=a.shape
translation=np.array([[1,0,(w-wa)/2],[0,1,(h-ha)/2]],np.float32)
canvas=cv2.warpAffine(a,translation,(w,h),borderValue=float(np.median(a)))
print('sizes',a.shape,b.shape)
for border in (0,.08,.15,.25):
    mask=np.zeros_like(b,np.uint8);mask[int(h*border):int(h*(1-border)) or h,int(w*border):int(w*(1-border)) or w]=255
    for seed in (-7,0,7):
        warp=cv2.getRotationMatrix2D(((w-1)/2,(h-1)/2),seed,1).astype(np.float32)
        try:
            score,m=cv2.findTransformECC(canvas,b,warp,cv2.MOTION_EUCLIDEAN,(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,150,1e-6),mask,5)
            print(border,seed,score,np.degrees(np.arctan2(m[1,0],m[0,0])))
        except cv2.error:print('fail',border,seed)
