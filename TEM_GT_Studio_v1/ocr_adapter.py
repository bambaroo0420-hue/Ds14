"""EasyOCR local-only adapter. No executable, automatic weights download or cloud API."""
from functools import lru_cache
import numpy as np
from model_paths import local_path

def required_files(language='en'):
    if language not in ('en','ko_en'): raise ValueError('지원 OCR 언어: en, ko_en')
    return ['craft_mlt_25k.pth','korean_g2.pth' if language=='ko_en' else 'english_g2.pth']

@lru_cache(maxsize=2)
def _reader(directory,language,stamps):
    try: import easyocr
    except ImportError as exc: raise ValueError('EasyOCR 패키지가 없습니다. python -m pip install -r requirements.txt 를 실행하세요.') from exc
    return easyocr.Reader(['ko','en'] if language=='ko_en' else ['en'],gpu=False,
        model_storage_directory=directory,user_network_directory=directory,
        download_enabled=False,detect_network='craft',verbose=False)

def read_words(image,model_dir='models/easyocr',language='en'):
    folder=local_path(model_dir or 'models/easyocr').resolve()
    names=required_files(language)
    missing=[n for n in names if not (folder/n).is_file()]
    if missing: raise ValueError('OCR 가중치가 없습니다: '+', '.join(missing)+f'\nZIP 압축을 풀어 {folder} 바로 아래에 .pth 파일을 넣으세요. 자동 다운로드는 꺼져 있습니다.')
    stamps=tuple(((folder/n).stat().st_size,(folder/n).stat().st_mtime_ns) for n in names)
    reader=_reader(str(folder),language,stamps)
    result=reader.readtext(image,detail=1,paragraph=False,workers=0)
    words=[];h,w=image.shape[:2]
    for polygon,text,confidence in result:
        q=np.asarray(polygon,dtype=float)
        box=[max(0,int(np.floor(q[:,0].min()))),max(0,int(np.floor(q[:,1].min()))),min(w,int(np.ceil(q[:,0].max()))),min(h,int(np.ceil(q[:,1].max())))]
        if box[2]>box[0] and box[3]>box[1]:
            # Keep low-confidence boxes for exclusion, even when their text is unreliable.
            words.append({'text':str(text),'box':box,'confidence':float(confidence)*100})
    return words
