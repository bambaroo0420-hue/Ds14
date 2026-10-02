"""Execute setup notebook code with safe CPU/local-test overrides, not company data."""
import argparse
import ast
import json
import os
from pathlib import Path
import socket
import shutil
import tempfile
from urllib.request import ProxyHandler, build_opener


def execute_cell(cell, namespace, overrides):
    tree = ast.parse(''.join(cell['source']))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in overrides:
                node.value = ast.Constant(overrides[target.id])
    ast.fix_missing_locations(tree)
    exec(compile(tree, f'setup.ipynb:{cell["id"]}', 'exec'), namespace)


def run(root, checkpoint, variant, ocr_dir='', run_sam_test=False):
    root = Path(root).resolve()
    original_cwd = Path.cwd()
    notebook = json.loads((root / 'setup.ipynb').read_text(encoding='utf8'))
    namespace = {}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    # Own isolated project only. The source/model folders are never deleted.
    with tempfile.TemporaryDirectory(prefix='tem_server_notebook_') as directory:
        overrides = {'APP_DIR': str(root), 'REQUIRE_CUDA': False,
                     'USE_OCR': bool(ocr_dir), 'INSTALL_PACKAGES': False,
                     'SAM_VARIANT': variant, 'SAM_CHECKPOINT': str(Path(checkpoint).resolve()),
                     'ADAPTATION': '', 'OCR_DIR': str(Path(ocr_dir).resolve()) if ocr_dir else 'models/easyocr',
                     'PROJECT_DIR': directory, 'PORT': port, 'START_SERVER': True,
                     'LOAD_MODEL_ON_START': True, 'RUN_SAM_TEST': run_sam_test, 'STOP_SERVER': True}
        results = []
        try:
            for cell in notebook['cells']:
                if cell['cell_type'] != 'code':
                    continue
                execute_cell(cell, namespace, overrides)
                results.append({'cell': cell['id'], 'status': 'PASS'})
                if 'START_SERVER = False' in ''.join(cell['source']):
                    server = namespace['TEM_SERVER']
                    pid = server.process.pid
                    execute_cell(cell, namespace, overrides)
                    assert namespace['TEM_SERVER'].process.pid == pid, 'rerun spawned a second server'
                    opener = build_opener(ProxyHandler({}))
                    for path in ('/', '/web/app.js', '/web/style.css'):
                        with opener.open(server.url + path, timeout=10) as response:
                            assert response.status == 200
                            assert response.read(100)
                    state = server.request('/api/state')
                    assert state['model']['device'] == 'cpu'
                    assert state['model']['variant'] == variant
                    assert not state['images'], 'not an isolated empty test project'
                    results.append({'step': 'same PID rerun / UI assets / API / real SAM model', 'status': 'PASS'})
            assert namespace['TEM_SERVER'].process.poll() is not None
            with socket.socket() as sock:
                sock.settimeout(1)
                assert sock.connect_ex(('127.0.0.1', port)) != 0, 'child server still listening after stop'
        finally:
            os.chdir(original_cwd)
            server = namespace.get('TEM_SERVER')
            if server is not None and not server.stop():
                raise RuntimeError('Owned test server still running; do not delete its project')
    return {'cells': results, 'scope': 'CPU local notebook code execution, no company images or GPU',
            'sam_smoke_in_notebook': run_sam_test, 'server_stopped': True,
            'tools_directory_present': (root / 'tools').is_dir()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--variant', choices=('vit_b', 'vit_l', 'vit_h'), default='vit_b')
    parser.add_argument('--ocr-dir', default='')
    parser.add_argument('--run-sam-test', action='store_true')
    parser.add_argument('--without-tools', action='store_true', help='Run a source-only copy with no tools directory')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    # Keep the local CPU review responsive; do not set this in the server notebook.
    os.environ.setdefault('OMP_NUM_THREADS', '4')
    os.environ.setdefault('MKL_NUM_THREADS', '4')
    if args.without_tools:
        source = Path(args.root).resolve()
        manifest = json.loads((source / 'SOURCE_SHA256.json').read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory(prefix='tem_notebook_no_tools_') as directory:
            for name in manifest:
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe source manifest path')
                if relative.parts[0] == 'tools':
                    continue
                target = Path(directory) / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
            report = run(directory, args.checkpoint, args.variant, args.ocr_dir, args.run_sam_test)
    else:
        report = run(args.root, args.checkpoint, args.variant, args.ocr_dir, args.run_sam_test)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
