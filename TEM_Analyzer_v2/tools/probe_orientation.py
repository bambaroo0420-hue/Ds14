"""Exploratory, not production metrology: orientation hypotheses from gradients."""
import json
import argparse
from pathlib import Path
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tem_analyzer.operations import excluded
from tem_analyzer.algorithms.annotations import propose_annotations

parser=argparse.ArgumentParser();parser.add_argument('--image',required=True);parser.add_argument('--ocr-report',required=True);args=parser.parse_args()
image=np.array(Image.open(args.image).convert('RGB'))
words=json.loads(Path(args.ocr_report).read_text(encoding='utf8'))['ocr']['words']
proposal=propose_annotations(image,words)
ex=excluded(image.shape[:2],proposal['template'])
colored=np.ptp(image.astype(float),axis=2)>35
ex|=ndi.binary_dilation(colored,iterations=5);ex[:8]=1;ex[-8:]=1;ex[:,:8]=1;ex[:,-8:]=1
for sigma in (2,4,8,12):
    g=ndi.gaussian_filter(image.mean(axis=2),sigma)
    gy,gx=np.gradient(g);magnitude=np.hypot(gx,gy)
    angles=(np.degrees(np.arctan2(gy,gx))+180)%180-90
    valid=~ndi.binary_dilation(ex,iterations=int(sigma*2))
    hist,bins=np.histogram(angles[valid],bins=np.linspace(-90,90,181),weights=magnitude[valid]**2)
    smoothed=ndi.gaussian_filter1d(hist,2,mode='wrap');best=int(np.argmax(smoothed))
    phase=np.deg2rad(angles[valid]*2);z=np.sum(magnitude[valid]**2*np.exp(1j*phase))/np.sum(magnitude[valid]**2)
    print(dict(sigma=sigma,mode=float(bins[best]+.5),tensor=float(np.degrees(np.angle(z))/2),coherence=float(abs(z))),flush=True)
    import cv2
    edge=cv2.Canny(np.uint8(g),10,25);edge[~valid]=0
    lines=cv2.HoughLinesP(edge,1,np.pi/720,25,minLineLength=60,maxLineGap=15)
    if lines is not None:
        spans=[]
        for x0,y0,x1,y1 in lines.reshape(-1,4):
            spans.append([float(np.hypot(x1-x0,y1-y0)),float(np.degrees(np.arctan2(y1-y0,x1-x0)))])
        print('hough',sorted(spans,reverse=True)[:8])
