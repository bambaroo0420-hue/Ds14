# 설치와 회사 오프라인 실행

## 최초 준비와 매일 실행

`install_windows.bat`는 최초 설치 또는 의존성 변경 때만 실행합니다.
`start_windows.bat`는 항상 같은 `.venv\Scripts\python.exe`를 사용하며 설치하지 않습니다.
가상환경을 활성화해도 패키지가 사라지지 않습니다. 매번 설치가 필요했다면
설치한 Python과 실행한 Python이 달랐는지 아래 명령으로 확인하세요.

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
.\.venv\Scripts\python.exe -m pip --version
```

Python 3.11 이상 64비트를 준비한 후 `TEM_Analyzer_v2` 폴더에서:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# CPU 예시. GPU는 아래 공식 PyTorch 설치 선택기의 호환 조합을 사용합니다.
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

[PyTorch 공식 설치 선택기](https://pytorch.org/get-started/locally/)에서
회사 PC의 OS, Python, CUDA 드라이버에 맞는 torch/torchvision 조합을 선택하세요.
두 패키지를 서로 다른 출처·호환되지 않는 버전으로 설치하지 마세요.
SAM 소스는 `adaptation_backend/vendor/segment-anything`에 포함되어 있습니다.
프로그램 실행 시 GitHub 접속이나 별도 `pip install segment-anything`은 필요 없습니다.

## 가중치 직접 다운로드

SAM은 아래 중 **하나**만 받으면 됩니다. 우선 CPU 확인에는 ViT-B를 권장합니다.
체크포인트 파일과 화면의 모델 종류가 같아야 합니다.

| 모델 | 공식 다운로드 | 배치 경로 |
|---|---|---|
| SAM ViT-B | [sam_vit_b_01ec64.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth) | `models/sam_vit_b_01ec64.pth` |
| SAM ViT-L | [sam_vit_l_0b3195.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth) | `models/sam_vit_l_0b3195.pth` |
| SAM ViT-H | [sam_vit_h_4b8939.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth) | `models/sam_vit_h_4b8939.pth` |
| EasyOCR 검출 | [craft_mlt_25k.zip](https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip) | ZIP을 풀어 `models/easyocr/craft_mlt_25k.pth` |
| EasyOCR 영어 | [english_g2.zip](https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip) | ZIP을 풀어 `models/easyocr/english_g2.pth` |

원본 안내: [SAM](https://github.com/facebookresearch/segment-anything),
[EasyOCR](https://github.com/JaidedAI/EasyOCR). Tesseract는 사용하지 않습니다.
영어·숫자·nm/µm용 기본 OCR을 제공합니다. 한글 인식에는 EasyOCR의 한국어 모델이 추가로 필요합니다.
SAM2 가중치를 이 SAM1 로더에 넣으면 안 됩니다.

1. 인터넷 가능한 PC에서 링크의 파일을 다운로드합니다.
2. 위 구조대로 회사 PC의 프로그램 폴더에 복사합니다. ZIP 자체가 아니라 내부 `.pth`를 배치합니다.
3. `start_windows.bat` 실행 후 `http://127.0.0.1:8765`를 엽니다.
4. `2 SAM·레이어 → SAM 모델 설정`에서 체크포인트 경로, 모델 종류, 장치를 지정하고 **모델 로드**를 누릅니다.
5. OCR 폴더를 `models/easyocr`로 지정합니다. 자동 다운로드는 비활성화되어 있습니다.

패키지 설치와 가중치 다운로드는 최초 준비입니다. 프로그램 재시작 후의 **메모리 로드**는 필요하지만,
이미지마다 다시 다운로드하지 않습니다. SAM 이미지 임베딩과 EasyOCR Reader는 프로세스 안에서 재사용합니다.
가중치는 코드 저장소에 올리지 않습니다.

## 완전 오프라인 패키지 설치

회사 PC와 같은 Windows/Python 버전·CPU/GPU 조합의 인터넷 PC에서 준비합니다.
다른 플랫폼의 wheel이나 `.venv` 폴더 자체를 복사하면 정상 동작을 보장할 수 없습니다.

```powershell
python -m pip download --dest wheelhouse -r requirements.txt -r requirements-ocr.txt
# GPU용 torch/torchvision wheel은 선택한 공식 인덱스에서 별도로 받아 같은 폴더에 추가
```

회사 PC로 소스, `wheelhouse`, 가중치를 옮긴 뒤:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt -r requirements-ocr.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe run.py --port 8765
```

CPU 기본 wheel 다운로드가 GPU 의존성을 포함할 수 있으므로 준비 PC에서 실제 설치·추론까지 검증하고,
`pip freeze > requirements-lock.txt`로 검증한 조합을 기록해 함께 전달하세요.

## 흔한 오류

- `ModuleNotFoundError`: 설치와 실행을 모두 `.venv\Scripts\python.exe`로 수행했는지 확인.
- 모델 파일 없음: 상대 경로는 `TEM_Analyzer_v2` 기준. 시작 BAT는 해당 폴더로 이동합니다.
- torchvision 연산 오류: torch/torchvision 호환 조합을 다시 설치.
- CUDA 없음: CPU로 확인한 뒤 회사 드라이버·PyTorch 조합 검증.
- OCR 문자를 못 읽음: 원본 해상도, 대비, 단위·숫자 확인 후 수동 스케일/박스를 사용.
- 여러 사람이 같은 프로젝트 폴더를 다른 서버에서 동시에 열면 안 됩니다. 프로젝트당 서버 하나를 사용하세요.
