# 설치와 회사 오프라인 실행

## 회사 GPU 서버와 setup.ipynb

`TEM_Analyzer_v2` 전체 폴더를 회사 서버의 쓰기 가능한 작업 경로에 올리고, 루트의 `setup.ipynb`를 JupyterLab에서 엽니다. **setup r2는 ABL 1.4의 직접 pip 설치 방식을 사용하며 `tools.server_setup` import/실행 의존성이 없습니다.** 첫 셀은 기본 Python 모듈로 경로만 확인합니다. 기존 v2.3.0 전체 프로그램 폴더가 있으면 새 노트북만 교체해도 됩니다. 단, 모델 경로 등 노트북 설정은 다시 입력하세요. 빈 폴더에 노트북만 넣는 경우에는 앱 소스가 없으므로 실행할 수 없습니다. `run.py`, `tem_analyzer`, `web`, `adaptation_backend`, requirements는 여전히 필요합니다. 이 노트북은 Analyzer 실행용이며 ABL 학습/데이터 분할/GT 변환을 다시 실행하지 않습니다.

### ABL 1.4에서 가져올 것

| 용도 | ABL 쪽 파일 | Analyzer 배치 위치 |
|---|---|---|
| 기본 SAM (필수) | `weights/sam_vit_h_4b8939.pth` | `models/sam_vit_h_4b8939.pth` |
| 학습 Decoder 또는 Refiner (선택) | `02_evaluate_export.ipynb`에서 내보낸 폴더의 `adaptation.pt` | `models/abl14/decoder_abl/adaptation.pt` 등 실험별 별도 폴더 |
| 학습 설정 기록 (선택) | export 폴더의 `inference_settings.json`, `model_manifest.json` | 해당 `adaptation.pt` 옆, 추적·참고용 (UI가 JSON을 자동 적용하지 않음) |
| OCR 검출 (OCR 사용 시 필수) | ABL 패키지에는 미포함 | `models/easyocr/craft_mlt_25k.pth` |
| OCR 영어 인식 (OCR 사용 시 필수) | ABL 패키지에는 미포함 | `models/easyocr/english_g2.pth` |

기본 SAM만 사용할 때는 `ADAPTATION=''`로 둡니다. 실험 이름은 예시이며 실제 ABL export 경로는 그 노트북의 출력값을 확인하세요. `runs/.../best.pt`도 동일 schema=1 bundle인 경우 로더가 받을 수 있지만, 추론 설정을 반영한 export `adaptation.pt`를 우선 사용하세요. 서로 다른 실험의 `adaptation.pt`를 같은 폴더에 덮어쓰지 마세요. decoder와 refiner를 동시에 결합하는 설정은 아닙니다.

학습 시 사용한 기본 SAM 파일과 SHA256, `model_type`, `preprocessing=uint8`, state 구조가 맞아야 합니다. `adaptation.pt`는 기본 SAM을 대체하지 않습니다. ViT-H로 학습한 decoder를 ViT-B 가중치에 연결할 수 없습니다. ABL의 `temlab`, `vendor`, `requirements.txt`, `.venv`, `config.local.json`, 학습 이미지/GT/cache를 Analyzer에 덮어쓸 필요가 없습니다. 필요한 SAM 소스와 Refiner 코드는 Analyzer에 포함되어 있습니다. 학습 시 `encoder_amp`와 현재 Analyzer 추론 정밀도 차이가 있으므로 같은 형식의 bundle을 읽는 것과 수치가 완전히 같은 것은 구분하세요.

이미 같은 서버에 가중치가 있으면 복사 대신 노트북의 `SAM_CHECKPOINT`/`ADAPTATION`에 절대 경로를 넣어도 됩니다. 기존 프로젝트 이전은 `project.json`, images, masks 등 **프로젝트 폴더 전체**를 복사한 뒤 `PROJECT_DIR`로 지정합니다. 원본 사진만 가져오는 경우는 UI에서 업로드합니다. 자동으로 ABL 학습 데이터나 Analyzer 프로젝트를 덮어쓰지 않습니다.

### 실행 순서

1. ABL이 정상 동작했던 CUDA 커널을 선택하고 Python 3.11 이상/64-bit인지 확인합니다. 학습 프로세스가 실행 중인 환경에 패키지를 설치하지 마세요. 별도 환경 복제가 가능하면 그 환경을 사용합니다.
2. 설치 셀은 ABL과 같이 기본 `INSTALL_PACKAGES=True`입니다. 최초 패키지 보충 뒤에는 False로 둡니다. torch/torchvision과 이미 설치된 주요 수치 패키지는 버전을 고정합니다. 호환성 충돌은 오류로 멈추며 강제 업그레이드하지 않습니다. 설치 중 다른 간접 의존성은 추가/변경될 수 있으므로 공유 학습 환경 변경은 서버 정책을 따르세요.
3. 설정 이름도 ABL과 같습니다. 사내 미러는 `PIP_INDEX_URL`, 오프라인은 서버 OS/Python/CUDA에 맞는 `WHEELHOUSE`, torch가 누락된 새 환경은 승인된 `TORCH_INDEX_URL` 또는 wheelhouse를 지정합니다. 기존 CUDA torch 쌍을 재설치하지 않습니다. 일부만 있으면 기존 버전을 고정하고 호환 쌍을 resolver로 찾으며 충돌하면 멈춥니다. 기존 ABL CUDA 커널을 그대로 쓰는 경우 보통 저장소 설정을 바꿀 필요가 없습니다. 새 CUDA 드라이버나 버전을 노트북이 임의로 지정하지 않습니다.
4. GPU 환경 검사에서 실제 CUDA tensor 연산과 torchvision NMS까지 확인합니다. `REQUIRE_CUDA=True`일 때 CUDA가 없으면 CPU로 조용히 전환하지 않고 중단합니다. CPU 시험은 명시적으로 False로 둡니다.
5. 파일 검사, 합성 이미지의 실제 SAM 두 번 추론(첫 인코딩/임베딩 재사용), 선택적인 로컬 OCR을 검사합니다. 별도 Python 프로세스가 끝나면 테스트 모델 메모리가 해제됩니다. 결과는 실행 확인이지 회사 영상 정확도 증명이 아닙니다.
6. `START_SERVER=True`로 실행하고 웹 UI에 접속합니다. 같은 Python으로 별도 프로세스를 실행하며, 모델은 선택적으로 서버에 한 번 로드합니다. CUDA 로드/OOM 오류가 나면 로그를 확인하세요. 실행 중 ABL 학습과 GPU 메모리를 경쟁할 수 있습니다.
7. 다음 접속은 `INSTALL_PACKAGES=False`, 필요하면 `RUN_SAM_TEST=False`로 시작합니다. 패키지/가중치는 다시 설치·다운로드하지 않지만 새 서버 프로세스에는 모델 메모리 로드가 필요합니다.

### 원격 UI 접속 — 회사 정책에 맞는 포트 전달

서버는 인증 없는 앱을 외부에 노출하지 않도록 `127.0.0.1`만 사용합니다. 서버에서 출력된 localhost를 PC에서 바로 열면 **PC 자신**에게 연결되므로 포트 전달이 필요합니다.

SSH가 허용된 경우 **사용자 PC 터미널**에서 (주소/계정은 본인 서버 값):

```text
ssh -N -L 8765:127.0.0.1:8765 USER@SERVER
```

그다음 PC 브라우저에서 `http://127.0.0.1:8765/`를 엽니다. VS Code Remote-SSH의 Ports 탭에서 **Private**로 포트 8765를 전달해도 됩니다. SSH 대상 호스트와 노트북 커널이 서로 다른 컨테이너/계산 노드라면 위 명령만으로 연결되지 않습니다. IT가 허용한 계산 노드 전달 경로가 필요합니다. 임의로 0.0.0.0, 공개 터널, 방화벽 개방, 인증서 검사 해제를 사용하지 마세요.

**현재 UI는 `/api`, `/web` 루트 절대 경로를 사용하므로 일반 JupyterHub `/user/.../proxy/8765/` 링크만 붙이면 정상 동작한다고 보장할 수 없습니다.** 노트북은 그런 링크를 성공 링크처럼 제공하지 않습니다. SSH 없이 Jupyter 프록시만 가능한 회사 서버라면 URL-prefix 대응이 별도로 필요합니다. Jupyter Server Proxy는 커널 환경이 아니라 Jupyter 서버 환경에 설치/활성화되어야 하므로 노트북에서 자동 설치하지 않습니다. [공식 설치 안내](https://jupyter-server-proxy.readthedocs.io/en/latest/install.html), [프록시 경로 규칙](https://jupyter-server-proxy.readthedocs.io/en/latest/server-process.html).

같은 프로젝트를 두 서버/여러 사용자가 동시에 편집하지 마세요. 노트북 재실행은 자신이 실행한 프로세스를 재사용하고 이미 사용 중인 다른 포트를 강제 종료하지 않습니다. 커널 재시작 시 Python의 프로세스 참조는 사라지지만 웹 서버가 남을 수 있습니다. 가능하면 UI 작업/저장을 마친 뒤 종료 셀을 실행하고 커널을 재시작하세요. Windows의 프로세스 종료는 강제 종료 방식이므로 저장 중 종료하지 마세요. 장기 운영·다중 사용자·로그인 기능·Jupyter idle 종료와 무관한 상시 서비스는 이 setup 노트북의 범위가 아닙니다.

### GPU 성능과 검증 범위

SAM의 이미지 인코딩·프롬프트 추론과 학습 Decoder/Refiner가 CUDA 대상입니다. OCR은 현재 `gpu=False`, Gradient/DP·회전·두께/CD는 NumPy/OpenCV 중심 CPU 처리입니다. 일괄 SAM은 GPU에서 이미지들을 순차 처리하며 여러 GPU에 자동 분산하지 않습니다. 속도 향상 배수는 GPU/이미지 크기/점 수에 따라 달라 실측 없이 보장하지 않습니다. ViT-H 메모리가 부족하면 먼저 다른 학습 프로세스의 점유를 확인하세요. H decoder를 유지한 채 기본 모델만 B로 바꾸면 안 됩니다. 새로 설치해야 할 CUDA 쌍은 [PyTorch 공식 선택기](https://pytorch.org/get-started/locally/)와 서버 IT의 드라이버 정책을 확인하세요.

서버 setup 변경의 로컬 검증과 실제 회사 CUDA 서버 검증은 별개입니다. 실제 회사 ABL checkpoint 및 회사 GPU에서는 사용자가 위 환경/추론 셀을 실행해야 최종 호환성을 확인할 수 있습니다.

2026-10-01 최초 setup 로컬 검증: 기존 198개와 setup 신규 15개를 포함한 Python 테스트 **213개 통과**(34.986초). 설치 스위치/기존 CUDA 버전 고정/오프라인 옵션/파일 누락/포트 충돌은 단위 테스트로 확인했으며, 회사 미러에 실제 설치한 것은 아닙니다. 실제 로컬 ViT-B 합성 추론은 모델 로드 3.606초, 첫 추론 13.375초, 임베딩 재사용 0.105초였고 OCR도 실행했습니다. 이는 CPU 합성 시험 값이며 GPU 배속/회사 정확도를 나타내지 않습니다. CUDA 필수 설정에서는 CPU-only 환경을 정상적으로 차단했습니다. 회사 ABL 학습 파일·Linux CUDA·JupyterHub 프록시의 실구동은 미검증입니다.

setup r2 수정: 설치 보조 모듈 의존성을 전부 제거했습니다. 첫 셀은 `tools` 폴더가 없고 외부 `tools` 모듈이 이미 import된 환경도 검사합니다. 설치 셀은 ABL 방식으로 현재 커널에 직접 pip를 호출하고 CUDA 버전 제약 및 오프라인 옵션을 유지합니다. 서버 시작/종료 등 후속 셀도 자체 포함합니다. 초기 오류의 실제 회사 원인이 파일 누락인지 모듈 이름 충돌인지는 확정하지 않았으나 이 의존성 자체를 없앴습니다. 검증 도구의 `--without-tools`는 회사 자료 없이 소스를 별도 복사하여 tools 디렉터리를 제외하고 노트북 전체를 실행합니다. `tools/server_setup.py`는 이전 CLI/테스트 호환용으로 남아 있지만 새 노트북에는 필요하지 않습니다.

setup r2 검증 결과: **217개 테스트 통과**(35.275초). tools 폴더가 없는 소스 복사본에서 노트북 코드 8개 셀을 실행하여 실제 CPU ViT-B 추론 2회·OCR·모델 로드·UI/API HTTP 접속·서버 재사용·종료/포트 해제를 확인했습니다. 설치 셀도 기존 환경에서 빈 오프라인 wheelhouse로 실제 실행하여 모든 요구 패키지가 이미 설치되어 있음을 확인했고 다운로드·패키지 교체 없이 pip check가 통과했습니다. 새로운 회사 환경에 패키지를 설치한 결과는 아닙니다.

## 최초 준비와 매일 실행

### v2.2.9 ZIP의 실행 순서와 오류 진단

1. ZIP 내부 `TEM_Analyzer_v2` 폴더를 완전히 압축 해제합니다. ZIP 안에서 BAT를 바로 실행하지 않습니다.
2. 기존 프로젝트 폴더(`project.json`, `images`, `masks` 등 전체)와 가중치를 보존합니다. 새 코드로 이 폴더를 덮어쓰지 않습니다. 가상환경 폴더는 다른 PC로 복사하지 않습니다.
3. 최초에는 `install_windows.bat`, 매일은 `start_windows.bat`을 실행합니다. 시작 BAT는 자체 폴더로 이동하고 자신의 `.venv` Python을 사용합니다. 모델은 UI에서 메모리로 로드하되 매일 다시 다운로드할 필요는 없습니다.
4. `No module named uvicorn` 같은 누락은 새 사전 검사에서 Python 경로와 누락 목록으로 안내합니다. `diagnose_windows.bat`은 패키지 상태만 출력하며 설치·삭제를 하지 않습니다.
5. 완전 오프라인은 아래 절차대로 동일 Python/Windows용 wheel을 준비한 뒤 `install_windows.bat --offline`을 사용합니다. 네트워크 제한을 우회하거나 인증서 검증을 끄지 마세요.
6. 기존 프로젝트를 열 때는 `start_windows.bat --project "프로젝트 폴더 전체 경로"`를 사용합니다. 같은 프로젝트를 여러 서버에서 동시에 열지 마세요. 기본 포트 변경은 `--port 8766`처럼 전달할 수 있습니다.

VS Code의 실행 버튼은 다른 Python을 선택할 수 있습니다. 먼저 `start_windows.bat`으로 실행을 확인하세요. `py_compile`에는 검사할 파일명이 필요하며, `python -m py_compile`까지만 실행하면 filenames 오류가 납니다. 이 검사만으로 기능이 검증되는 것은 아닙니다.

`파일 저장/접근 실패 … 편집을 차단했습니다`가 표시되면 서버를 종료하고 프로젝트 전체를 백업하세요. 실제 폴더의 쓰기 권한/파일 잠금 원인을 확인한 뒤 다시 실행해야 합니다. 관리자 실행이나 보안 기능 해제를 기본 해결책으로 권장하지 않습니다. `.tmp`/`project.json`을 임의 삭제하지 마세요. 일시적 잠금에 대한 대기는 한 저장 시도당 최대 약 5.6초이며 영구적인 권한 오류는 해결하지 못합니다.

`이미지 읽기 실패`는 손상된/미지원 입력을 뜻하며 저장 오류와 구분합니다. `업로드 임시 파일 읽기 실패`이면 서버 터미널 오류와 임시 폴더 접근 상태를 확인하세요. 회사에서 보고된 짧은 `read` 문구의 정확한 원인은 원본 traceback이 없어 확정하지 않았습니다.

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

v2.2.3 검증 PC는 `opencv-python-headless 5.0.0.93` (`cv2.__version__=5.0.0`)이 이미 설치돼 있었습니다.
기존 requirements의 `<5` 상한과 실제 환경이 달라 `<6`으로 조정했습니다. 이 작업 중 OpenCV를 재설치하지 않았습니다.
기존 기능은 `>=4.8` 범위를 유지하지만 이 반복에서 4.x 전체 조합을 다시 검증한 것은 아닙니다.
새 **양쪽 제외 ECC**는 `findTransformECCWithMask` 존재를 검사하며 미지원이면 오류 안내 후 중단합니다.
기존 normalized/ECC로 조용히 바꾸지 않습니다. 회사 환경에서 아래로 확인하세요.

```powershell
.\.venv\Scripts\python.exe -c "import cv2; print(cv2.__version__, hasattr(cv2, 'findTransformECCWithMask'))"
```

일반 ECC와 Grid/SAM 사용 때문에 새 정합 API를 반드시 설치할 필요는 없습니다.
해당 실험 모드가 필요하면 별도 검증 가상환경에서 같은 플랫폼의 5.0.0.93 wheel로 테스트 후 freeze/wheelhouse에 포함하세요.
OpenCV 패키지 여러 종류를 동시에 설치하지 마세요. `pip check` 통과만으로 프로젝트의 requirements 버전 일치를 보장하지는 않습니다.

- `ModuleNotFoundError`: 설치와 실행을 모두 `.venv\Scripts\python.exe`로 수행했는지 확인.
- 모델 파일 없음: 상대 경로는 `TEM_Analyzer_v2` 기준. 시작 BAT는 해당 폴더로 이동합니다.
- torchvision 연산 오류: torch/torchvision 호환 조합을 다시 설치.
- CUDA 없음: CPU로 확인한 뒤 회사 드라이버·PyTorch 조합 검증.
- OCR 문자를 못 읽음: 원본 해상도, 대비, 단위·숫자 확인 후 수동 스케일/박스를 사용.
- 여러 사람이 같은 프로젝트 폴더를 다른 서버에서 동시에 열면 안 됩니다. 프로젝트당 서버 하나를 사용하세요.
