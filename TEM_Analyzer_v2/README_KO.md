# TEM Analyzer v2.3.0 — 시각화 워크벤치·Manual 그룹·Recipe v2

회사 GPU 서버/Jupyter용: 루트의 [setup.ipynb](setup.ipynb)를 실행하세요. ABL 1.4의 기본 SAM 가중치와 선택적인 `adaptation.pt`를 재사용하며, 파일 배치·기존 CUDA 패키지 보존·실제 추론 시험·웹 서버 실행/종료 절차가 포함되어 있습니다. 자세한 서버 접속/이전 방법은 [설치 문서의 서버 절](docs/INSTALL_KO.md#회사-gpu-서버와-setupipynb)을 보세요. SAM 외의 OCR·경계·계측 전체가 GPU로 전환되는 것은 아닙니다.

새 버전 변경/검증: [V230_IMPLEMENTATION_KO.md](docs/V230_IMPLEMENTATION_KO.md). 실제 조작 순서와 버튼 설명: [V230_USER_GUIDE_KO.md](docs/V230_USER_GUIDE_KO.md).

요청 누락·의도 일치·코드의 완성 후 재검토: [V230_FINAL_REVIEW_KO.md](docs/V230_FINAL_REVIEW_KO.md). **모든 논의 요구의 완성판은 아니며** 부분/미구현 항목을 명시합니다.

기존 Grid/feature 일괄 SAM, 프롬프트 재사용, 부분 GT 및 선택 마스크 회전·계측 기능은 유지됩니다. 새 UI는 원본 영상 위에 마스크/GT 진단을 표시하고 실제 회전 기준점·치수선을 별도 창에서 보여줍니다. 자동 결과는 재료 정답이 아니며 검수가 필요합니다.

v2.3.0에 통합: [레이어별 브러시 잠금·두 층 사이 Gradient/DP 빈틈 보정 사용법과 검증](docs/GAP_BRIDGE_AND_LOCKS_KO.md). 내부 구멍 자동 채움은 포함하지 않습니다. 해당 문서의 로컬 검토 시점 기록과 현재 배포 상태는 구분하세요.

Windows 소스 ZIP은 압축을 푼 뒤 처음 한 번 `install_windows.bat`, 이후에는 `start_windows.bat`으로 실행합니다. 패키지·가중치는 ZIP에 포함하지 않습니다. 문제가 생기면 `diagnose_windows.bat`과 [설치 안내](docs/INSTALL_KO.md)를 확인하세요. 기존 프로젝트·가중치는 별도 백업하고, 새 버전은 새 폴더에 설치하세요.

- [이번 오류 수정·기능별 검증 및 한계](docs/V229_REVIEW_KO.md)
- `준비한 프롬프트로 SAM 실행`: 후보를 모두 준비한 뒤 메타데이터 1회 저장, 일시적 Windows 잠금 재시도, 저장 실패 후 편집 차단.
- `5 일괄 처리 → 대상 이미지 스케일 확인·확정`: 표에서 미적용 검출값 저장과 최종 확정을 구분합니다. 검출값 저장만으로 제외 박스가 바뀌지는 않습니다.

SAM 후보를 레이어로 묶어 회전하고 두께/CD를 측정하는 로컬 도구입니다. **경계 보정과 GT 생성은 선택 사항이며 회전·계측의 선행 조건이 아닙니다.**

v2.2에서는 필요한 마스크만 선택 집합으로 저장해 **레이어 배정 없이** 부분 GT·회전·계측할 수 있습니다. 미선택 영역은 unknown입니다. 프롬프트 preset 재사용(크기 비율/ECC), 확대 OCR, 프레임 경계 오판 방지와 영상 방향 보조 추정을 추가했습니다.

- [v2.2 사용법·실제 검증·남은 한계](docs/V220_REVIEW_KO.md)
- [v2.2.1 계측 표본·품질 기준, 실제 5장 비교](docs/V221_REVIEW_KO.md)
- [v2.2.2 얇은 층 프로파일·실제 SAM 24회·회전 반례](docs/V222_REVIEW_KO.md)
- [v2.2.3 프롬프트 일괄 재사용·실제 SAM 16회·정합 실패 개선](docs/V223_REVIEW_KO.md)
- [v2.2.4 독립 ROI·실제 SAM 38회·crop 경계 보호·얇은 층 계측 한계](docs/V224_REVIEW_KO.md)
- [v2.2.5 기울어진 마스크의 계측 유효성 오류 수정·72개 대조시험](docs/V225_REVIEW_KO.md)
- [v2.2.6 직선층 ROI 사전정렬·실제 SAM 비교·미리보기 로딩 보완](docs/V226_REVIEW_KO.md)
- [v2.2.7 회전 기준 비교·일괄 실패/건너뜀·실제 GUI 검증](docs/V227_REVIEW_KO.md)
- [v2.2.8 두께·CD 동시 보존·실제 GUI ZIP·좌표 왕복 검증](docs/V228_REVIEW_KO.md)
- [5시간 개선 종합 검토·사용자 의도 일치도·남은 우선순위](docs/FINAL_5H_REVIEW_KO.md)
- [5시간 반복 개선 진행 기록](docs/ITERATION_VNEXT_KO.md)

기존 고정 위치 템플릿은 기본 비활성화입니다. `기존 위치 템플릿 켜기/끄기`로 제어하며, 이미지별 OCR 검출 박스는 독립적으로 작동합니다.

- **실행:** 최초 설치 후 `start_windows.bat` → `http://127.0.0.1:8765`.
- [설치·공식 체크포인트 링크·회사 오프라인 준비](docs/INSTALL_KO.md)
- [사용 순서·기능별 수정·테스트 명령](docs/DEVELOPMENT_KO.md)
- [모듈 구성과 수정 위치](docs/ARCHITECTURE_KO.md)
- [좌표·GT·측정 데이터 계약](docs/DATA_CONTRACT_KO.md)
- [실제 검증 결과와 한계](docs/VALIDATION_REPORT_KO.md)
- [추가점·노이즈 제거 및 분할 우선 일괄 처리](docs/PROMPTS_DENOISE_KO.md)
- [공개 이미지 14장 실제 검토·보완 우선순위](docs/PUBLIC_IMAGE_REVIEW_KO.md)
- [첨부 45° 이미지: 자동 경로 실패 및 보조 회전 검토](docs/ATTACHED_45DEG_REVIEW_KO.md)
- [변경 기록](docs/CHANGELOG_KO.md)

v2.1은 이미지별 문자/바 자동 검출, 레이어 공유 경계 Gradient+DP,
분리된 배정·검수, Ctrl/Shift 다중 선택·드래그, 삭제 복원,
회전 좌표 변환, 두께/CD, 일괄 처리·취소·실패 재시도를 추가합니다.
아래 v2.0.1 내용은 기존 기능 이력입니다. 새 작업 흐름과 설치 기준은 위 문서를 우선 참고하세요.

## 2026-09-29 수정: 레이어·제외 ROI·재분할 검수

- `레이어 추가`는 이름 입력창 없이 `Layer N`을 바로 생성합니다. 원하는 이름은 생성 후 `이름 수정`에서 바꿀 수 있습니다. API도 빈 이름/공백을 자동 이름으로 처리합니다.
- 글씨/스케일 제외 ROI를 드래그하면 기존 Grid·ML·수동점 중 제외 영역의 점을 제거합니다. Grid/ML 생성·SAM 실행·ROI 편집 전에 현재 이미지에 제외 영역을 자동 적용합니다. 서버도 오래된 제외 영역 안의 점을 추론 전에 걸러내며 마스크 출력에서 제외합니다. 다른 이미지 전체 적용은 기존 일괄 적용 기능을 사용하세요.
- ROI 재분할은 `재분할 미리보기` → 주황색 결과 확인 → `확인 후 새 후보 저장`의 순서입니다. 미리보기 중에는 프로젝트에 후보나 mask 파일을 만들지 않습니다. 취소/창 닫기는 저장하지 않습니다. 입력이 바뀌면 미리보기를 무효화합니다.
- 임시 미리보기는 15분 동안 유지되며 최대 4개입니다. 서버 재시작 또는 부모/모델/전처리 변경 후에는 다시 실행해야 저장할 수 있습니다.
- 설치 후 기존 서버를 종료하고 새 폴더에서 다시 실행하세요. 브라우저도 새로고침해야 합니다.

## 프로그램 개요

TEM 원본 해상도에서 SAM 후보 생성 → 기존 마스크 수정 → 레이어 확정 → 공유 경계 보정 → GT 출력까지 수행하는 로컬 도구입니다. `TEM_Analyzer_v1`과 별도 폴더/프로젝트로 실행합니다.

## 설치와 실행: Windows 로컬·회사망

**SAM 코드, Python 패키지, 모델 가중치는 서로 다른 준비물입니다.** `install_windows.bat`는 기본 UI 패키지만 설치합니다. SAM·OCR까지 사용하려면 아래 절차가 필요합니다. 명령은 압축을 푼 `TEM_Analyzer_v2` 폴더에서 PowerShell로 실행하세요.

| 준비물 | v2 ZIP에 포함? | 준비 방법 |
|---|---|---|
| 공식 SAM Python 소스 | 포함 | `adaptation_backend/vendor/segment-anything` 사용. git clone 불필요 |
| torch + torchvision | 미포함 | CPU/GPU에 맞는 한 쌍을 pip 또는 로컬 wheel로 설치 |
| SAM ViT-B/L/H 체크포인트 | 미포함 | 아래 `.pth` 중 사용할 모델 다운로드 |
| EasyOCR Python 패키지 | 미포함, OCR 사용 시 필요 | `requirements-ocr.txt`로 설치 |
| OCR 검출·영어 인식 가중치 | 미포함, OCR 사용 시 필요 | ZIP 2개를 풀어 `models/easyocr`에 `.pth` 배치 |

### 1. Python과 실행 환경

예시는 **Windows 64-bit + Python 3.11** 기준입니다. 준비 PC와 회사 PC의 OS·CPU 아키텍처·Python minor 버전을 맞추세요. 회사 서버가 Linux라면 Linux 환경에서 wheel을 준비해야 합니다. Windows용 `.venv`를 Linux로 복사해서 사용할 수 없습니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

이후 모든 명령도 같은 `.venv` Python으로 실행합니다. 가상환경 활성화나 PowerShell 실행 정책 변경은 필요하지 않습니다.

### 2. torch·torchvision 설치

**GPU가 없는 로컬 PC / CPU로 먼저 확인할 경우:**

```powershell
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**NVIDIA GPU 서버:** [PyTorch 공식 설치 선택기](https://pytorch.org/get-started/locally/)에서 해당 OS / Pip / Python / 지원 CUDA 조합을 선택하세요. 출력 명령의 `pip`를 `.\.venv\Scripts\python.exe -m pip`로 바꿔 실행합니다. `torch`와 `torchvision`을 **동일 명령·동일 CPU/CUDA 배포 경로**에서 함께 설치하세요. torchaudio는 Analyzer에 필요하지 않습니다. 특정 CUDA 버전을 GPU 정보 없이 일괄 지정하지 않습니다.

```powershell
nvidia-smi
.\.venv\Scripts\python.exe -c "import torch, torchvision; print('torch:',torch.__version__); print('torchvision:',torchvision.__version__); print('CUDA runtime:',torch.version.cuda); print('CUDA available:',torch.cuda.is_available())"
```

CPU 설치에서 `CUDA available: False`는 정상입니다. GPU로 실행하려면 True여야 합니다. CUDA wheel, GPU 세대, NVIDIA 드라이버가 맞아야 하며 Windows wheel과 Linux wheel도 구분해야 합니다.

### 3. SAM 로컬 소스 사용과 체크포인트

Analyzer는 다음 폴더의 SAM을 자동으로 불러옵니다. **앱만 실행할 때 별도의 `pip install segment-anything`은 필요하지 않습니다.**

`adaptation_backend/vendor/segment-anything/segment_anything`

일반 Python 코드에서도 `import segment_anything`을 쓰고 싶다면 선택적으로 설치합니다. 아래는 로컬 폴더 설치이며 GitHub 접속을 요구하지 않습니다. 1단계의 setuptools/wheel이 먼저 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps --no-build-isolation .\adaptation_backend\vendor\segment-anything
```

[Meta 공식 SAM 체크포인트 안내](https://github.com/facebookresearch/segment-anything#model-checkpoints)의 원본 파일을 사용하세요.

| 화면에서 선택할 모델 | 다운로드 | 저장 위치 예시 |
|---|---|---|
| `vit_b` | [sam_vit_b_01ec64.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth) | `models/sam_vit_b_01ec64.pth` |
| `vit_l` | [sam_vit_l_0b3195.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth) | `models/sam_vit_l_0b3195.pth` |
| `vit_h` | [sam_vit_h_4b8939.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth) | `models/sam_vit_h_4b8939.pth` |

이미 받은 체크포인트가 있으면 그대로 사용합니다. 3개 모두 받을 필요는 없습니다. CPU에서 설치 확인을 시작할 때는 ViT-B가 상대적으로 부담이 적습니다. UI의 체크포인트 칸에는 실제 파일 경로, 모델 칸에는 해당 variant를 입력합니다.

**Hugging Face만 접속 가능한 경우:** 현재 Analyzer는 원본 SAM `.pth`의 state_dict를 받습니다. [facebook/sam-vit-huge](https://huggingface.co/facebook/sam-vit-huge)는 Transformers용 배포이므로 `model.safetensors`/`pytorch_model.bin`을 이름만 `.pth`로 바꿔 넣으면 안 됩니다. 원본 `.pth`가 그대로 올라간 승인된 배포처를 사용하거나 공식 원본을 외부에서 받아 반입하세요. 학습 adaptation bundle은 학습 당시 기본 SAM의 SHA-256과 같아야 합니다.

SAM 소스 import 확인(가중치는 아직 로드하지 않음):

```powershell
.\.venv\Scripts\python.exe -c "import tem_analyzer.sam_service; import segment_anything; print(segment_anything.__file__)"
```

### 4. EasyOCR 패키지와 가중치

영문·숫자·기호를 읽는 현재 UI에는 **CRAFT + english_g2 두 파일**이 필요합니다. Tesseract를 설치할 필요는 없습니다. 먼저 torch·torchvision을 설치한 뒤:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python.exe -m pip check
```

`requirements-ocr.txt`는 `easyocr==1.7.2`를 지정하며 OpenCV 등 의존성도 pip가 설치합니다. torch가 설치되지 않은 상태에서 EasyOCR부터 설치하면 장치와 다른 torch 패키지가 선택될 수 있습니다.

| 용도 | 공식 다운로드 | 압축 해제 후 필요한 파일 |
|---|---|---|
| 글자 위치 검출 | [craft_mlt_25k.zip](https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip) | `craft_mlt_25k.pth` |
| 영어·숫자 인식 | [english_g2.zip](https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip) | `english_g2.pth` |

ZIP 자체가 아니라 **압축을 푼 `.pth` 파일**을 다음 위치에 넣습니다.

- `TEM_Analyzer_v2/models/easyocr/craft_mlt_25k.pth`
- `TEM_Analyzer_v2/models/easyocr/english_g2.pth`

UI의 `로컬 EasyOCR 폴더`는 `models/easyocr` 또는 그 폴더의 절대 경로입니다. ZIP 이름의 하위 폴더가 한 번 더 생기지 않도록 확인하세요. `korean_g2.pth`는 현재 영어 OCR UI에는 필요하지 않습니다.

인터넷이 되는 Windows PC에서 다운로드·압축 해제를 명령으로 하려면:

```powershell
New-Item -ItemType Directory -Force .\downloads, .\models\easyocr | Out-Null
Invoke-WebRequest -Uri "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip" -OutFile .\downloads\craft_mlt_25k.zip
Invoke-WebRequest -Uri "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip" -OutFile .\downloads\english_g2.zip
Expand-Archive -LiteralPath .\downloads\craft_mlt_25k.zip -DestinationPath .\models\easyocr -Force
Expand-Archive -LiteralPath .\downloads\english_g2.zip -DestinationPath .\models\easyocr -Force
```

이 다운로드 명령은 인터넷 연결이 있는 준비 PC에서 실행합니다. 회사망에서 GitHub 다운로드가 막혀 있으면 외부에서 받은 파일을 회사의 반입 절차에 따라 옮깁니다.

**자동 다운로드를 끈 상태에서 OCR 가중치 로드 확인:**

```powershell
.\.venv\Scripts\python.exe -c "import easyocr; easyocr.Reader(['en'],gpu=False,model_storage_directory='models/easyocr',user_network_directory='models/easyocr',download_enabled=False,verbose=False); print('OCR local weights OK')"
```

현재 앱의 OCR은 CPU로 실행됩니다. GPU는 SAM에서 선택할 수 있습니다. 앱도 `download_enabled=False`로 로드하므로 가중치가 없으면 자동 다운로드를 시도하지 않고 오류를 표시합니다.

### 5. 회사망용 wheel 준비와 오프라인 설치

**인터넷 연결 준비 PC에서** 위 1~4단계 패키지 설치와 확인을 먼저 마칩니다. 다음 절차는 같은 OS/아키텍처/Python 3.11용 패키지를 모으는 CPU 예시입니다. 별도 실험 패키지가 없는 새 `.venv`에서 진행하세요.

```powershell
# 빌드 도구도 함께 보존합니다.
.\.venv\Scripts\python.exe -m pip install setuptools wheel
# pip freeze 출력은 UTF-8 파일로 저장합니다. 선택 설치한 로컬 SAM은 앱에 소스가 있으므로 제외합니다.
.\.venv\Scripts\python.exe -c "import subprocess,pathlib; s=subprocess.check_output([__import__('sys').executable,'-m','pip','freeze','--all'],text=True); lines=[x for x in s.splitlines() if not x.lower().replace('_','-').startswith('segment-anything')]; pathlib.Path('requirements-lock.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')"
.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --dest wheelhouse -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

GPU 패키지를 준비했다면 마지막 명령의 `/cpu` 주소를 **2단계 설치 때 사용한 공식 CUDA wheel index 주소**로 바꾸세요. 이미 설치한 정확한 버전을 `requirements-lock.txt`에 기록하므로 torch/torchvision 조합을 유지합니다. wheel을 구할 수 없다는 오류가 있으면 누락된 채로 반입하지 말고 Python/OS 일치 여부와 해당 패키지의 wheel 제공 여부를 먼저 확인합니다. 위 절차는 회사 정책상 패키지 반입이 허용된 경우 사용합니다.

회사 PC로 복사할 것은 **프로그램 폴더, wheelhouse, requirements-lock.txt, SAM `.pth`, OCR `.pth` 2개**입니다. `.venv` 자체는 복사하지 않습니다. Python 3.11 64-bit는 회사 PC에도 설치되어 있어야 합니다.

**인터넷이 없는 회사 PC에서:**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r .\requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import torch,torchvision,easyocr; print(torch.__version__,torchvision.__version__); print('CUDA:',torch.cuda.is_available())"
.\.venv\Scripts\python.exe -c "import tem_analyzer.sam_service; import segment_anything; print(segment_anything.__file__)"
.\.venv\Scripts\python.exe run.py
```

`--no-index`는 외부 패키지 인덱스를 사용하지 않도록 합니다. 오프라인 PC에서는 온라인용 `install_windows.bat` 대신 위 명령을 사용하세요. 패키지 설치 후에는 `start_windows.bat`로 실행할 수 있습니다.

### 6. 화면 입력과 실제 모델 점검

`http://127.0.0.1:8765`를 열고 다음을 지정합니다.

| 화면 항목 | 예시 |
|---|---|
| SAM 체크포인트 | `C:/TEM_Analyzer_v2/models/sam_vit_b_01ec64.pth` |
| 모델 | `vit_b` (파일과 일치) |
| 장치 | GPU 없는 PC: `cpu`, GPU 서버: 확인 후 `cuda` 또는 `auto` |
| 학습 decoder / Lab adaptation | 기본 SAM을 확인할 때는 둘 다 빈칸 |
| 로컬 EasyOCR 폴더 | `C:/TEM_Analyzer_v2/models/easyocr` |

```powershell
# 가중치 없이 기본 앱 점검
.\.venv\Scripts\python.exe smoke_test.py
# 실제로 준비한 SAM 가중치로 합성 이미지 추론 점검
.\.venv\Scripts\python.exe smoke_test.py --checkpoint models/sam_vit_b_01ec64.pth --variant vit_b --device cpu --no-grid
```

이 문서 작성 환경에서는 실제 torch/SAM/OCR 가중치 전체 설치를 실행하지 않았습니다. 위 명령은 공식 설치 방식과 앱 경로를 대조해 작성했으며, 최종 설치·실제 가중치 로드는 대상 PC에서 확인해야 합니다.

### 설치 오류별 확인

| 오류 | 확인할 내용 |
|---|---|
| `No module named torch/torchvision/easyocr` | 설치할 때와 실행할 때 모두 `.venv/Scripts/python.exe`를 사용했는지 확인 |
| `operator torchvision::nms does not exist` / torchvision 확장 로드 실패 | torch·torchvision의 버전과 CPU/CUDA 배포가 섞였는지 확인. 두 패키지를 같은 공식 index의 호환 조합으로 함께 재설치 |
| `No module named segment_anything` | ZIP의 `adaptation_backend/vendor/segment-anything/segment_anything` 폴더 존재 확인. 앱 import 확인 명령을 사용하거나 3단계 로컬 설치 수행 |
| `Missing/Unexpected key(s) in state_dict` | ViT-B/L/H와 체크포인트 일치 확인. Transformers 변환 가중치 또는 SAM 2 파일을 넣지 않았는지 확인 |
| `OCR 가중치가 없습니다` / MD5 mismatch | ZIP 압축 해제, 폴더 중첩, 정확한 파일명 확인. 손상된 파일은 공식 ZIP으로 다시 받기 |
| `not a supported wheel on this platform` | Windows/Linux, x64/ARM, Python 3.11/3.12 등 wheel 대상 확인 |
| `CUDA available: False` | CPU 설치는 정상. GPU 사용 시 CUDA wheel 및 드라이버 확인 |

설치 근거: [PyTorch](https://pytorch.org/get-started/locally/), [공식 SAM](https://github.com/facebookresearch/segment-anything), [EasyOCR v1.7.2 가중치 설정](https://github.com/JaidedAI/EasyOCR/blob/v1.7.2/easyocr/config.py), [pip 로컬 패키지 설치](https://pip.pypa.io/en/stable/user_guide/#installing-from-local-packages).

## v2의 주요 변경

- 파일 이동이 모두 성공한 뒤 이미지 메타데이터를 삭제합니다. 실패하면 원상 복구하며, 여러 이미지 중 실패한 항목은 별도로 반환합니다. 삭제 파일은 프로젝트 `trash/`에 남습니다.
- 이미지 목록에서 다중 선택 모드의 클릭·Ctrl/Cmd·Shift·드래그로 선택 삭제할 수 있습니다. 처리 중 이미지 이동·삭제·편집 입력을 막고 서버도 요청을 직렬화합니다.
- 후보 확정 시 **추가 / 부모 교체 / 부모 분할**을 구분합니다. 부모 교체는 기존 마스크를 비활성화하고 파일·이력을 보존합니다. 분할은 부모의 나머지도 새 후보로 남깁니다.
- 메타데이터 편집의 Undo/Redo를 최근 20단계까지 저장합니다. 앱 재시작 후에도 유지됩니다. 이미지 업로드/삭제는 Undo 대상이 아니며 이전 편집 이력을 초기화합니다.
- 기존 마스크 수정 시 같은 모델·같은 분석용 이미지의 SAM low-resolution logits를 재사용합니다. 조건이 달라졌거나 logits가 없으면 원본 종횡비와 SAM padding에 맞춘 이진 마스크 seed를 사용합니다. ROI 편집은 crop에 맞는 seed를 사용합니다.
- SAM과 경계 각각에 독립된 Gaussian/Bilateral, sigma, 대비 설정을 저장합니다. 원본은 바꾸지 않습니다. 제외 영역은 가까운 유효 픽셀로 채워 인공적인 검정 경계 영향을 줄이고 최종 마스크에서 제외합니다.
- `TEM_SAM_Lab_v1_2` adaptation bundle을 읽고 기본 SAM SHA-256과 모델 종류를 확인합니다. decoder/refiner 모두 학습과 같은 single-mask 경로를 사용합니다.
- 원본 좌표의 법선 gradient + 연속성 DP 경계 보정, 피크 비교, 프로파일, 부분 탐색 폭/극성, 수동 고정점, 연결 구조 보호를 제공합니다.
- 배경·미지정·불확실·제외·수동 보호를 명시적으로 관리하고 검수된 결과만 학습 출력에 포함합니다.

## 권장 작업 순서

1. **이미지·스케일**: 이미지를 업로드하고 스케일바/스케일 숫자/샘플명/배율 ROI를 지정합니다. 좌표는 이미지 크기로 정규화하여 템플릿에 저장됩니다. 템플릿 저장만으로 기존 이미지의 적용값은 바뀌지 않으며, 현재/전체 이미지에 적용해야 합니다.
2. 바 검출과 실제 길이 입력으로 스케일을 계산하거나, 전체 이미지별 OCR + 바 매칭을 사용합니다. OCR은 각 이미지에서 별도로 실행합니다. OCR 실패 시 실제 길이 칸이 채워져 있으면 공통 길이를 fallback으로 사용합니다. 바 길이와 숫자가 이미지마다 다른 경우 OCR 제안값을 반드시 확인하세요. 확정 전에는 제안 상태입니다.
3. **SAM·레이어**: SAM 체크포인트와 모델 종류를 지정합니다. Grid/ML 점 준비는 추론하지 않으며, 실행 버튼을 눌러야 추론합니다. 생성 후보를 레이어와 instance에 연결합니다.
4. **기존 마스크 + 현재 점/box로 수정 제안**: 부모 마스크를 seed로 수정합니다. 결과 확인 후 `부모 교체`로 확정하거나 미확정 후보를 취소합니다. 원래 부모는 이력에 남습니다. 브러시도 새 후보를 만든 뒤 확정합니다. 확정한 브러시 변경 픽셀은 수동 보호 영역이 됩니다.
5. **공유 경계 보정·GT**: 레이어에 연결한 후보 A를 선택하고 인접한 다른 레이어의 후보 B를 고릅니다. B를 선택하지 않으면 명시적으로 칠한 배경과의 경계를 사용합니다. 겹침은 먼저 해결해야 합니다.
6. 경계 미리보기 후 흰색 원래 경계, 주황 피크, 청록 DP 제안을 비교합니다. **초록색 마스크가 보호·공유 경계 제약까지 반영한 실제 적용 결과**입니다. 경계를 클릭하면 법선 gradient 프로파일을 확인할 수 있습니다. 이동량 고정이나 두 클릭 지점 사이의 짧은 구간 설정을 추가한 뒤 미리보기를 다시 실행합니다.
7. 적용하면 A와 B 마스크를 함께 갱신하여 틈/겹침을 만들지 않고 instance 이름을 유지합니다. 변경 전후 연결 성분/구멍 개수가 달라지면 차단합니다. 미리보기 이후 다른 프로젝트 편집이 있으면 재계산해야 적용할 수 있습니다.
8. 브러시 추가로 영역을 그린 후 배경/미지정/불확실/제외/보호 상태를 적용합니다. 잠긴 레이어의 픽셀은 자동/수동 영역 변경에서 보호합니다. 수동 보호 해제는 레이어 잠금을 해제하지 않습니다.
9. 검수 결과 ZIP과 후보 비교 CSV를 내려받습니다.

## 학습 모델 연결

모델 설정의 `Lab adaptation bundle`에 `TEM_SAM_Lab_v1_2`가 저장한 `adaptation.pt`를 지정합니다.

- bundle 계약: `schema=1`, `method=decoder|refiner`, `base_sha256`, `config`, `state`.
- 현재 지원하는 학습 전처리는 `uint8`입니다. `percentile_1_99` bundle은 명시적으로 거부합니다.
- decoder는 mask decoder state를 읽습니다. refiner는 원본 SAM logits를 학습 때와 같은 종횡비/`refine_side`로 입력하는 ResidualRefiner입니다.
- 기존 v1의 256×256 이진 마스크 TorchScript refiner는 이 계약과 달라 지원하지 않습니다.
- 기본 모델과 학습 모델 모두 single-mask inference를 사용합니다. 자동 후보의 NMS는 **mask IoU**입니다. 학습 후 IoU head가 보정되지 않았으므로 학습 모델은 predicted IoU 임계값을 적용하지 않고 stability로 정렬합니다. 원본 모델은 predicted IoU 임계값도 적용합니다.
- 모델 SHA, 이미지 SHA, 입력 prompt, 전처리 snapshot, 실행 시간은 프로젝트 run 기록에 남습니다. ROI crop 결과는 원본 전체 logits로 재사용하지 않습니다.
- SAM/경계 전처리를 바꾸면 학습 때와 입력 분포가 달라질 수 있습니다. 모델 비교 시 같은 전처리와 프롬프트를 사용하세요.

## 출력 계약

| 파일 | 내용 |
|---|---|
| `image.png` | 8-bit RGB 원본 |
| `labels.png` | uint16: 배경 0, 레이어 1–65532, 제외 65533, 불확실 65534, 미지정 65535 |
| `semantic.png` | 유효 레이어 ID. 유효하지 않은 곳은 0이므로 **valid와 함께 사용** |
| `valid.png` | 검수된 레이어/명시적 배경 255, 미검수·미지정·불확실·제외·충돌 0 |
| `lab_mask.png` | 모든 무효 영역을 65535로 합친 단일 GT. TEM SAM Lab의 `ignore_label=65535`로 사용 |
| `edge.png` | 유효한 서로 다른 클래스 간 경계, 1회 팽창한 이진 edge |
| `center.png` | 클래스별 연결 성분의 distance-transform 최대점 하나. instance별 Gaussian heatmap은 아님 |
| `metadata.json` | 스케일·클래스·후보/instance·전처리·실행 기록·출력 계약 |

Lab에 연결할 때 class_names의 ID를 레이어 ID에 맞추고 background=0, ignore=65535로 설정합니다. 여러 이미지의 학습/검증 분리는 원본 이미지 단위로 별도로 구성하세요.

후보 비교는 현재 이미지의 유효한 레이블 영역에서 IoU, Dice, boundary F1, 대칭 평균 경계 거리(px)를 계산합니다. 경계 허용오차는 사용자 설정입니다. 사용자 검수 후보를 기준으로 하는 비교이며 독립 테스트셋 성능 검증은 아닙니다. 계측 수치와 실제 두께 산출은 아직 제공하지 않습니다.

## 기존 프로젝트 열기

v1 프로젝트 폴더 전체를 복사한 뒤 사본을 지정하는 것을 권장합니다.

```bash
python run.py --project /path/to/copied_project --port 8765
```

schema v1을 열면 `project.v1.backup.<timestamp>.json`을 저장하고 v2로 변환합니다. 마스크·원본 파일은 그대로 둡니다. v2 프로젝트를 v1에서 다시 열지 마세요. 이미지 삭제는 Undo 대신 `trash/`의 저널/파일로 보존되며, 삭제 실패 또는 중단된 이동은 다음 시작 시 복구합니다. 정상 완료한 삭제를 되살리는 UI는 아직 없습니다. 로그와 undo 기록이 커질 수 있으므로 프로젝트 전체를 정기적으로 백업하세요.

## 검증과 한계

```bash
python -m unittest discover -s tests -v
python smoke_test.py
# 개발용 Node + @napi-rs/canvas 설치 후
node tests/ui_regression.cjs
# 실제 로컬 가중치 검증
python smoke_test.py --checkpoint /models/sam_vit_b.pth --variant vit_b --device cpu
python smoke_test.py --checkpoint /models/sam_vit_b.pth --variant vit_b --adaptation /models/adaptation.pt
```

이번 환경에서는 Python 워크플로/합성 경계/출력 테스트와 Node canvas 회귀 테스트를 실행했습니다. **torch·모델 가중치·EasyOCR 가중치가 없어 실제 SAM/학습 bundle 추론, 실제 TEM 정확도, OCR 정확도, GPU 성능은 검증하지 않았습니다.** 회사 이미지에서 소규모 검수를 먼저 진행하세요.

법선 DP는 폐곡선 seam 비용을 포함하지만 시작 상태 상위 5개를 탐색하는 근사 알고리즘입니다. 강한 결정 격자/오염/접합점에서는 잘못된 피크가 선택될 수 있습니다. 원본 이미지 좌표를 유지하되 경계 샘플은 보통 2px 간격(루프당 최대 2,500개)입니다. 넓은 탐색 폭, 고해상도 Bilateral, 많은 single-mask 점은 느릴 수 있습니다. 16-bit 입력은 자동 축소하지 않고 거부합니다.

우선순위 3의 RF 학습·다른 이미지 자동 전파, 대량 모델 벤치마크, 두께 계측은 이번 버전에 포함하지 않았습니다.

## 코드 출처

사용자 저장소의 `TEM_Analyzer_v1`, `TEM_SAM_Boundary_Demo_v2`, `TEM_SAM_Lab_v1_2` 구조를 통합했습니다. 외부 소스/라이선스는 `THIRD_PARTY_NOTICES.md` 및 `adaptation_backend/THIRD_PARTY_NOTICES.md`를 참조하세요.
