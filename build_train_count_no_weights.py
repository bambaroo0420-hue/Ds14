"""Build the training-only ZIP from approved code and pinned SAM sources; no weights."""
from pathlib import Path, PurePosixPath
import hashlib,io,json,urllib.request,zipfile

BASE=Path(__file__).resolve().parent
ROOT=BASE/'TEM_Offline_Metrology'
REV='2b90b9f5ceec907a1c18123530e92e794ad901a4'
FILES=['temflow/__init__.py','temflow/core.py','temflow/models.py','temflow/data.py',
       'temflow/semantic_decoder.py','temflow/folder_splits.py','temflow/learning_curve.py',
       'requirements.txt','prepare_training_assets.py','README_TRAIN_COUNT_KO.md',
       'README_NO_WEIGHTS_KO.md','notebooks/00_train_count_setup.ipynb',
       'notebooks/13_train_count_benchmark.ipynb']

def build():
    contents={p:(ROOT/p).read_bytes() for p in FILES}
    if (ROOT/'vendor/sam2/build_sam.py').exists():
        for p in (ROOT/'vendor/sam2').rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.yaml','.yml'):
                contents[p.relative_to(ROOT).as_posix()]=p.read_bytes()
        contents['vendor/SAM2_LICENSE']=(ROOT/'vendor/SAM2_LICENSE').read_bytes()
    else:
        data=urllib.request.urlopen(f'https://codeload.github.com/facebookresearch/sam2/zip/{REV}',timeout=120).read()
        prefix=f'sam2-{REV}/'
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.startswith(prefix):continue
                rel=info.filename[len(prefix):]
                if '..' in PurePosixPath(rel).parts:raise ValueError('Unsafe archive')
                if rel=='LICENSE':contents['vendor/SAM2_LICENSE']=z.read(info)
                elif rel.startswith('sam2/') and PurePosixPath(rel).suffix in ('.py','.yaml','.yml'):
                    contents['vendor/'+rel]=z.read(info)
    contents['weights/README.txt']=b'Place sam2.1_hiera_large.pt here. See README_NO_WEIGHTS_KO.md. No weights included.\n'
    output=BASE/'TEM_Train_Count_Benchmark_No_Weights.zip'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(contents.items()):
            assert not name.endswith(('.pt','.pth','.safetensors','.ckpt'))
            zi=zipfile.ZipInfo('TEM_Offline_Metrology/'+name,date_time=(2026,10,7,0,0,0))
            zi.compress_type=zipfile.ZIP_DEFLATED;z.writestr(zi,data)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert 'TEM_Offline_Metrology/vendor/sam2/configs/sam2.1/sam2.1_hiera_l.yaml' in z.namelist()
    result=dict(file=output.name,bytes=output.stat().st_size,files=len(contents),sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (BASE/'TEM_Train_Count_Benchmark_No_Weights.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__':build()
