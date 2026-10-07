"""Notebook setup support. No installation, downloads or server start on import."""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

SAM_NAMES = {'vit_h': 'sam_vit_h_4b8939.pth', 'vit_l': 'sam_vit_l_0b3195.pth',
             'vit_b': 'sam_vit_b_01ec64.pth'}
PRESERVE = ('torch', 'torchvision', 'numpy', 'scipy', 'Pillow', 'matplotlib',
            'opencv-python-headless')


def app_root(path):
    root = Path(path).expanduser().resolve()
    for name in ('run.py', 'requirements.txt', 'tem_analyzer/sam_service.py',
                 'adaptation_backend/vendor/segment-anything/segment_anything/__init__.py'):
        if not (root / name).is_file():
            raise FileNotFoundError(f'TEM_Analyzer_v2 전체 폴더가 필요합니다: {root / name}')
    return root


def installed_versions():
    result = {}
    for name in PRESERVE:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def pip_source(wheelhouse='', index=''):
    if wheelhouse:
        folder = Path(wheelhouse).expanduser().resolve()
        if not folder.is_dir():
            raise FileNotFoundError(f'wheelhouse 폴더 없음: {folder}')
        return ['--no-index', '--find-links', str(folder)]
    if index:
        if not index.startswith('https://') or '@' in index or '?' in index or '#' in index:
            raise ValueError('패키지 저장소는 자격 증명 없는 HTTPS URL을 사용하세요.')
        return ['--index-url', index]
    return []  # Existing company pip configuration remains in effect.


def install_packages(root, *, enabled=False, use_ocr=True, wheelhouse='',
                     package_index='', torch_index='', torch_packages=()):
    """Explicit opt-in; preserve an installed CUDA pair and ABL numerical stack."""
    root = app_root(root)
    if not enabled:
        print('패키지 설치 생략. 최초 설치/패키지 누락 때만 INSTALL_PACKAGES=True.')
        return
    if sys.version_info < (3, 11):
        raise RuntimeError('Analyzer는 Python 3.11 이상이 필요합니다. 다른 커널을 선택하세요.')
    source = pip_source(wheelhouse, package_index)
    torch_source = pip_source(wheelhouse, torch_index or package_index)
    before = installed_versions()
    print('보존할 기존 패키지:', before)
    pair = [before['torch'], before['torchvision']]
    if bool(pair[0]) != bool(pair[1]):
        raise RuntimeError('torch/torchvision 중 하나만 있습니다. IT가 호환 쌍을 복구한 뒤 재실행하세요.')
    if not all(pair):
        specs = list(torch_packages)
        if (len(specs) != 2 or
                not re.fullmatch(r'torch==[0-9][A-Za-z0-9.+]*', specs[0]) or
                not re.fullmatch(r'torchvision==[0-9][A-Za-z0-9.+]*', specs[1])):
            raise ValueError('CUDA 조합을 추측하지 않습니다. TORCH_PACKAGES에 승인된 torch==버전, torchvision==버전을 지정하세요.')
    else:
        specs = []
    with tempfile.TemporaryDirectory(prefix='tem_setup_') as directory:
        constraints = Path(directory) / 'preserve.txt'
        def write_constraints(versions):
            constraints.write_text(''.join(f'{k}=={v}\n' for k, v in versions.items() if v), encoding='utf8')
        def install(args, origin):
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                            '--upgrade-strategy', 'only-if-needed', '-c', str(constraints),
                            *origin, *args], cwd=root, check=True)
        write_constraints(before)
        if specs:
            install(specs, torch_source)
        # Pin the newly installed pair too: OCR must not replace CUDA torch.
        pinned = installed_versions()
        write_constraints(pinned)
        requirements = ['-r', str(root / 'requirements.txt')]
        if use_ocr:
            requirements += ['-r', str(root / 'requirements-ocr.txt')]
        install(requirements, source)
    subprocess.run([sys.executable, '-m', 'pip', 'check'], cwd=root, check=True)
    after = installed_versions()
    if any(after[k] != v for k, v in before.items() if v):
        raise RuntimeError('보존 대상 버전이 변경됐습니다. 설치 기록을 확인하세요.')
    print('설치 완료. 이 노트북의 후속 검사는 동일 Python의 새 프로세스에서 실행합니다.')


def model_paths(root, variant='vit_h', checkpoint='', adaptation='', ocr_dir='models/easyocr', use_ocr=True):
    root = app_root(root)
    if variant not in SAM_NAMES:
        raise ValueError('SAM1 vit_h/vit_l/vit_b만 지원합니다. SAM2 가중치는 호환되지 않습니다.')
    def resolve(value):
        p = Path(value).expanduser()
        return (root / p).resolve() if not p.is_absolute() else p.resolve()
    base = resolve(checkpoint or f'models/{SAM_NAMES[variant]}')
    adapted = resolve(adaptation) if adaptation else None
    ocr = resolve(ocr_dir)
    required = [base] + ([adapted] if adapted else [])
    if use_ocr:
        required += [ocr / 'craft_mlt_25k.pth', ocr / 'english_g2.pth']
    missing = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise FileNotFoundError('파일 없음/빈 파일 (자동 다운로드 안 함):\n' + '\n'.join(missing))
    return {'checkpoint': str(base), 'variant': variant, 'adaptation_path': str(adapted) if adapted else None,
            'ocr_dir': str(ocr)}


def environment_report(root, *, require_cuda=True, use_ocr=True):
    root = app_root(root)
    import struct
    if sys.version_info < (3, 11) or struct.calcsize('P') != 8:
        raise RuntimeError('Python 3.11 이상 / 64-bit 커널 필요')
    import fastapi, uvicorn, numpy, scipy, PIL, cv2, matplotlib, httpx  # noqa: F401
    import torch, torchvision
    try:
        import python_multipart  # noqa: F401
    except ImportError:
        import multipart  # noqa: F401
    if use_ocr:
        import easyocr  # noqa: F401
    sys.path.insert(0, str(root / 'adaptation_backend/vendor/segment-anything'))
    from segment_anything import sam_model_registry  # noqa: F401
    cuda = torch.cuda.is_available()
    if require_cuda and not cuda:
        raise RuntimeError('CUDA 사용 불가. GPU 할당/드라이버/torch 빌드/커널 확인. CPU 시험만 하려면 REQUIRE_CUDA=False.')
    devices = ['cpu', 'cuda'] if require_cuda else ['cpu']
    for device in devices:
        boxes = torch.tensor([[0., 0., 2., 2.], [0., 0., 1., 1.]], device=device)
        torchvision.ops.nms(boxes, torch.tensor([.9, .8], device=device), .5)
        x = torch.ones((32, 32), device=device)
        if not torch.isfinite(x @ x).all().item():
            raise RuntimeError(f'{device} tensor 연산 실패')
    if require_cuda:
        torch.cuda.synchronize()
    report = {'python': sys.executable, 'torch': torch.__version__, 'torchvision': torchvision.__version__,
              'cuda_build': torch.version.cuda, 'cuda_available': cuda, 'tested_devices': devices,
              'gpu': torch.cuda.get_device_name(0) if cuda else None,
              'gpu_total_GiB': round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if cuda else None,
              'ocr_device': 'cpu', 'masked_ecc_available': hasattr(cv2, 'findTransformECCWithMask')}
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def sam_smoke(root, checkpoint, variant, device, adaptation=None, ocr_dir=None):
    """Real local weights, synthetic pixels. Timings are NOT an accuracy score."""
    root = app_root(root)
    sys.path.insert(0, str(root))
    import numpy as np
    import torch
    from tem_analyzer.sam_service import ModelService
    model = ModelService()
    start = time.perf_counter()
    info = model.load(checkpoint, variant, device, adaptation_path=adaptation)
    if device == 'cuda':
        torch.cuda.synchronize()
    load_seconds = time.perf_counter() - start
    image = np.full((192, 256, 3), 30, dtype=np.uint8)
    image[60:130, 24:232] = 180
    timings = []
    for _ in range(2):
        if device == 'cuda':
            torch.cuda.synchronize()
        start = time.perf_counter()
        result = model.prompt(image, [[128, 96, 1]], [24, 60, 232, 130])
        if device == 'cuda':
            torch.cuda.synchronize()
        if result['mask'].shape != (192, 256) or not np.isfinite(result['probability']).all():
            raise RuntimeError('SAM 출력 크기/수치 검사 실패')
        timings.append({'seconds': round(time.perf_counter() - start, 3),
                        'embedding_reused': result['embedding_reused'], 'mask_pixels': int(result['mask'].sum())})
    if ocr_dir:
        from tem_analyzer.ocr import read_words
        read_words(image, ocr_dir, 'en')  # Loads + runs existing offline CPU OCR, no downloads.
    report = {'device': info['device'], 'variant': variant, 'adapted': info['adapted'],
              'load_seconds': round(load_seconds, 3), 'inference': timings,
              'ocr_executed': bool(ocr_dir), 'scope': 'runtime check only; not TEM segmentation accuracy'}
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


class NotebookServer:
    """Own-process-only lifecycle. No PID files, no killing unknown servers."""
    def __init__(self, root, project, port=8765):
        self.root = app_root(root)
        project = Path(project).expanduser()
        self.project = (self.root / project).resolve() if not project.is_absolute() else project.resolve()
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ValueError('PORT는 1024~65535 정수여야 합니다.')
        self.port = port
        self.url = f'http://127.0.0.1:{port}'
        self.process = None
        self.log_path = None

    def request(self, path, payload=None, timeout=10):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('이 노트북에서 시작한 서버가 실행 중이 아닙니다.')
        request = Request(self.url + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'Content-Type': 'application/json'} if payload is not None else {})
        # Only loopback: never send local API requests via a corporate HTTP proxy.
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f'HTTP {exc.code}: {exc.read(1000).decode("utf8", "replace")}') from exc

    def start(self, timeout=45):
        if self.process is not None and self.process.poll() is None:
            print('이미 실행 중:', self.url)
            return self.url
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', self.port))
            except OSError as exc:
                raise RuntimeError(f'포트 {self.port} 사용 중. 기존 프로세스를 종료하지 않습니다. 다른 포트를 선택하세요.') from exc
        self.project.mkdir(parents=True, exist_ok=True)
        # Check actual writes, not os.access (unreliable on network mounts/ACLs).
        with tempfile.TemporaryFile(dir=self.project):
            pass
        logs = self.root / 'test-output/server-setup'
        logs.mkdir(parents=True, exist_ok=True)
        self.log_path = logs / f'server-{self.port}-{time.time_ns()}.log'
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        with self.log_path.open('wb') as log:
            self.process = subprocess.Popen([sys.executable, '-u', str(self.root / 'run.py'),
                                             '--port', str(self.port), '--project', str(self.project)],
                                            cwd=self.root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('서버 시작 실패')
                try:
                    state = self.request('/api/state', timeout=1)
                    if 'schema_version' in state and self.process.poll() is None:
                        print('실행 중:', self.url, '\n프로젝트:', self.project, '\n로그:', self.log_path)
                        return self.url
                except (URLError, TimeoutError, OSError):
                    pass
                time.sleep(.25)
            raise TimeoutError('웹 서버 응답 대기 시간 초과')
        except BaseException:
            self.stop()
            print(self.log_path.read_text(encoding='utf8', errors='replace')[-4000:])
            raise

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            # Call only after UI jobs have completed and project saves are done.
            if os.name == 'nt':
                # A Windows venv python.exe may be a redirector with a child Python.
                # Terminating only the parent leaves uvicorn running and files locked.
                result = subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                                        capture_output=True, text=True,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode and self.process.poll() is None:
                    print('소유한 서버 트리 종료 실패:', result.stderr.strip())
                    return False
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                print('아직 종료 중입니다. 강제 종료/프로젝트 삭제를 하지 않았습니다.')
                return False
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['environment', 'smoke'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--cpu', action='store_true')
    parser.add_argument('--no-ocr', action='store_true')
    parser.add_argument('--checkpoint')
    parser.add_argument('--variant', choices=SAM_NAMES, default='vit_h')
    parser.add_argument('--adaptation')
    parser.add_argument('--ocr-dir')
    args = parser.parse_args()
    if args.action == 'environment':
        environment_report(args.root, require_cuda=not args.cpu, use_ocr=not args.no_ocr)
    else:
        if not args.checkpoint:
            parser.error('smoke에는 --checkpoint가 필요합니다.')
        sam_smoke(args.root, args.checkpoint, args.variant, 'cpu' if args.cpu else 'cuda', args.adaptation, args.ocr_dir)


if __name__ == '__main__':
    main()
