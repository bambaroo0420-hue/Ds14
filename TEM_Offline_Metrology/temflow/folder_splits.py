"""Read user-defined splits without moving or automatically splitting inputs."""
from pathlib import Path
import hashlib, json
import numpy as np
from PIL import Image
from .core import read_image, digest
from .data import decode_gt

def load_folder_splits(split_dirs, prepared_dir, class_names, rgb_map=None,
                       ignore=255, groups=None):
    groups=groups or {}; prepared_dir=Path(prepared_dir).resolve()
    if prepared_dir.exists() and any(prepared_dir.iterdir()):
        raise ValueError('Use a new empty prepared_dir to preserve previous manifests')
    if set(split_dirs)!={'train','val','test'}:
        raise ValueError('Configure train, val and test paths explicitly')
    rows=[]; arrays=[]; pixel_splits={}; group_splits={}
    def index(folder,extensions):
        folder=Path(folder).expanduser().resolve()
        if not folder.is_dir():raise ValueError('Missing folder: '+str(folder))
        files={}
        for p in sorted(folder.iterdir()):
            if not p.is_file() or p.suffix.lower() not in extensions:continue
            key=p.stem.casefold()
            if key in files:raise ValueError('Duplicate stem: '+str(p))
            files[key]=p
        if not files:raise ValueError('Empty input folder: '+str(folder))
        return files
    for split,dirs in split_dirs.items():
        images=index(dirs['images'],{'.png','.tif','.tiff','.jpg','.jpeg'})
        gts=index(dirs['gt'],{'.png','.tif','.tiff'})
        if set(images)!=set(gts):
            raise ValueError(f'{split}: missing GT {sorted(set(images)-set(gts))}; unmatched GT {sorted(set(gts)-set(images))}')
        for key,p in images.items():
            gt=gts[key]; im=read_image(p)
            with Image.open(gt) as src:
                a=np.asarray(src)
                if getattr(src,'n_frames',1)!=1:raise ValueError('Multi-page GT unsupported: '+str(gt))
                if a.ndim==3 and a.shape[2]==4 and np.any(a[:,:,3]!=255):
                    raise ValueError('Transparent GT must be explicitly converted to ignore')
                if a.ndim==2 and a.dtype.kind not in 'uib':raise ValueError('GT IDs must be integers')
            a=decode_gt(gt,rgb_map=rgb_map)
            if a.shape!=im.shape[:2]:raise ValueError('Image/GT size mismatch: '+str(p))
            unknown=set(map(int,np.unique(a)))-set(map(int,class_names))-{ignore}
            if unknown:raise ValueError(f'{p.name}: undefined classes {unknown}')
            ph=hashlib.sha256(str(im.shape).encode()+im.tobytes()).hexdigest()
            if ph in pixel_splits and pixel_splits[ph]!=split:
                raise ValueError('Identical image pixels across splits: '+str(p))
            pixel_splits[ph]=split
            ident=f'{split}/{p.stem}'
            group=groups.get(ident,ident)
            if group in group_splits and group_splits[group]!=split:
                raise ValueError('Same specimen group across splits: '+str(group))
            group_splits[group]=split
            dest=prepared_dir/split/(p.stem+'.png')
            rows.append(dict(id=ident,image=str(p),gt=str(dest),source_gt=str(gt),
                source_gt_sha256=digest(gt),group=group,split=split,image_sha256=digest(p),
                pixel_sha256=ph,classes=[int(c) for c in np.unique(a) if c!=ignore]))
            arrays.append(a.astype('uint16'))
    # Write only normalized copies, after all source data has passed validation.
    for r,a in zip(rows,arrays):
        dest=Path(r['gt']);dest.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(a).save(dest);r['gt_sha256']=digest(dest)
    (prepared_dir/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    return rows
