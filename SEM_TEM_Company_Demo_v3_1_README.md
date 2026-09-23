# SEM/TEM Company Demo v3.1

Windows에서 실행하는 로컬 SAM 분할·클릭 보정 및 Random Forest 부분 주석 학습 도구입니다.
**이 ZIP은 최신 전체 소스입니다. 이전 패치를 순서대로 설치할 필요가 없습니다.**
가중치, Python, 가상환경, 오프라인 설치용 wheelhouse는 포함하지 않습니다.

## 실행

기존 설치가 있다면 앱을 닫고 기존 폴더를 백업한 뒤 이 소스를 덮어쓰세요.
기존 `.venv`, `checkpoints`, `wheelhouse`, 작업 데이터와 결과는 유지합니다.

- `start.bat`: SAM 분할 화면. 상단 버튼으로 RF 화면도 실행합니다.
- `start_rf.bat`: RF 학습·예측 화면만 실행합니다. SAM 가중치는 필요 없습니다.
- 모든 화면은 8-bit RGB/회색조 PNG, JPG, TIFF를 사용합니다. 16-bit 영상은 정한 대비 기준으로 먼저 변환하세요. 다중 페이지 TIFF는 첫 페이지를 읽습니다.

새 설치(인터넷 사용 가능 Windows, Python 3.13 x64 + Tkinter):

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
start_rf.bat
```

SAM을 사용할 때 추가 설치:

```powershell
.venv\Scripts\python -m pip install -r requirements-sam.txt
start.bat
```

SAM 공식 체크포인트를 미리 준비하고 화면에서 파일과 모델 종류를 일치시킵니다.
CPU 시험에 사용한 파일은 `sam_vit_b_01ec64.pth`이며 **vit_b**를 선택합니다.
공식 체크포인트 안내: https://github.com/facebookresearch/segment-anything#model-checkpoints
CPU/CUDA에 맞는 torch·torchvision 설치가 필요합니다. 실행 중 파일 자동 다운로드나 외부 전송은 없습니다.
오프라인 설치는 동일 Windows/Python용 wheelhouse를 별도로 준비하고 `setup_offline.bat`를 실행합니다.
소스 ZIP만으로 인터넷 없는 새 PC에 설치할 수는 없습니다.

## SAM 작업 순서

1. 이미지 열기 → 체크포인트와 모델 종류 선택 → 모델 로드.
2. MatSAM Canny, MatSAM Otsu, SAM grid 중 선택.
3. 처리 영상 / 자동 점 미리보기 → 설정 확인 → 같은 조건으로 SAM 실행.
4. 자동 후보 선택 → 선택층에 적용. 다른 층은 층 추가로 보관.
5. 양성·음성 점/박스 입력 → 선택 마스크 클릭 보정 → 전후 비교 → 적용/취소.
6. 필요한 부분을 브러시로 수정하고 검수한 뒤 결과 저장.
7. 작업을 이어가려면 저장 폴더의 session.json을 불러오고 모델을 별도 로드.

이전 SAM logits가 유효하면 다음 보정에 재사용합니다. 브러시 수정/구버전 세션은 이진 마스크에서 근사 입력을 만듭니다.
이 기능은 기존 경계를 고정하거나 클릭 부근만 수정하지 않습니다. 점·박스·마스크를 최대 8단계 되돌릴 수 있습니다.
Gaussian은 자동 점 생성 경로에만 적용하고 SAM에는 원본 RGB를 입력합니다.
Canny/Otsu 윤곽 중심은 재료층 내부를 보장하지 않습니다. 겹친 SAM 마스크는 노랑으로 표시하며 자동 제거하지 않습니다.
모든 자동 후보는 세션에 보존되지 않으므로 보관할 후보를 층에 적용하세요.

## RF 작업 순서

1. 쓰기 가능한 폴더에 프로젝트 생성 → 이미지 열기 → 클래스 이름 정의.
2. 각 클래스의 확실한 내부에 짧은 브러시 주석 입력. 배경도 별도 클래스입니다.
3. 문자·스케일바 등은 분석 제외 브러시로 표시.
4. 누적 주석으로 RF 학습 → 예측 확인 → 오분류 부분에 주석 추가 → 재학습.
5. 새 이미지를 열면 현재 모델로 자동 예측. 모델 저장/불러오기로 다른 PC에서도 사용.
6. 결과 JPG/라벨맵 저장. 독립 GT가 있을 때만 GT 평가.

21개 밝기·질감 특징을 사용하는 OpenCV RTrees(80 trees, depth 18)입니다.
미주석/제외 픽셀과 자동 예측을 학습 정답으로 넣지 않습니다. 재학습 시 누적 주석으로 forest를 새로 만듭니다.
RF 결과는 픽셀당 하나의 클래스이므로 겹침이 없습니다. 노란 빗금의 투표비는 보정된 정확도 확률이 아닙니다.
SAM과 RF는 별도 작업 흐름이며 자동 연결하지 않습니다.

## 코드 구성

| 파일 | 역할 |
|---|---|
| app.py / core.py | SAM 화면, 모델·추론, 마스크·세션 저장 |
| matsam_prompt.py / prompt_ops.py / auto_tools.py | 자동 점 생성, 필터, 다층 표시 |
| prompt_preview.py | 처리 영상 미리보기와 실제 실행 조건 일치 확인 |
| refinement.py | 이전 마스크 입력, 상태 복사, 되돌리기 |
| rf_app.py / rf_core.py | 부분 주석 UI, RF 학습·예측·저장 |
| test_*.py | 단위·회귀·숨긴 Tk 창 핸들러 테스트 |
| verify_release.py | 실제 RF와 선택적 SAM CPU 추론 검증 |
| RELEASE_NOTES.md / VALIDATION_v3_1.json | 이번 수정 사항과 검증 결과 |

## 재검증

SAM 의존성까지 설치한 환경에서 실행합니다.

```powershell
.venv\Scripts\python -m unittest discover -s . -p "test_*.py" -v
.venv\Scripts\python verify_release.py --checkpoint checkpoints/sam_vit_b_01ec64.pth
```

체크포인트 인자를 생략하면 RF만 검증합니다. 결과는 `results/release_validation`에 저장합니다.
기존 V2/V3 안내와 VALIDATION 파일은 과거 버전의 기록이며, 현재 동작은 이 README와 RELEASE_NOTES를 기준으로 합니다.

## 검증 범위와 미구현

합성 영상의 기능 검증이며 회사 TEM 정확도·속도를 보장하지 않습니다.
회사 PC 화면 배율 및 실제 마우스 사용성, ViT-H, CUDA, 학습된 Decoder 로딩은 이번 검증 범위에 포함하지 않습니다.
nm 환산·두께/CD 계측·실제 ROI 크롭·서버 학습·Decoder/LoRA 학습은 미구현입니다.
선택적 Decoder 입력은 동일 SAM 구조의 mask_decoder state_dict만 받습니다.

## 출처 및 라이선스

SAM: https://github.com/facebookresearch/segment-anything (Apache-2.0, licenses/SAM-Apache-2.0.txt).
MatSAM 프롬프트 출처: https://github.com/USTB-AI3DVIP/matsam . 원본은 vendor_reference에 보존했습니다.
MatSAM 원본의 명시적 라이선스 확인은 기존 프로젝트에서 미완료 상태이며, 이 배포는 이를 해결했다고 주장하지 않습니다.
전체 MatSAM 논문 재현은 아니며 공식 SAM AMG에 중심점+격자를 연결한 데모입니다.
예제 이미지와 RF 예제 모델은 합성 데이터 기반입니다. 회사 영상·계정 정보는 포함하지 않습니다.
