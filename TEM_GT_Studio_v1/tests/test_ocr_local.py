import sys,types
import numpy as np
import pytest
from PIL import Image
from ocr_adapter import read_words,_reader,required_files
from model_paths import checkpoint_path
from core import match_scale_bars

def test_missing_weights_error_before_import(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'easyocr',None)
    with pytest.raises(ValueError,match='craft_mlt_25k.pth'):
        read_words(np.zeros((20,20,3),np.uint8),str(tmp_path))

def test_offline_reader_contract_and_cache(tmp_path,monkeypatch):
    _reader.cache_clear(); calls=[]
    for f in required_files(): (tmp_path/f).write_bytes(b'test double, not real weights')
    class FakeReader:
        def __init__(self,langs,**kw): calls.append((langs,kw))
        def readtext(self,*args,**kw): return [([[1,2],[8,2],[8,9],[1,9]],'50 nm',.92),([[10,2],[18,2],[18,9],[10,9]],'?',.01)]
    monkeypatch.setitem(sys.modules,'easyocr',types.SimpleNamespace(Reader=FakeReader))
    im=np.zeros((20,20,3),np.uint8)
    words=read_words(im,str(tmp_path));read_words(im,str(tmp_path))
    assert len(calls)==1
    assert calls[0][1]['download_enabled'] is False
    assert calls[0][1]['gpu'] is False
    assert calls[0][1]['model_storage_directory']==str(tmp_path)
    assert len(words)==2 and words[1]['confidence']==1 # uncertain box still excluded
    _reader.cache_clear()

def test_korean_recognizer_is_optional(tmp_path):
    assert required_files('ko_en')==['craft_mlt_25k.pth','korean_g2.pth']
    for f in required_files(): (tmp_path/f).write_bytes(b'fake')
    with pytest.raises(ValueError,match='korean_g2.pth'): read_words(np.zeros((20,20,3),np.uint8),str(tmp_path),'ko_en')

def test_split_number_unit_and_magnification():
    im=np.zeros((120,250,3),np.uint8);im[48:52,20:221]=255
    words=[{'text':'50','box':[60,65,80,80],'confidence':90},{'text':'nm','box':[85,65,108,80],'confidence':90},{'text':'120k','box':[10,5,50,20],'confidence':90}]
    result=match_scale_bars(im,words)
    assert result['candidates'][0]['nm']==50
    assert result['candidates'][0]['nm_per_pixel']==.25

def test_relative_checkpoints_do_not_depend_on_cwd(tmp_path,monkeypatch):
    import model_paths
    monkeypatch.setattr(model_paths,'ROOT',tmp_path)
    p=tmp_path/'models/micro_sam/vit_b_em_organelles.pth';p.parent.mkdir(parents=True);p.write_bytes(b'fake')
    monkeypatch.chdir(tmp_path.parent)
    assert checkpoint_path('','micro_sam','vit_b')==p
