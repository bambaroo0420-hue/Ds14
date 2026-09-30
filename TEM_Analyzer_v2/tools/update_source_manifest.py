"""Mechanically rebuild hashes of source assets, never local models or projects."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
excluded={'.git','.venv','__pycache__','test-output','projects','node_modules','wheelhouse','downloads','.pytest_cache'}
source_suffixes={'.py','.js','.cjs','.css','.html','.md','.txt','.json','.bat','.cfg'}
source_names={'.gitignore','LICENSE','ABL_LICENSE'}
items={}
for p in sorted(root.rglob('*')):
    rel=p.relative_to(root)
    if not p.is_file() or any(x in excluded for x in rel.parts):continue
    if p.name in ('SOURCE_SHA256.json','requirements-lock.txt') or p.suffix in ('.pth','.pt','.pyc','.log'):continue
    if p.suffix not in source_suffixes and p.name not in source_names:continue
    # Source files are text. Normalize checkout CRLF to Git's canonical LF.
    items[rel.as_posix()]=hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
(root/'SOURCE_SHA256.json').write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Updated source hashes:',len(items))
