"""Build a source-only server notebook ZIP; never include weights or user images."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest = json.loads((root / 'SOURCE_SHA256.json').read_text(encoding='utf8'))
    names = sorted([*manifest, 'SOURCE_SHA256.json'])
    contents = {}
    blocked = {'projects', 'test-output', '.venv', '.git', '__pycache__', 'node_modules', 'wheelhouse', 'downloads'}
    allowed = {'.py', '.js', '.cjs', '.css', '.html', '.md', '.txt', '.json', '.bat', '.cfg', '.ipynb'}
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or set(relative.parts) & blocked:
            raise ValueError(f'Unsafe archive path: {name}')
        if relative.suffix not in allowed and relative.name not in {'.gitignore', 'LICENSE', 'ABL_LICENSE'}:
            raise ValueError(f'Not a source file: {name}')
        raw = (root / relative).read_bytes().replace(b'\r\n', b'\n')
        if name in manifest and hashlib.sha256(raw).hexdigest() != manifest[name]:
            raise ValueError(f'Stale source hash: {name}; run tools/update_source_manifest.py first')
        if relative.suffix == '.py':
            ast.parse(raw, filename=name)
        if relative.suffix == '.ipynb':
            notebook = json.loads(raw)
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    if cell['outputs'] or cell['execution_count'] is not None:
                        raise ValueError('Notebook must not contain local execution output')
                    ast.parse(''.join(cell['source']))
        contents[name] = raw.replace(b'\n', b'\r\n') if name.endswith('.bat') else raw
    for name in ('setup.ipynb', 'run.py', 'web/index.html',
                 'adaptation_backend/vendor/segment-anything/segment_anything/__init__.py'):
        if name not in contents:
            raise ValueError(f'Missing required source: {name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Do not replace previous releases.
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in contents.items():
            archive.writestr('TEM_Analyzer_v2/' + name, raw)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('ZIP CRC failure')
        for name, expected in manifest.items():
            actual = hashlib.sha256(archive.read('TEM_Analyzer_v2/' + name).replace(b'\r\n', b'\n')).hexdigest()
            if actual != expected:
                raise RuntimeError(f'Packaged hash mismatch: {name}')
    report = {'file': output.name, 'files': len(names), 'bytes': output.stat().st_size,
              'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'crc_and_source_hashes': 'PASS',
              'scope': 'v2.3.0 source + server setup notebook; no weights/images/venv/projects'}
    output.with_suffix('.sha256').write_text(report['sha256'] + '  ' + output.name + '\n', encoding='utf8')
    output.with_suffix('.verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    build(args.root, args.output)
