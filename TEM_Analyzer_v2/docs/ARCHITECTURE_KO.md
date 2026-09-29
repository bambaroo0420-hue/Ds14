# 구조와 수정 위치

기존 기능은 유지하고 v2.1 추가 기능을 계산·서비스·라우트·화면 모듈로 나누었습니다.
기존 `api.py`, `v2_api.py`, `app.js`, `v2.js`는 호환을 위해 남아 있으며 완전히 분해한 구조는 아닙니다.

| 파일/폴더 | 책임 | 수정 예 |
|---|---|---|
| `run.py`, `start_windows.bat` | 실행·프로젝트 선택 | 포트/프로젝트 경로 |
| `tem_analyzer/storage.py` | JSON 저장, 불변 마스크, Undo/Redo, 휴지통 | 저장·복원 계약 |
| `tem_analyzer/labels.py` | 레이어 합성, 유효/제외/충돌 | GT 코드 규칙 |
| `tem_analyzer/ocr.py` | 로컬 EasyOCR·Reader 캐시 | OCR 언어/모델 |
| `tem_analyzer/sam_service.py` | SAM 로드·프롬프트·임베딩 캐시 | SAM 추론 |
| `feature_prompts.py`, `prompts.py` | 선택형 ML/에지 추가점·Grid·미리보기 | 방식/거리/노이즈 제거 선택 |
| `preprocessing.py` | 원본 불변 SAM/경계 필터 | Gaussian/Median/Bilateral/NLM |
| `algorithms/annotations.py` | 문자/배율/바 박스 제안 | 촬영 표기 분류 |
| `calibration.py`, `operations.py` | 실제 바 길이·숫자/단위 매칭 | 축척 인식 |
| `boundary.py` | 마스크 외곽 법선 Gradient + cyclic DP | 경계 비용·극성·연속성 |
| `services/layers.py` | 레이어 합집합, 충돌, 공유 경계, 대응 | 자동 보정 폭·층 순서 |
| `algorithms/metrology.py` | 강건 직선·변환·경계 교차 | 회전/두께/CD 계산 |
| `services/measurement.py` | 검수 조건·입력 해시·계측 버전 | 결과 만료 조건 |
| `services/scopes.py` | 레이어 없는 선택 mask target·부분 GT | 검수 hash·unknown 계약 |
| `services/prompt_transfer.py` | 재사용 preset·정규화/ECC 좌표 변환 | 정합 QC·pixel-centre 기준 |
| `services/prompt_batches.py`, `routes/prompt_batches.py` | 영상별 재사용 draft·입력 hash·검수·실행/PNG | 준비와 SAM 분리, 오래된 draft 차단 |
| `algorithms/orientation.py` | Hough/구조 텐서 보조 방향 | 프레임·문자 제외·방향 합의 |
| `algorithms/profile_prompts.py` | 얇은 층의 횡단 프로파일 점 제안 | 방향·에지 쌍·평활·폭 제한 |
| `routes/workflow.py` | `/api/workflow/*` 기능 연결·출력 | 새 HTTP 기능 |
| `jobs/manager.py` | 이미지/단계별 직렬 실행·취소·재시도 | 일괄 작업 |
| `web/bridge.js` | 기존 화면과 새 모듈의 어댑터 | 공통 상태 접근 |
| `web/modules/selection.js` | Ctrl/Shift·다중 삭제·드래그 | 목록 편의성 |
| `web/modules/metrology.js` | 회전·계측 화면 | 측정 옵션 |
| `web/modules/batch.js` | 진행률·취소·실패 재시도 | 일괄 처리 UI |
| `web/modules/prompt_batch.js` | preset 일괄 준비·이미지별 미리보기·검토 표 | 이미지 로드 gate, 검수 행 선택 |
| `web/modules/workflow.js` | 자동 제외·레이어 경계 화면 조립 | 페이지 기능 연결 |
| `web/modules/scopes.js`, `prompt_transfer.js` | 선택 범위·프롬프트 재사용 UI | 저장·미리보기·별도 실행 |
| `tests/`, `tools/` | 수치/API 테스트·실제 모델 검증 | 회귀 재현 |

경로가 짧게 쓰인 Python 파일은 모두 `tem_analyzer/` 아래입니다.

새 기능은 **배열 계산 → 서비스 → 라우트 → 화면** 순서로 추가하세요.
배열 계산 함수는 프로젝트 파일이나 HTTP를 직접 다루지 않습니다.
UI의 새 버튼은 해당 모듈에서 한 번만 연결하고, 기존 전역 함수를 다시 덮어쓰지 않습니다.

일반 API 변경은 `v2_api.py`의 직렬 트랜잭션과 Undo 체크포인트를 통과합니다.
작업 상태·취소 경로는 긴 추론 중에도 응답하도록 별도 처리합니다.
일괄 작업은 같은 직렬화 잠금 안에서 단계별로 저장하며, 오류가 난 단계의 메타데이터를 복원합니다.
이미지 하나의 실패는 다른 이미지의 처리를 막지 않습니다. 서버 재시작 시 진행 중 작업은 `interrupted`입니다.

마스크 파일은 새 ID로 저장합니다. 수정 전 파일을 덮어쓰지 않습니다.
입력 해시는 마스크·레이어·유효/보호 영역·분석 전처리에 연결되고, 계측은 회전과 스케일까지 포함합니다.
스케일만 바꾸면 계측은 만료되지만 회전은 유지됩니다. 마스크를 바꾸면 둘 다 만료됩니다.

`SOURCE_SHA256.json`은 소스의 CRLF를 LF로 정규화한 SHA-256입니다. Windows checkout 줄바꿈 차이를 무시합니다.
소스 변경 후 `python tools/update_source_manifest.py`로 재생성합니다. 모델·프로젝트·생성 이미지는 대상이 아닙니다.

v2.2.1 계측 표본 정책은 `algorithms/metrology.measure(..., sampling=...)`의 순수 배열 계산입니다.
서비스에서 정책을 전달하고, UI와 일괄 작업은 같은 `measurementConfig()`를 사용합니다.
새 제외 정책은 원시 행을 삭제하지 말고 `quality_flags`/`exclusion_reasons`에 추가하세요.
값으로부터 임의로 이상치 임계값을 학습하거나 최종 길이를 조작하지 않습니다.
알고리즘 변경으로 값의 의미가 달라지면 `services/measurement.measurement_hash`의 버전 표식도 갱신하세요.

v2.2.2 프로파일 설정은 `feature_prompts.FeatureConfig` → `propose` → `profile_proposals` 순서입니다.
점 준비는 SAM 호출과 분리되며, 새 방식은 단일/일괄의 같은 FeatureConfig 검증을 거칩니다.
`tools/compare_profile_prompts.py`는 생성 GT와 공개 무GT 데이터를 명시적으로 구분합니다.
`tools/validate_real_orientation.py`는 원본을 읽기만 하며, 알려진 추가 회전의 일관성을 검증합니다. 기준 방향 정확도 시험으로 해석하지 마세요.
방향 보조 모드는 기존 합의가 충분할 때 유지하고, 실패/불일치 시 L2 Canny의 제한된 설정을 탐색합니다. 보조 후보는 텐서와 2° 미만 일치해야 높은 신뢰도 제안이며, 그 외는 미확정 경고입니다. 높은 신뢰도도 물질 경계 인증은 아닙니다.

v2.2.3 재사용은 `JobManager(prompt_transfer)` → `prepare_transfer`만 실행하고, 검수 후 별도 `sam`의 `prompt_source=transferred`가 `run_transferred`를 호출합니다.
새 준비 시작 시 기존 review를 먼저 만료시켜 부분 실패/취소에 옛 좌표가 살아나지 않게 합니다.
`current_transfer` 검증을 우회하거나 실패 때 Grid로 대체하지 마세요. `tem:idle`에서 미리보기 로드 gate를 재적용합니다.
`transfer_matrix`의 양쪽 제외 ECC는 optional OpenCV API입니다. 기존 ECC 경로를 유지하며 새 패키지 기능 미지원은 명시적 오류로 처리합니다.

v2.2.4 독립 ROI는 기존 `ROIEditor.open(imageId, null, image)`와 `/api/sam/prompt`의 preview 경로를 재사용합니다.
`ModelService.in_roi`가 원본 좌표 `inference_domains`를 만들고, `Project.put_candidate`가 부모 도메인을 상속합니다.
`roi_domains.crop_contacts/crop_guard`는 near-edge 판정과 validity 보호의 단일 구현입니다. UI 경고와 GT/측정이 다른 규칙을 쓰지 않게 하세요.
일반 부모 ROI edit는 바깥을 보존하므로 새 도메인을 붙이지 않습니다. crop-only 예측과 혼동하지 마세요.
mask 파일은 불변으로 두고 GT validity/회전 기준/Gradient+DP guard를 바꿉니다. 규칙 변경 시 fingerprint의 roi_cut_guard_version도 올리세요.
기본 SAM 후보 번호는 0/1/2(API), 1/2/3(UI)입니다. single-mask 모델에는 없는 번호를 조용히 대체하지 않습니다.
