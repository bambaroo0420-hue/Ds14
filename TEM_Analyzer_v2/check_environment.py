"""Standard-library-only preflight. Never downloads packages or model weights."""
import argparse
import importlib.util
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import struct
import sys

REQUIRED = {'fastapi':'fastapi', 'uvicorn':'uvicorn', 'python-multipart':'python_multipart',
            'numpy':'numpy', 'Pillow':'PIL', 'scipy':'scipy',
            'opencv-python-headless':'cv2', 'matplotlib':'matplotlib'}


def check(verbose=False):
    print('Python:',sys.executable)
    valid=sys.version_info>=(3,11) and struct.calcsize('P')==8
    if not valid:print('Requires 64-bit Python 3.11 or newer.')
    missing=[]
    for package,module in REQUIRED.items():
        try:found=importlib.util.find_spec(module) is not None
        except (ImportError,ValueError):found=False
        # Older python-multipart releases expose the legacy module name.
        if not found and package=='python-multipart':
            try:found=importlib.util.find_spec('multipart') is not None
            except (ImportError,ValueError):pass
        if not found:missing.append(package)
        elif verbose:
            try:print(package,version(package))
            except PackageNotFoundError:print(package,'module available')
    if missing:
        print('Missing required packages:',', '.join(missing))
        print('Run install_windows.bat once in the extracted TEM_Analyzer_v2 folder.')
        print('Offline: install_windows.bat --offline (matching wheels required in wheelhouse).')
    app=Path(__file__).resolve().parent
    if Path(sys.prefix).resolve()!=app/'.venv':
        print('NOTE: Not using this app\'s .venv. start_windows.bat selects it explicitly.')
    if verbose:
        for module in ('torch','torchvision','easyocr'):
            print('Optional',module,':','present' if importlib.util.find_spec(module) else 'not installed')
        print('SAM/OCR weights are separate local files; no automatic download.')
    return valid and not missing


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verbose',action='store_true')
    args=parser.parse_args();sys.exit(0 if check(args.verbose) else 1)
