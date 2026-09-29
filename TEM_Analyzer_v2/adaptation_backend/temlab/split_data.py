"""Reproducible train/validation split, independent of unlabelled test images."""
from pathlib import Path
import csv
import json
import random
import shutil
from datetime import datetime


def split_trainval(source, destination, *, seed=42, val_fraction=.2, group_overrides=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not 0 < val_fraction < 1:
        raise ValueError('val_fraction must be between 0 and 1')
    with source.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields, raw = reader.fieldnames, list(reader)
    required = {'image_id', 'image', 'mask', 'group', 'split'}
    if not fields or not required.issubset(fields):
        raise ValueError('Missing manifest columns')
    # Previously held-out images remain held out; do not silently train on them.
    rows = [dict(r) for r in raw if r['split'] != 'test']
    ids = [r['image_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate image_id')
    overrides = group_overrides or {}
    if not set(overrides).issubset(ids):
        raise ValueError('Unknown image_id in group_overrides')
    for r in rows:
        # Defaults preserve existing grouping. Initial manifest uses image_id.
        r['group'] = str(overrides.get(r['image_id'], r['group'] or r['image_id']))
        if not r['group'].strip():
            raise ValueError('Empty group')
        for key in ('image', 'mask'):
            path = Path(r[key])
            r[key] = str(path.resolve() if path.is_absolute() else (source.parent / path).resolve())
            if not Path(r[key]).is_file():
                raise FileNotFoundError(r[key])
    groups = sorted({r['group'] for r in rows})
    if len(groups) < 2:
        raise ValueError('Need >=2 groups. Separate cells: use image_id as group; same-cell crops stay together.')
    marker = destination.with_suffix('.split.json')
    if marker.exists():
        saved = json.loads(marker.read_text())
        if set(saved['assignment']) != set(ids):
            raise ValueError('Image list changed after split. Use a new destination for a new experiment.')
        if saved['groups'] != {r['image_id']: r['group'] for r in rows}:
            raise ValueError('Grouping changed after split. Use a new destination for a new experiment.')
        if saved['seed'] != seed or saved['val_fraction'] != val_fraction:
            raise ValueError('Split settings changed. Use a new destination for a new experiment.')
        assignment = saved['assignment']
    else:
        # Do not overwrite an existing user-authored manifest at this destination.
        if destination.exists() and destination != source:
            raise FileExistsError(f'{destination} already exists. Choose a new destination filename.')
        random.Random(seed).shuffle(groups)
        n_val = max(1, min(len(groups)-1, round(len(groups)*val_fraction)))
        val = set(groups[:n_val])
        assignment = {r['image_id']: 'val' if r['group'] in val else 'train' for r in rows}
    for r in rows:
        r['split'] = assignment[r['image_id']]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        shutil.copy2(destination, destination.with_name(destination.stem + '.backup_' + stamp + '.csv'))
    temporary = destination.with_suffix('.csv.tmp')
    with temporary.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    temporary.replace(destination)
    marker.write_text(json.dumps(dict(seed=seed, val_fraction=val_fraction,
        groups={r['image_id']: r['group'] for r in rows}, assignment=assignment),
        indent=2, ensure_ascii=False), encoding='utf-8')
    return rows
