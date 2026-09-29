# TEM Analyzer v2.0.1 수정 안내

## 2026-09-29 수정: 레이어·제외 ROI·재분할 검수

- `레이어 추가`는 이름 입력창 없이 `Layer N`을 바로 생성합니다. 원하는 이름은 생성 후 `이름 수정`에서 바꿀 수 있습니다. API도 빈 이름/공백을 자동 이름으로 처리합니다.
- 글씨/스케일 제외 ROI를 드래그하면 기존 Grid·ML·수동점 중 제외 영역의 점을 제거합니다. Grid/ML 생성·SAM 실행·ROI 편집 전에 현재 이미지에 제외 영역을 자동 적용합니다. 서버도 오래된 제외 영역 안의 점을 추론 전에 걸러내며 마스크 출력에서 제외합니다. 다른 이미지 전체 적용은 기존 일괄 적용 기능을 사용하세요.
- ROI 재분할은 `재분할 미리보기` → 주황색 결과 확인 → `확인 후 새 후보 저장`의 순서입니다. 미리보기 중에는 프로젝트에 후보나 mask 파일을 만들지 않습니다. 취소/창 닫기는 저장하지 않습니다. 입력이 바뀌면 미리보기를 무효화합니다.
- 임시 미리보기는 15분 동안 유지되며 최대 4개입니다. 서버 재시작 또는 부모/모델/전처리 변경 후에는 다시 실행해야 저장할 수 있습니다.
- 설치 후 기존 서버를 종료하고 새 폴더에서 다시 실행하세요. 브라우저도 새로고침해야 합니다.

# TEM Analyzer v2.0.0

TEM 원본 해상도에서 SAM 후보 생성 → 기존 마스크 수정 → 레이어 확정 → 공유 경계 보정 → GT 출력까지 수행하는 로컬 도구입니다. `TEM_Analyzer_v1`과 별도 폴더/프로젝트로 실행합니다.

## 설치와 실행

Python 3.10 이상을 권장합니다.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

브라우저에서 `http://127.0.0.1:8765`를 엽니다. Windows에서는 `install_windows.bat`, `start_windows.bat`를 사용할 수 있습니다. 기본 실행은 로컬 주소에만 바인딩합니다. 앱이 이미지나 추론 결과를 외부 서비스에 전송하지 않습니다. 회사 환경에서는 승인된 wheel/모델 파일을 미리 준비하세요.

SAM 사용 시 장치에 맞는 **torch + torchvision**을 별도로 설치해야 합니다. 공식 SAM Python 소스는 `adaptation_backend/vendor/segment-anything`에 포함되어 있으므로 별도 git 다운로드는 필요하지 않습니다. SAM 가중치는 포함되어 있지 않습니다. OCR은 선택 사항이며 EasyOCR 및 로컬 가중치가 필요합니다. OCR 자동 다운로드는 꺼져 있습니다.

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
