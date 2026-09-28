# TEM GT Studio v1 — 테스트용 로컬 GT 제작 도구

2026-09-28. 이 도구는 사용자 확인을 전제로 하는 GT 편집기입니다. 자동 계측/학습 프로그램은 아닙니다.

## 빠른 실행

Python 3.10~3.12 권장. ZIP을 풀고 Windows에서는 `install_windows.bat`를 한 번 실행한 뒤 `start_windows.bat`를 실행합니다. 브라우저에 `http://127.0.0.1:8765`가 열립니다. 오류가 나도 창이 닫히지 않도록 pause를 넣었습니다.

Linux/macOS 또는 기존 환경:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

포트가 사용 중이면 `python app.py --port 8766`. 자동 브라우저 실행을 끄려면 `--no-browser`.
로컬 PC 전용으로 127.0.0.1에 바인딩합니다. 데이터는 외부 서비스로 전송하지 않습니다. 의존성 설치는 별도입니다. 여러 사용자가 공유하는 서버 운영용 인증/HTTPS는 포함하지 않았습니다.

## 첫 테스트 순서

1. 상단 **합성 예제**를 누릅니다. 실제 회사 TEM은 포함하지 않았습니다.
2. 층 1을 선택하고 **Polygon 영역** 모드로 원하는 층을 둘러싸는 4개 이상 점을 찍어 **Polygon 적용**합니다. 층 이름은 `층 목록 편집`에서 `1=층명` 형식으로 바꿉니다.
3. **ROI 사각형** 모드로 일부 영역을 드래그하고 **ROI / 전체 재분할**을 누릅니다. Superpixel 모드에서 클릭/드래그하면 해당 조각이 선택한 층이 됩니다.
4. 편집 동작을 `미주석으로 지우기`로 하면 라벨을 없애고 valid=0으로 만듭니다. 확인된 배경은 class 0을 선택해 칠해야 합니다.
5. **선택 층 전체 경계 미리보기**를 실행합니다. 회색 초기 경계, 분홍 최대 peak, 청록 DP 경계를 토글 비교합니다. 연속성 0은 독립적인 최대 점수 선택입니다. Contrast=0일 때 gradient 점수만 사용합니다.
6. **반대/비워질 영역 class**를 올바르게 선택한 뒤 **보정 결과 적용**을 누릅니다. 한 객체의 주변에 여러 서로 다른 층이 접하면 전체 mask 적용보다 ROI+계면선 방식으로 구간별 수정하세요. 전체 mask 모드에서 줄어든 부분은 선택한 반대 class로 채워집니다.
7. 합성 예제에는 50 nm, 120k, Sample A-01이 있습니다. OCR 실행 → 바 후보 확인 → 후보 확정 → 검출 문자·바 학습 제외 순서로 진행합니다.
8. **작업 저장 ZIP**으로 편집 상태를 저장합니다. 서버를 끄면 메모리 작업이 사라지므로 반드시 저장하세요.
9. 원본과 결과를 확인한 후 **원본과 GT를 확인했습니다**를 체크하고 **Semantic + Edge + Valid ZIP 저장**을 누릅니다.

### 내부 계면이 없는 경우

ROI 사각형을 지정하고 `계면 polyline` 모드에서 계면을 대략 가로질러 그립니다. **그린 계면선 미리보기** → **보정 결과 적용**으로 ROI 안을 두 class로 나눕니다. 점을 그린 방향 기준 왼쪽(normal +)에 선택 class, 오른쪽에 반대 class가 들어갑니다. 예: 왼쪽에서 오른쪽으로 그린 수평선은 아래쪽이 선택 class입니다(영상 y축은 아래 방향).

선은 ROI 한쪽 끝부터 다른 끝까지 가로지르게 그리세요. ROI 안의 해당 두 class 또는 미주석 영역만 수정하고 다른 class는 유지합니다. 틀린 선은 `점·선·ROI 지우기`로 다시 그립니다. 직접 경계점 드래그/잠금은 v1에 포함되지 않았으며, 취소 후 polyline 재입력 또는 brush/polygon으로 수정합니다.

## SAM / micro-SAM 설정 (선택 설치)

기본 설치만으로 수동·superpixel·DP·GT 저장을 사용할 수 있습니다. SAM과 OCR은 각 실행 환경이 추가로 필요합니다. 가중치는 용량/라이선스 때문에 ZIP에 넣지 않았으며 앱이 자동 다운로드하지 않습니다.

**SAM**: 사용 환경(CPU/CUDA)에 맞는 PyTorch/torchvision을 먼저 설치하고 Meta SAM 패키지를 설치합니다.

```bash
python -m pip install torch torchvision
python -m pip install git+https://github.com/facebookresearch/segment-anything.git
```

CUDA를 사용하려면 GPU 드라이버에 맞는 PyTorch 배포판을 선택하세요. 공식 설치 안내: https://pytorch.org/get-started/locally/
보유한 vit_b/vit_l/vit_h 체크포인트의 절대 경로를 UI에 넣고 모델 종류와 device를 선택합니다. 예: `C:\models\sam_vit_b_01ec64.pth`.

**micro-SAM**: 공식 설치 안내에 따라 micro-SAM 환경을 준비하고, 그 환경에서 이 앱의 requirements도 설치하여 실행하세요. https://github.com/computational-cell-analytics/micro-sam
UI backend를 micro-SAM으로 바꾸고 체크포인트와 일치하는 model type을 선택합니다. 로컬 파일이 없으면 실행하지 않습니다. micro-SAM의 `get_sam_model`과 predictor API를 사용합니다. napari 자체 UI를 띄우는 방식은 아닙니다.

- 일반 모드: 양성/음성점들이 현재 한 객체를 설명합니다. ROI는 box prompt입니다.
- 배치 모드: 양성점 하나씩 독립 추론 후 **같은 class로 합칩니다**. 음성점은 이 모드에서 사용하지 않습니다. 각기 다른 층은 class를 바꿔 나눠 실행하세요.
- SAM 전 smoothing σ=0은 OFF. ROI crop 체크 시 실제 이미지 crop 후 원본 좌표로 복원합니다.
- Import mask: micro-SAM/다른 프로그램에서 만든 원본 크기 단일 채널 mask를 가져올 수도 있습니다. 가져온 0은 확인된 배경으로 처리하므로 미주석 구역은 별도로 지우거나 제외하세요.
- SAM/micro-SAM 실행은 이 배포 환경에서 가중치 추론을 검증하지 못했습니다. 모델/체크포인트 호환성을 사용자 환경에서 확인해야 합니다. 실패 시 에러를 표시하며 CV 결과를 SAM 결과처럼 대체하지 않습니다.

## OCR 설치 및 제외

Python 패키지 pytesseract 외에 **Tesseract 실행 프로그램**이 필요합니다. PATH에 있으면 자동 사용하고, 없으면 UI에 실행 파일의 절대 경로를 넣습니다. 공식 안내: https://tesseract-ocr.github.io/tessdoc/Installation.html

v1 OCR은 기본 영어 데이터로 숫자/영문 샘플 정보/단위를 읽습니다. 한글 샘플명 완전 인식은 보장하지 않으며 수동 제외로 보완하세요. 가로 방향 스케일바와 `nm` / `um` / `µm`를 처리합니다. 바 후보 선택은 사람이 확인합니다. 잘린 바/세로·회전 바/겹친 숫자는 수동 두 끝점+실제 nm 길이 입력을 사용하세요.

배율 숫자만으로 스케일을 계산하지 않습니다. 문자 박스는 읽은 단어 중심이므로 누락된 문자와 다른 주석은 polygon/brush로 `학습 제외`하세요. 문자/바 제외는 **loss와 metric용 mask**이며 입력 이미지를 자동으로 inpaint하거나 crop하지 않습니다. 학습에서 문자 입력 자체를 없애려면 구조 밖 주석 띠를 crop해서 patch를 추출하세요.

## 출력 ZIP

- `images/`: RGB 원본 해상도 PNG (원본 파일은 사용자가 별도 보존).
- `semantic_gt/`: uint16 class ID PNG. 0=확인된 배경, 1..N=층.
- `edge_gt/`: uint8, 0/1. semantic raster 경계에서 radius 1 cross(유클리드 거리 1 px) 팽창. 수평/수직 기준 약 3 px 폭.
- `valid_semantic/`, `valid_edge/`: uint8, 0/1. **0은 loss·평가에서 제외**. 미주석/문자/스케일바를 배경으로 학습시키지 마세요.
- `boundary_center/`: edge GT 생성에 실제 사용한 1 px 래스터 중심선. class 전이의 위/왼쪽 픽셀을 택하는 규칙입니다.
- `centerlines/`: DP 원본 좌표 경로와 class별 래스터 외곽선. 래스터 외곽선은 제외 영역/이미지 외곽에도 생길 수 있으므로 valid_edge와 함께 사용합니다. 공유 계면이 class별 외곽선에 중복 표현될 수 있지만 binary edge GT는 한 번만 생성됩니다.
- `metadata/`: class 목록, nm/px·확정 여부, OCR 결과, 라벨 규칙.

선형 보간으로 class label을 resize하지 마세요. Edge 및 valid PNG는 0/1 값이므로 시각적으로 거의 검게 보이는 것이 정상입니다. `training_example.py`에 PyTorch masked loss 사용 예시가 있습니다. 스케일 미확정이어도 GT export는 가능하지만 nm 계측에 사용하면 안 됩니다.

## v1 범위 및 알려진 한계

- 기준 이미지에서 다른 셀/다른 이미지로 프롬프트 자동 전파, 모델 학습, 두께/RMS 계측은 미포함.
- 객체별 영구 instance ID 대신 semantic class map 중심으로 편집합니다. 동일 class 영역의 분리 편집은 ROI/수동 도구로 수행합니다.
- DP는 법선 전체 후보에서 gradient(+선택적 contrast)와 이웃 offset 차이를 최적화합니다. 초기 경계에서 멀어지는 페널티는 없습니다. closed 경로는 시작/끝 연속성도 최적화합니다.
- 곡률 2차 페널티, 자기교차 방지, subpixel peak fitting은 미포함. 급격한 코너/매우 얇은 층은 검토 필요.
- UI는 이미지 여러 장 추가/전환/삭제가 가능하지만 일괄 자동 GT 생성은 하지 않습니다.
- 16-bit 원본 입력은 현재 RGB 8-bit 표시/분석으로 변환됩니다. 정량 원본 강도 보존이 필요한 경우 외부에서 명시적으로 8-bit 변환 후 사용하세요. 마스크는 uint16 보존합니다.
- 원본 크기 3200만 픽셀 상한. 큰 영상에서 superpixel과 closed DP는 느릴 수 있으므로 ROI 사용을 권장합니다.
- Undo/redo 최대 15단계, RAM 저장. 작업 ZIP에는 원본·semantic·valid·exclude·중심선·설정이 들어가며 undo 기록과 미확정 클릭/ROI는 들어가지 않습니다.
- 합성 데이터 검증은 실제 TEM 계면 정확도를 보장하지 않습니다. 처음에는 1~2장으로 GT와 원본을 비교해 주세요.

## 사내 오프라인 반입

사내 OS/Python과 같은 환경에서 base requirements의 wheel을 준비합니다.

```bash
python -m pip download -r requirements.txt -d wheels
# 사내에서:
python -m pip install --no-index --find-links wheels -r requirements.txt
```

SAM/micro-SAM/PyTorch, 체크포인트, Tesseract 실행 파일·언어 데이터는 별도로 준비해야 합니다. 이 ZIP은 설치파일 전체를 포함한 오프라인 번들이 아닙니다.

## 검증

```bash
python -m pip install pytest
python -m pytest -q
```

테스트는 수평/대각선/닫힌 경계 이동, 3 px edge, ignore 처리, 프로젝트 roundtrip, superpixel 편집/undo, polyline 분할, export API를 검사합니다. 실제 TEM 데이터는 사용하지 않았습니다.
