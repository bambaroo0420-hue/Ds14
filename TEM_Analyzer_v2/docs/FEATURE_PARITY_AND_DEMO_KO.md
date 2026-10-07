# 기존 기능 보존 감사 · 계측 도구형 UI · 데모

작성: 2026-09-30. 기준: v2.2.9, Git commit `281ddcfe9c12c397dd57804abbd9f6ed9f56e4ae`.

## 결론

기존 기능을 삭제한 것은 아니다. 배포 체크아웃의 SOURCE_SHA256.json에 기록된 **174개 파일**과 작업본을 CRLF→LF 정규화 후 비교했다. 누락 0, 내용 불일치 0이었다. 이전 작업은 새 MD와 별도 대화형 시안만 추가했다. 다만 **앞선 시안은 전체 기능을 담은 UI가 아니었고**, 기능 보존을 보여주는 설계로 불충분했다. 시안의 버튼과 실제 앱 기능을 동일시하면 안 된다.

‘기존 코드 존재’, ‘현재 시험 통과’, ‘새 UI에서 접근 가능’, ‘회사 영상에서 정확’은 서로 다른 상태다. 아래 표의 구현됨은 전자의 존재를 뜻하며 모든 UI 경로·모델·실제 영상에서 정상임을 보장하지 않는다.

## 1. 기존 기능 → 새 UI 대응표

| 구역 | 유지할 기존 기능 | 근거 파일/모듈 | 앞선 시안 누락/부족 | 새 UI 위치 |
|---|---|---|---|---|
| 프로젝트 | 이미지 등록·목록·여러 이미지 선택 | api.py / app.js / selection.js | 업로드·일괄 선택 생략 | 좌측 프로젝트 트리 |
| 프로젝트 | 이미지 삭제·휴지통 복원 | workflow.py / storage.py | 생략 | 트리 메뉴·휴지통 |
| 프로젝트 | Undo/Redo·재시작 복원·불변 mask | storage.py / v2_api.py | 제한적 시안 Undo만 | 상단 이력 + 하단 로그 |
| 환경 | 오프라인 모델·venv·시작/진단 BAT | INSTALL_KO.md / launchers | 생략 | 프로젝트·환경 메뉴 |
| 모델 | SAM 종류·CPU/GPU·로컬 checkpoint | api.py / sam_service.py | 생략 | 모델 관리자 |
| 모델 | decoder/refiner/adaptation 경로 | sam_service.py / adaptation_backend | 생략 | 모델 관리자 고급 |
| 스케일 | bar 자동/수동 양끝·수치/단위·nm/px | calibration.py / api.py | 화면 자체 생략 | 영상·스케일 작업공간 |
| 스케일 | 검출 제안/저장값/확정 분리 | batch.js / workflow.py | 생략 | 보정 표·속성 패널 |
| OCR | 확대 OCR·문자/배율/bar 제안·선택 제외 | annotations.py / ocr.py | 생략 | OCR 검출 레이어·지역 검토 |
| OCR | 템플릿 켜기/끄기·저장·복사·삭제 | app.js / workflow.js | 생략 | 선택형 템플릿 관리자 |
| 전처리 | SAM/경계/점 제안용 독립 denoise | preprocessing.py / feature_prompts.py | 일부 선택지만 표시 | 목적별 전처리 속성 |
| SAM | Grid 준비·점 미리보기·실행 분리 | prompts.py / app.js | 개념만 | SAM 도구막대·입력 레이어 |
| SAM | K-means/Canny/Sobel/Scharr/hybrid/profile | feature_prompts.py | 일부 방법·세부값 생략 | 특징점 생성 고급 설정 |
| SAM | 간격·edge clearance·분석해상도·프로파일 폭 | feature_prompts.py / profile_prompts.py | 생략 | 특징점 속성·미리보기 |
| SAM | 수동 +/−점·box·객체/독립점 방식 | api.py / sam_service.py | 부분 시안 | 프롬프트 트리·도구막대 |
| SAM | 예측 IoU·Stability·NMS | sam_service.py / index.html | 독립 ROI 시안에만 표시 | 자동 후보 속성 |
| ROI | 부모 내부 재분할·독립 ROI·후보 1/2/3 | roi_editor.js / roi_review.py | 독립 ROI만 시안 | ROI 작업공간 모드 선택 |
| ROI | 사전정렬·box 여백·절단 보호·원본 복원 | roi_alignment.py / roi_domains.py | 보호 근거 표시 부족 | 좌표/추론 범위 레이어 |
| 편집 | 후보 이름·복제·brush 수정·새 후보 | app.js / api.py | 생략 | 후보 메뉴·brush 도구 |
| 배정 | add/replace/split·부모/instance 관계 | api.py / selection.js | 단순 배정만 | 배정 패널 고급 모드 |
| 레이어 | 삭제·순서·잠금·합집합 표시 | workflow.js / layers.py | 순서·삭제 생략 | 레이어 트리 |
| 레이어 | 후보 대응/배정 제안 | layers.py / workflow.py | 생략 | 이미지 간 대응 검토 |
| 선택 | Ctrl/Shift·범위선택·일괄 검수/삭제/드래그 | selection.js | checkbox 시안만 | 트리/썸네일·캔버스 공통 선택 |
| scope | layer 없이 mask 집합 저장·검수·큰 미리보기 | scopes.py / scopes.js | 저장 scope 생략 | 분석 대상 트리 |
| 경계 | 후보 A/B·명시적 배경과의 cyclic Gradient+DP | boundary.py / v2.js | 알고리즘 설정 대부분 생략 | 경계·GT 속성 |
| 경계 | inside/outside·극성·연속성·거리·jump | boundary.py / v2.js | 폭만 표시 | 경계 비용 설정 |
| 경계 | profile·pin·local 구간·적용/취소 | v2_api.py / v2.js | 고정점 조작 생략 | 법선 그래프·제약 레이어 |
| 경계 | layer 전체 충돌/틈 검사·ROI 제한·제안 적용 | services/layers.py | 단순 전후 시안 | 충돌 검토 표·제안 diff |
| GT | background/unknown/uncertain/exclude/protect | labels.py / v2_api.py | 일부 범례만 | GT 상태 brush·보호 레이어 |
| GT | semantic·instance·edge·valid 출력 | labels.py / v2_api.py | 출력 조작 없음 | 출력 관리자 |
| 평가 | 검수 후보 기준 IoU/경계 평가·CSV | v2_api.py / v2.js | 생략 | 평가 작업공간 |
| 회전 | auto/edge/objects/points/image_direction | measurement.py / metrology.js | 하부 edge 하나만 | 기준선 속성·기준 비교 |
| 회전 | 방법 비교·잔차·warning·채택/확정 분리 | rotation_compare.js | 생략 | 후보 기준 비교 표 |
| 회전 | 원본↔정렬 matrix/inverse·원본 보존 | algorithms/metrology.py | 개념만 | 좌표계·변환 정보 |
| 계측 | thickness/CD·start/stop/step·단위 | measurement.py / metrology.js | 예시 값만 | 캘리퍼 속성·결과표 |
| 계측 | component center·길이/프레임/다중교차 정책 | measurement_sampling tests / metrology.py | 생략 | 샘플링·품질 설정 |
| 계측 | 원시값·무효사유·방향별 최신값 보존 | measurement.py / workflow.py | 생략 | 결과표·품질 열·양축 출력 |
| recipe | preset 이름 저장·동명 덮어쓰기 확인·Undo | prompt_transfer.js / prompt_transfer.py | 저장 문구만 | recipe 라이브러리 |
| recipe | normalized/ECC/ecc_masked·좌표 미리보기 | prompt_transfer.py | 일부 선택지만 | 프롬프트 대응 검토 |
| recipe | 이미지별 준비·미리보기 검토·확정·SAM | prompt_batches.py / prompt_batch.js | 실제 상태/실행 없음 | recipe 적용 표·작업 큐 |
| recipe | stale hash·실패된 새 준비의 옛 좌표 차단 | prompt_batches.py / jobs/manager.py | 경고 문구만 | 만료/보류 사유 |
| batch | OCR/SAM/배정/경계/회전/GT/계측 단계 선택 | workflow.py / batch.js | SAM만 표시 | 단계별 작업 큐 |
| batch | 진행·취소·실패격리·skipped·재시도·중단 복구 | jobs/manager.py / batch.js | 생략 | 하단 작업 큐·로그 |
| export | GT 선택·두 방향 CSV/JSON/PNG/ZIP | workflow.py / scopes.js | 출력 문구만 | 출력 관리자 |

표는 주요 사용자 기능 그룹의 대응표다. 모든 버튼/파라미터를 빠짐없이 연결했는지는 새 UI 구현 시 route/action ID별 체크리스트와 실제 GUI 시험으로 추가 확인해야 한다. 기능을 고급 패널로 옮기는 것은 가능하지만 접근 경로 없이 삭제하지 않는다.

## 2. 기존 자동화 기능의 실제 범위

현재 preset은 수동점·box + 자동점(Grid/feature 통합) + manual mode를 저장한다. 재사용은 좌표변환 후 검토하는 방식이며 **SAM 실행 자체와 분리**된다. 일반 Grid/feature batch는 새로운 자동점을 만드는 별도 경로다. 기존 recipe 수동점을 여기에 묵시적으로 합치지 않는다.

이미 존재하는 것을 살릴 항목: 저장/다시 선택, 단일/일괄 이전, 정합 선택, preview PNG, 검토·확정, stale 차단, 이전 후보 보존, 재시작 후 복원.

새로 필요한 항목: 여러 수동 객체 그룹, ROI/부모 대응이 포함된 recipe, 자동점 출처 분리, 대상별 feature 재생성 정책, 회전 기준·측정 구간까지 포함하는 통합 공정 recipe. 이들은 기존 기능이 ‘사라진’ 것이 아니라 원래 통합되지 않았던 요구다.

호환 원칙:

1. 기존 project/preset을 그대로 열어야 한다. 원본 JSON을 먼저 덮어쓰지 않는다.
2. 기존 단일 manual 객체는 새 구조의 Manual 1로 읽되 `independent` 의미를 유지한다.
3. 출처가 합쳐진 `auto_points`를 임의로 Grid/ML로 추정하지 않는다. `legacy_auto`로 보존한다.
4. feature_settings가 존재해도 옛 recipe를 자동으로 ‘재생성 모드’로 바꾸지 않는다. 기존 좌표 재사용이 기본 호환 동작이다.
5. 새로운 통합 recipe는 명시적인 ‘다른 이름/새 버전 저장’으로 생성한다. 이전 파일과 결과·검수 이력을 보존한다.
6. 새 UI는 기존 API/서비스 위에서 교체한다. 핵심 계산기를 동시에 전면 교체하지 않는다.

## 3. 계측 도구형 UI 원칙

웹 기술에서도 데스크톱 계측 작업대 같은 인터페이스가 가능하다. 웹페이지형 긴 입력폼 대신 다음을 사용한다.

- 상단 메뉴/도구막대: 프로젝트, 영상·보정, SAM, GT, 계측, recipe·일괄, 출력.
- 좌측 프로젝트 트리: 이미지 → layer → mask / 분석 scope / prompt group. 가시성·잠금·선택 상태.
- 중앙 문서 뷰: 원본/정렬 동기 비교, 눈금자·원점·좌표·스케일, 캘리퍼·기준선·ROI.
- 우측 속성 검사창: 현재 선택 도구의 설정만 표시. 고급 설정은 접더라도 기능 유지.
- 하단: 측정표 / 법선 profile / 작업 큐 / 로그 / 변경 이력 탭.
- 미리보기/적용/확정/저장 상태를 혼동하지 않는 용어. 잘못된 버튼은 이유와 함께 비활성.
- 패널 도킹·크기 조정·레이아웃 저장, 큰 비교창은 구현 대상. Windows 네이티브 앱으로 다시 만들 필요는 없음.

이번 UI 데모는 위 구조를 설명하는 제한된 POC다. 모든 메뉴를 기존 서버에 연결한 완성품은 아니다. 비연결 메뉴는 기능 보존 위치와 상태를 표시하며 실제 SAM/OCR/GT 버튼인 것처럼 동작 성공을 꾸미지 않는다.

## 4. 검증 결과

### 소스 보존

배포 manifest 174개 대조: 누락 0 / 내용 변경 0. 별도로 추가한 설계 문서·시안·테스트 산출물은 비교 대상 밖이다. Desktop 저장소에서 기존 ZIP 삭제 항목이 관찰됐지만 이번 작업에서 수정·복원·커밋하지 않았다.

### 회귀시험

첫 일반 unittest 실행은 `%TEMP%` 안에 만든 디렉터리의 하위 폴더 접근이 WinError 5로 실패했다. 앱 API 로직 실행 전 테스트 fixture 생성 단계다. 이를 코드 회귀 성공/실패로 해석하지 않는다.

기존 sandbox runner로 경로를 workspace의 새 독립 폴더로 바꾸고 테스트 폴더를 보존해 실행한 결과 **Python 169개, 56.197초, 통과**. 앱 저장/원자적 교체/권한 실패 테스트는 그대로이며 테스트용 TemporaryDirectory 생성/정리만 대체했다. 시험 경로: `tmp/release-v229/tests-183b4b01`.

Node UI 검사 **6개 스위트 통과**. 첫 시도에서 `@napi-rs/canvas` 미발견이 있었고, 기존 bundled NODE_PATH를 지정해 남은 검사를 통과했다. 새 패키지는 설치하지 않았다. 이 검사는 일부 DOM/서비스를 모사하는 회귀시험이며 실제 모델/실제 브라우저의 전체 경로 검증을 대체하지 않는다.

### 보존된 실제 SAM 마스크 재실행 데모

19.jpg 파생 5장에 대해 기존 SAM 후보를 읽기만 하고 새 테스트 프로젝트에 복사했다. 한 셀은 후보 1개, 세 셀은 가운데를 제외한 양끝 후보만 선택했다. **레이어 배정 0개인 상태**에서 회전 5/5, GT 없는 잠정 계측 5/5, 부분 GT+계측 10/10 단계 완료 및 ZIP 출력을 확인했다. 선택 밖은 Unknown으로 보존됐다. 이것은 기존 SAM 마스크를 사용한 workflow 재실행이며 새 SAM 추론은 아니다.

| 파생 이미지 | 계산 보정각 | 유효 계측 수 |
|---|---:|---:|
| 1cell +0° | +0.0919° | 22 |
| 1cell +7° | −6.7730° | 27 |
| 3cell +0° | 0.0000° | 46 |
| 3cell +7° | −7.0228° | 50 |
| 3cell −8° | +8.0063° | 52 |

가장자리 짧은 교차가 평균을 낮추는 현상이 여전히 있다. 예를 들어 3cell −8° 평균 139.5452, 중앙값 163.7779, 최소 0.5154 nm였다. 따라서 위 성공은 계측 정확도 인증이 아니다. 대상/구간/샘플링 정책과 전문가 GT 검수가 필요하다.

증거: `test-output/ui-audit-20260930-partial/results.json`, `partial-results.zip`. 원본 보존, 별도 프로젝트 사용.

### 실제 SAM recipe 재사용

별도 테스트 프로젝트에서 로컬 SAM ViT-B checkpoint로 5장을 새로 추론했다(CPU, torch 4 threads). 이전 좌표를 영상 크기 비율로 이전하는 `normalized` 경로다. 한 셀 preset에는 수동 +/−점·box와 자동점을 함께 넣었다. 세 셀 preset에는 자동점 2개를 넣었다. 이번 자동점은 이전 SAM mask의 거리변환 내부점이며, Canny/Sobel 등의 특징점을 새로 생성한 시험은 아니다.

| 파생 이미지 | 새 후보 수 | SAM 단계 시간(초) | 대상별 이전 SAM과 최대 IoU |
|---|---:|---:|---|
| 1cell +0° | 3 | 43.19 | 0.9854 |
| 1cell +7° | 3 | 35.44 | 0.9672 |
| 3cell +0° | 4 | 17.56 | 0.9835 / 0.9655 |
| 3cell +7° | 2 | 17.69 | 0.9315 / **0.0990** |
| 3cell −8° | 2 | 17.87 | 0.9872 / 0.9936 |

5장 모두 실행 완료했고 모든 후보는 레이어 미배정 상태로 남았다. 따라서 ‘SAM을 먼저 일괄 실행하고 나중에 layer 배정’하는 경로는 존재하고 실행됐다. **하지만 +7° 세 셀의 한 대상은 거의 대응하지 않았다.** 실행 완료만으로 올바른 mask라고 확정하면 안 된다. 크기 비율 이전은 회전·이동 정합이 아니다. 화면에도 이 경고가 생성됐으며, 새 UI에서 더 명확히 보여야 한다. 이번에는 ECC를 시험하지 않았으므로 ECC가 해결했다고 주장하지 않는다.

자동 검수 확정은 테스트 연결 확인용이며 사람의 과학적 검수를 대신하지 않는다. 이전 SAM과의 IoU는 일관성 비교이지 전문가 GT 정확도가 아니다. source project는 읽기만 했으며 테스트 프로젝트만 생성했다.

증거: `test-output/ui-audit-20260930-real-recipe/results.json` 및 같은 폴더의 `*_result.png`.

![실제 SAM recipe 재사용: 3cell +7도에서 일부 대상 대응 실패](../test-output/ui-audit-20260930-real-recipe/normalized_19_crop_3cell_+07deg_result.png)

## 5. 대화형 데모의 범위

계측 도구형 데모는 생성한 기하 마스크에서 기준선 피팅, 회전좌표 계산, 수직/수평 교차 길이와 nm 단위 변환, 설정/점 recipe 저장·복원을 실제 JavaScript로 수행한다. 표시 수치를 고정 문구로 바꾸는 시안과 구분한다. 단, **이 코드가 기존 Python 계측 엔진을 호출하는 것은 아니고**, SAM/OCR/DP는 대화 안에서 실행하지 않는다. 버튼 이름과 상태에 이 제한을 표시한다.

실제 기존 엔진 증거는 별도 Python/모델 실행 결과다. 데모 데이터의 저장은 대화 데모 상태 안이며 기존 project.json을 변경하지 않는다. 데모 recipe와 생산용 preset 스키마도 구분한다.

### 데모 조작 검증

- 순수 기하 계산 시험: −30°, 0°, 8°, 45° × thickness/CD 8조합에서 30 px 두께=15 nm, 80 px CD=40 nm 확인. 별도 축척/단일 mask/빈 선택 경계조건 확인.
- 실제 브라우저: 기준선 피팅 → 회전 확정 → 측정표와 캘리퍼 표시 확인.
- Recipe 저장 → 45° 예제로 변경 → 복원 시 8° 설정과 선택 mask 복원, 기존 결과는 만료 상태로 유지.
- 키보드로 두께 30→50 px 변경 → 결과 만료 → 재계산하면 25 nm. CD로 변경 후 재계산하면 40 nm.
- 두 번째 단일 확대 배치로 전환해 45° 예제의 −45° 보정과 15 nm 두께 결과를 브라우저에서 확인.
- 입력 자동화 `fill()` 한 번은 표시값만 바뀌고 change가 반영되지 않았다. 실제 키보드 입력과 Tab으로 다시 검증하여 결과 반영을 확인했다. 이 초기 시도를 성공으로 세지 않았다.
- 브라우저 콘솔 오류 조회 0건. 이 범위 밖의 완성 앱 GUI 전체를 검증했다는 뜻은 아니다.

![계측 작업대 데모: 기준점, 정렬, 캘리퍼, 결과표](assets/ui-redesign/workbench-demo.png)

기존 상세 요구사항은 [UI_REDESIGN_REVIEW_KO.md](UI_REDESIGN_REVIEW_KO.md)에 유지한다. 이번 문서는 기능 보존 감사와 추가 시험 결과이며 기존 요구사항을 대체하거나 축소하지 않는다.

## 다음 구현의 승인 기준

2026-10-01 추가 실제 모델·GUI 시험은 [목적 재점검·기능 감사](FUNCTIONAL_AUDIT_20261001_KO.md)에 정리했다. 19 증강, 실제 혼합 Recipe, 독립 ROI, 경계 GT, 선택 mask 일괄 회전·두 축 계측과 버튼별 실패를 포함한다. 디자인 데모와 생산 앱의 검증 증거를 구분한다.

새 UI 완료를 선언하려면 위 기존 기능 그룹의 route/action 연결과 파라미터 round trip, 기존 프로젝트·recipe 불변 로드, 독립 ROI 실패 재현/해결, 실제 SAM mixed prompt batch, 부분 GT/두 축 export, 오류/취소/Undo/재시작, 기능별 overlay 일치 시험이 모두 필요하다. 색상이나 레이아웃만 개선한 시안을 완성 버전으로 배포하지 않는다.

우선순위는 ① 기존 action/설정/recipe 호환 검사 ② 이미지·layer 고정 선택 및 통합 overlay ③ 독립 ROI와 여러 manual 객체/프롬프트 recipe ④ 충돌·틈·보호 brush·DP 시각 검토 ⑤ 기준선·계측 구간·무효값 표시 ⑥ 실제 모델 일괄 작업과 오류 복구다. 이번에는 생산 코드 교체, 원본 프로젝트 변경, Desktop 동기화, GitHub 배포를 하지 않았다.
