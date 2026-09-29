"""Optional offline OCR with no automatic model downloads."""
from pathlib import Path
from functools import lru_cache
from threading import RLock

_lock = RLock()

@lru_cache(maxsize=2)
def _reader(folder,language,versions):
    import easyocr
    return easyocr.Reader(['ko','en'] if language=='ko_en' else ['en'],gpu=False,model_storage_directory=folder,user_network_directory=folder,download_enabled=False,verbose=False)

def read_words(image,folder,language):
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
    for polygon,text,confidence in result:
        x=[p[0] for p in polygon];y=[p[1] for p in polygon]
        out.append(dict(text=str(text),box=[int(min(x)),int(min(y)),int(max(x)),int(max(y))],confidence=float(confidence)))
    return out

