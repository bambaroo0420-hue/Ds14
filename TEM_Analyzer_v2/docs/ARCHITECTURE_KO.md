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
| `algorithms/orientation.py` | Hough/구조 텐서 보조 방향 | 프레임·문자 제외·방향 합의 |
| `routes/workflow.py` | `/api/workflow/*` 기능 연결·출력 | 새 HTTP 기능 |
| `jobs/manager.py` | 이미지/단계별 직렬 실행·취소·재시도 | 일괄 작업 |
| `web/bridge.js` | 기존 화면과 새 모듈의 어댑터 | 공통 상태 접근 |
| `web/modules/selection.js` | Ctrl/Shift·다중 삭제·드래그 | 목록 편의성 |
| `web/modules/metrology.js` | 회전·계측 화면 | 측정 옵션 |
| `web/modules/batch.js` | 진행률·취소·실패 재시도 | 일괄 처리 UI |
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
