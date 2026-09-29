from pathlib import Path
import csv, hashlib, json
import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_image(path, preprocessing='uint8'):
    a = np.asarray(Image.open(path))
    if a.ndim == 2:
        a = np.repeat(a[..., None], 3, -1)
    if a.ndim != 3 or a.shape[-1] not in (3, 4):
        raise ValueError(f'Unsupported image shape {a.shape}: {path}')
    a = a[..., :3]
    if preprocessing == 'uint8':
        if a.dtype != np.uint8:
            raise ValueError('16-bit input: set preprocessing="percentile_1_99" explicitly.')
    elif preprocessing == 'percentile_1_99':
        lo, hi = np.percentile(a, [1, 99])
        a = np.clip((a.astype(np.float32)-lo) / max(float(hi-lo), 1e-6), 0, 1)
        a = np.round(a*255).astype(np.uint8)
    else:
        raise ValueError(preprocessing)
    return np.ascontiguousarray(a)


def load_mask(path, cfg):
    # Palette PNG must stay as indices. Do not convert P mode to RGB.
    a = np.asarray(Image.open(path))
    if a.ndim == 3:
        mapping = cfg.get('rgb_label_map')
        if not mapping:
            raise ValueError('RGB mask needs explicit rgb_label_map, e.g. {"255,0,0": 1}.')
        b = np.full(a.shape[:2], cfg['ignore_label'], dtype=np.int64)
        seen = np.zeros(a.shape[:2], bool)
        for rgb, label in mapping.items():
            hit = np.all(a[..., :3] == np.array([int(x) for x in rgb.split(',')]), axis=-1)
            b[hit] = int(label); seen |= hit
        if not seen.all():
            raise ValueError(f'Unmapped RGB colors in {path}; include background/ignore colors.')
        a = b
    if a.ndim != 2:
        raise ValueError(f'GT must be one 2D label image: {path}')
    a = a.astype(np.int64)
    if cfg.get('label_map'):
        out = np.full_like(a, cfg['ignore_label'])
        for old, new in cfg['label_map'].items():
            out[a == int(old)] = int(new)
        unknown = set(np.unique(a)) - {int(x) for x in cfg['label_map']}
        if unknown:
            raise ValueError(f'Unmapped labels: {unknown}')
        a = out
    allowed = set(map(int, cfg['class_names'])) | {cfg['background_label'], cfg['ignore_label']}
    bad = set(np.unique(a)) - allowed
    if bad:
        raise ValueError(f'Unknown GT labels {bad}; update class_names.')
    return a


def targets(mask, cfg):
    """Semantic class -> connected region. These are operational regions, not true instances."""
    out = []
    for cls in sorted(map(int, cfg['class_names'])):
        if cls in (cfg['background_label'], cfg['ignore_label']):
            continue
        cc, n = ndi.label(mask == cls, structure=np.ones((3, 3)))
        for i in range(1, n+1):
            region = cc == i
            if region.sum() >= cfg['min_gt_area']:
                out.append((cls, region))
    return out


def scan_to_manifest(root, output):
    """Generate editable manifest. User must set specimen groups and splits before training."""
    root = Path(root).resolve()
    exts = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}
    images = sorted(p for p in (root/'images').iterdir() if p.suffix.lower() in exts)
    masks = {p.stem: p for p in (root/'masks').iterdir() if p.suffix.lower() in exts}
    if not images: raise ValueError(f'No images in {root / "images"}')
    if len({p.stem for p in images}) != len(images): raise ValueError('Duplicate image stems')
    with open(output, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['image_id','image','mask','group','split'])
        w.writeheader()
        for p in images:
            if p.stem not in masks: raise ValueError(f'Missing GT: {p.stem}')
            w.writerow(dict(image_id=p.stem, image=str(p), mask=str(masks[p.stem]), group=p.stem, split=''))
    return str(output)


def read_manifest(path):
    path = Path(path).resolve()
    with open(path, encoding='utf-8-sig', newline='') as f: rows = list(csv.DictReader(f))
    required = {'image_id','image','mask','group','split'}
    if not rows or not required.issubset(rows[0]): raise ValueError(f'Manifest requires {required}')
    groups, ids = {}, set()
    for r in rows:
        if r['split'] not in ('train','val','test'): raise ValueError('Fill split: train/val/test')
        if not r['group']: raise ValueError('group cannot be empty')
        if r['image_id'] in ids: raise ValueError('Duplicate image_id')
        ids.add(r['image_id'])
        if '/' in r['image_id'] or '\\' in r['image_id'] or r['image_id'] in ('.','..'):
            raise ValueError('image_id must be a filename-safe stem')
        if r['group'] in groups and groups[r['group']] != r['split']:
            raise ValueError(f'Leakage: group {r["group"]} appears in multiple splits')
        groups[r['group']] = r['split']
        for k in ('image','mask'):
            p = Path(r[k]); r[k] = str((path.parent/p).resolve() if not p.is_absolute() else p)
            if not Path(r[k]).is_file(): raise FileNotFoundError(r[k])
    if not {'train', 'val'}.issubset({r['split'] for r in rows}):
        raise ValueError('Need nonempty train and val groups')
    return rows


def audit(rows, cfg):
    summary, hashes = [], {}
    for r in rows:
        im = load_image(r['image'], cfg['preprocessing']); gt = load_mask(r['mask'], cfg)
        if im.shape[:2] != gt.shape: raise ValueError(f'Image/GT shape mismatch: {r["image_id"]}')
        # Pixel content catches copies re-encoded under another filename.
        h = hashlib.sha256(im.tobytes()).hexdigest()
        if h in hashes and hashes[h] != r['split']: raise ValueError('Duplicate image pixels across splits')
        hashes[h] = r['split']
        summary.append(dict(image_id=r['image_id'], split=r['split'], group=r['group'], pixel_sha256=h,
                            mask_file_sha256=sha256(r['mask']),
                            shape=list(gt.shape), labels=[int(x) for x in np.unique(gt)],
                            targets=len(targets(gt,cfg)), valid_fraction=float((gt != cfg['ignore_label']).mean())))
    return summary


def center_point(region):
    y,x = np.unravel_index(ndi.distance_transform_edt(region).argmax(), region.shape)
    return [float(x),float(y)]


def sample_prompt(region, rng, kind='point', jitter=0.05, valid=None):
    ys,xs = np.where(region)
    if len(xs) == 0: raise ValueError('Prompt target is empty')
    if kind == 'center': return {'points':[center_point(region)], 'labels':[1]}
    if kind == 'box':
        x0,x1,y0,y1 = xs.min(),xs.max(),ys.min(),ys.max()
        dx=max(1,x1-x0)*jitter; dy=max(1,y1-y0)*jitter
        box=np.array([x0,y0,x1,y1],dtype=float)+rng.uniform(-1,1,4)*[dx,dy,dx,dy]
        box[[0,2]]=np.clip(box[[0,2]],0,region.shape[1]-1)
        box[[1,3]]=np.clip(box[[1,3]],0,region.shape[0]-1)
        box[[0,2]]=np.sort(box[[0,2]]); box[[1,3]]=np.sort(box[[1,3]])
        return {'box':box.tolist()}
    k=rng.integers(len(xs)); p={'points':[[float(xs[k]),float(ys[k])]],'labels':[1]}
    if kind == 'point_negative':
        ring=ndi.binary_dilation(region,iterations=12)&~region
        if valid is not None: ring &= valid
        yy,xx=np.where(ring)
        if len(xx):
            k=rng.integers(len(xx)); p['points'].append([float(xx[k]),float(yy[k])]); p['labels'].append(0)
    return p


def grid_prompts(h,w,n):
    return [{'points': [[float(x),float(y)]], 'labels':[1]}
            for y in (np.arange(n)+.5)*h/n for x in (np.arange(n)+.5)*w/n]


def dump_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
