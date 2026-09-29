"""Optional offline OCR with no automatic model downloads."""
from pathlib import Path

def read_words(image,folder,language):
    path=Path(folder).expanduser().resolve()
    names=['craft_mlt_25k.pth','korean_g2.pth' if language=='ko_en' else 'english_g2.pth']
    missing=[x for x in names if not (path/x).is_file()]
    if missing:raise ValueError('OCR 가중치가 없습니다: '+', '.join(missing))
    import easyocr
    reader=easyocr.Reader(['ko','en'] if language=='ko_en' else ['en'],gpu=False,model_storage_directory=str(path),user_network_directory=str(path),download_enabled=False,verbose=False)
    out=[]
    for polygon,text,confidence in reader.readtext(image,detail=1,paragraph=False):
        x=[p[0] for p in polygon];y=[p[1] for p in polygon]
        out.append(dict(text=str(text),box=[int(min(x)),int(min(y)),int(max(x)),int(max(y))],confidence=float(confidence)))
    return out
