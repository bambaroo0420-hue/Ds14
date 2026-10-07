# TEM Analyzer v3.0.0 — SAM 2.1 Hiera Large

v2의 이미지·스케일, SAM 프롬프트/ROI/recipe/일괄 처리, 레이어 편집,
경계 보정, 회전·계측 UI와 API를 유지하고 분할 엔진을 교체한 별도 버전입니다.
원래 v2와 프로젝트를 덮어쓰지 말고 새 폴더에 압축을 해제하세요.

## 설치 (처음 한 번)

Python 3.11 이상 64-bit를 사용하세요. 회사 GPU 서버에서는 기존 GPU 커널을
사용해도 됩니다. torch>=2.5.1와 torchvision>=0.20.1의 **서로 호환되는 GPU 빌드**를
먼저 설치/확인하세요. CPU torch를 GPU 환경에 무작정 덮어쓰지 마세요.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# CPU 시험 환경에만 사용. GPU에서는 PyTorch 공식 설치 선택기에 맞는 명령 사용.
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# OCR을 사용하는 경우
.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

Linux/서버에서는 `.venv/bin/python` 또는 선택한 커널의 `sys.executable`을 사용합니다.
`setup.ipynb`도 제공하며 기존처럼 tools 모듈 import 없이 설치/실행할 수 있습니다.
SAM2 공식 Python 소스는 `vendor/sam2`에 포함되어 별도 git clone이 필요 없습니다.
CUDA 커스텀 작은 구멍/점 제거는 사용하지 않습니다. 해당 영역 수정은 기존 편집 기능을 사용합니다.
네트워크 차단 서버에서는 호환 wheel을 `wheelhouse`에 준비하고
`pip install --no-index --find-links wheelhouse -r requirements.txt`를 사용하세요.
가중치만 복사하는 것은 패키지 설치를 대신하지 않습니다. 같은 환경에서는 매번 설치하지 않습니다.

## 모델 파일 위치

```text
TEM_Analyzer_v3/
  run.py
  setup.ipynb
  models/
    sam2.1_hiera_large.pt
    easyocr/
      craft_mlt_25k.pth
      english_g2.pth
```

[SAM 2.1 Large 공식 가중치 다운로드](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt)
([공식 설치 문서](https://github.com/facebookresearch/sam2)).
OCR 파일은 기존 v2의 easyocr 폴더를 복사할 수 있습니다.
모델/회사 이미지/프로젝트는 배포 ZIP에 포함하지 않습니다. 모델 자동 다운로드는 하지 않습니다.

## 실행 순서

```powershell
.venv\Scripts\python.exe -X utf8 run.py --port 8766 --project projects/v3_test
```

1. 브라우저에서 `http://127.0.0.1:8766` 열기 → 이미지 업로드/스케일 확인.
2. 2 SAM·레이어 → 모델 설정 → Large 파일 경로 → 장치 → 모델 로드.
3. Grid/ML/수동 +/−점·box 구성 → 준비한 프롬프트로 실행. 독립/회전 ROI, 수동 객체 그룹도 기존 방식대로 사용.
4. 필요한 마스크만 레이어 배정 → 브러시·잠금·경계 보정 → 미리보기 후 적용.
5. 회전 기준/측정 구간을 확인하고 회전·계측. 전체 GT를 완성해야만 계측하는 것은 아닙니다.
6. recipe를 저장한 뒤 별도 이미지에서 일괄 SAM을 시험하고 결과를 검수하세요.

## 호환성과 반드시 확인할 사항

- 기존 프로젝트는 **폴더 전체를 복사한 사본**에서 먼저 여세요. 기존 schema를 유지하며 마스크/레이어/프롬프트를 사용할 수 있습니다.
- SAM1 decoder, ABL adaptation/refiner는 호환되지 않으므로 UI 비활성 및 API 거부합니다.
  기존 SAM1 학습 기능까지 SAM2에서 그대로 실행된다는 의미는 아닙니다.
- 이전 SAM1 low-resolution logits는 재사용하지 않습니다. 이미지/모델/엔진이 일치할 때만 logits를 사용합니다.
  이전 바이너리 mask는 SAM2의 정사각 resize 규칙에 맞게 seed로 변환합니다.
- Grid/ML 점 생성은 그대로입니다. ML 표시 기능에는 기존 classical CV 방식도 포함됩니다.
- 새 모델은 결과/점수 분포가 다릅니다. v2 threshold/recipe가 같은 정확도를 보장하지 않습니다.
- 기존 법선 보정의 제한, 부분 GT, top3 수동 배정 정책은 그대로입니다. v3가 자동 full semantic GT 정확도를 보장하지 않습니다.
- 이 버전은 정지 이미지 분석입니다. SAM2 video memory를 이용한 영상 추적/이미지 간 자동 전파를 추가한 버전은 아닙니다.
- `docs/`의 v2 문서는 계승된 기능 설명/과거 기록입니다. 모델 설치는 이 문서가 우선합니다.

## 수정 지점

`tem_analyzer/sam_service.py`: SAM2 Large 어댑터/좌표 및 seed 변환.
`tem_analyzer/api.py`: 모델 로드 API 기본값.
`web/index.html`: 버전/모델 설정 UI. 나머지 JS/CSS는 기존 기능 유지.
`tools/server_setup.py`, `setup.ipynb`: 설치/실행 진단.
`tests/test_sam2_contract.py`, `tools/validate_sam2_large.py`: 전용 계약/실제 가중치 검사.

회귀 검사: `python tools/check_gap_bridge.py --all --output v3-regression`.
실제 가중치 검사: `python tools/validate_sam2_large.py --checkpoint models/sam2.1_hiera_large.pt --image YOUR_IMAGE.png`.
실측 결과와 미검증 범위는 `docs/V3_VALIDATION_KO.md`를 확인하세요.

