"""Run on an internet-connected machine; prepares pinned SAM sources and weights.
No pip or CUDA environment changes. Existing files are never overwritten.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, io, urllib.request, zipfile

REV='2b90b9f5ceec907a1c18123530e92e794ad901a4'
URL='https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt'
SHA='2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318'

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def prepare(root,check_only=False):
    root=Path(root).resolve();vendor=root/'vendor';weight=root/'weights/sam2.1_hiera_large.pt'
    if not check_only:
        archive=urllib.request.urlopen(f'https://codeload.github.com/facebookresearch/sam2/zip/{REV}',timeout=120).read()
        prefix=f'sam2-{REV}/'
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.startswith(prefix):continue
                rel=info.filename[len(prefix):]
                if rel=='LICENSE':target=vendor/'SAM2_LICENSE'
                elif rel.startswith('sam2/'):
                    parts=PurePosixPath(rel).parts
                    if '..' in parts or ':' in rel:raise ValueError('Unsafe archive path')
                    target=vendor.joinpath(*parts)
                else:continue
                content=z.read(info)
                if target.exists():
                    if target.read_bytes()!=content:raise ValueError(f'Existing source differs from pinned revision: {target}')
                else:
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        if not weight.exists():
            weight.parent.mkdir(parents=True,exist_ok=True)
            partial=weight.with_suffix('.pt.partial')
            if partial.exists():raise RuntimeError(f'Remove or rename incomplete download first: {partial}')
            print('Downloading SAM2.1 Large (~898 MB)',flush=True)
            urllib.request.urlretrieve(URL,partial)
            if digest(partial)!=SHA:raise ValueError('Weight hash mismatch; partial file retained for inspection')
            partial.rename(weight)
    needed=['temflow/models.py','temflow/core.py','temflow/data.py',
            'vendor/sam2/build_sam.py','vendor/sam2/configs/sam2.1/sam2.1_hiera_l.yaml',
            'notebooks/13_train_count_benchmark.ipynb']
    missing=[p for p in needed if not (root/p).is_file()]
    if missing:raise FileNotFoundError(missing)
    if not weight.exists() or digest(weight)!=SHA:raise ValueError('Missing or incorrect SAM2.1 Large weights')
    print('Training assets OK:',root)
    print('Python/CUDA dependencies must be installed separately. DINO is not needed for notebook 13.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--check-only',action='store_true');a=p.parse_args();prepare(a.root,a.check_only)
