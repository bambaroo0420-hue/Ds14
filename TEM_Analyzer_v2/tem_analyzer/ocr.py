"""Optional offline OCR with no automatic model downloads."""
from pathlib import Path
from functools import lru_cache
from threading import RLock

_lock = RLock()

@lru_cache(maxsize=2)
def _reader(folder,language,versions):
    import easyocr
    return easyocr.Reader(['ko','en'] if language=='ko_en' else ['en'],gpu=False,model_storage_directory=folder,user_network_directory=folder,download_enabled=False,verbose=False)

def read_words(image,folder,language,enhanced=False):
    path=Path(folder).expanduser().resolve()
    names=['craft_mlt_25k.pth','korean_g2.pth' if language=='ko_en' else 'english_g2.pth']
    missing=[x for x in names if not (path/x).is_file()]
    if missing:raise ValueError('OCR 가중치가 없습니다: '+', '.join(missing))
    if language not in ('en','ko_en'):raise ValueError('OCR 언어는 en/ko_en입니다.')
    versions=tuple((x,(path/x).stat().st_mtime_ns,(path/x).stat().st_size) for x in names)
    out=[]
    with _lock:
        reader=_reader(str(path),language,versions)
        result=reader.readtext(image,detail=1,paragraph=False)
        extra=[]
        if enhanced:
            import numpy as np
            from PIL import Image
            h,w=image.shape[:2];factor=min(2.,2400/max(h,w))
            if factor>1.05:
                size=(round(w*factor),round(h*factor));sx=size[0]/w;sy=size[1]/h
                larger=np.asarray(Image.fromarray(image).resize(size,Image.Resampling.BICUBIC))
                extra=[([[float(x)/sx,float(y)/sy] for x,y in polygon],text,confidence) for polygon,text,confidence in reader.readtext(larger,detail=1,paragraph=False)]
    for polygon,text,confidence in result:
        x=[p[0] for p in polygon];y=[p[1] for p in polygon]
        out.append(dict(text=str(text),box=[int(min(x)),int(min(y)),int(max(x)),int(max(y))],confidence=float(confidence)))
    # Keep already-confident complete labels. Replace weak labels only when the
    # larger pass corroborates their location; never concatenate unrelated text.
    for polygon,text,confidence in extra:
        if confidence<.25:continue
        xs=[p[0] for p in polygon];ys=[p[1] for p in polygon];box=[min(xs),min(ys),max(xs),max(ys)]
        area=max(1,(box[2]-box[0])*(box[3]-box[1]));matches=[]
        for i,old in enumerate(out):
            a=old['box'];overlap=max(0,min(a[2],box[2])-max(a[0],box[0]))*max(0,min(a[3],box[3])-max(a[1],box[1]))
            if overlap/min(area,max(1,(a[2]-a[0])*(a[3]-a[1])))>.6:matches.append(i)
        candidate=dict(text=str(text),box=[int(round(v)) for v in box],confidence=float(confidence),ocr_pass='upscaled')
        if not matches:out.append(candidate)
        elif all(out[i]['confidence']<.35 and confidence>out[i]['confidence'] for i in matches):
            out[matches[0]]=candidate
    return out

