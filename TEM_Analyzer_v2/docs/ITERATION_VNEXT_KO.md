# vNext 반복 개선 기록 (진행 중)

요청 시간: 2026-09-30 02:39:53~07:39:53 KST (5시간). 작업 예약 ID: `tem-v2-5`.
예약은 20분 간격 후속 실행이며 PC·앱이 실행 중이어야 한다. 5시간 연속 계산이나 완료를 미리 보장하는 의미는 아니다.
종료 시각 이후 새 실험을 시작하지 않고 결과 정리 후 예약을 비활성화한다.

## 출발점

- GitHub PR #1, branch `codex/tem-v2-batch-metrology`, commit `b9cb34b`.
- 기존 공개 이미지 검토 42회 SAM은 feature-only였다. Grid+feature를 검증한 것으로 오해하면 안 된다.
- 이전 한계는 `PUBLIC_IMAGE_REVIEW_KO.md`, `ATTACHED_45DEG_REVIEW_KO.md`에 기록했다.
- 원본·기존 프로젝트 보존. 모델/공개 영상/첨부 영상/테스트 프로젝트는 Git에 올리지 않는다.

## 우선순위와 합격 기준

| 순서 | 개선·실험 | 검증 기준 |
|---|---|---|
| 1 | 특정 마스크만 선택한 부분 GT·회전·계측 | layer 미배정 허용, 미선택 영역 unknown, 별도 검수, 이미지별 선택 누락 시 실패, 일괄 API/GUI 검사 |
| 2 | OCR 과대 박스·scale 문자/바 결합 | 구조 전체를 덮는 박스 기본 비선택, 첨부 5 nm 링크 재현, 확정은 사용자 |
| 3 | 회전의 프레임 경계 오판 | 프레임 선을 0도 정답으로 확정하지 않음, 대각 구조 실제 검증 |
| 4 | Grid / feature / Grid+feature | 동일 입력·SAM 필터 조건, 점 개수·cold/warm 시간 구분, 결과 정확도와 비어 있지 않음을 구분 |
| 5 | 비슷한 이미지 프롬프트 재사용 | 좌표계 명시·미리보기·등록 실패 처리, 다른 이미지 좌표 맹목 복제 금지 |
| 6 | 최종 실제 구동·재검토 | 단위/API/실제 SAM·OCR/GUI 증거와 미해결 한계 기록, 검증 버전 PR 갱신 |

## 반복 이력

### 02:45 KST — 시작

기존 코드와 보고서 확인. `scope`를 레이어와 독립적인 선택 마스크 집합으로 설계 중.
부분 GT는 선택 집합의 이진 target이며 물질별 semantic GT라고 부르지 않는다.
겹치는 선택 마스크는 같은 target 합집합, 미선택 마스크의 물질 의미는 판단하지 않는다.
후속 실행 시 이 문서를 읽고 마지막 완료 지점에서 이어간다.

## 최신 검증 결과

### 03:10 KST 전후 — 1차 구현·실험 (아직 최종 배포 아님)

- 선택 scope: 레이어 0개 배정 상태에서 binary target 부분 GT, 미선택 unknown, 입력 변경 후 검수 만료, 삭제/복구. 두 이미지 일괄 GT→회전→확정→계측 테스트에서 합성 두께 20/10 nm 일치.
- 전체 Python 회귀 **75개 통과** (15.015 s). Node UI 회귀 통과. 이후 변경은 최종 재실행 필요.
- 실제 GUI 8881 테스트: existing_43의 미배정 후보 #2만 저장→GT 없이 회전→스케일→잠정 계측 110개 행. 이는 버튼/흐름 검증이며, 복잡한 SAM 구멍 때문에 물질 두께 정확도 증거가 아니다. 최초 91 px 테스트선은 실제 검출 기록 `[[16,402],[107,402]]`로 정정함.
- 첨부 45도 실제 OCR 재실행: 확대 재검출로 TiO…3 nm 추가, 총 6 영역. 5 nm/70.01298 px = **0.07141533 nm/px** 제안. 원본 보존, 모든 문자가 정확히 판독된 것은 아님, 화살표·색 선은 여전히 별도 문제.
- 첨부 SAM 경계 기반 회전은 여전히 실패: 기본 약 3.22°; frame edge 0도 오판은 차단했지만 잘못된 SAM 경계를 고친 것은 아님.
- 영상 보조 방향(Hough+구조 텐서)은 **44.1441°** 보정 제안, 수동 두 점 44.6067°와 약 0.463° 차이. 수동선은 전문가 GT가 아니므로 정확도 인증 아님. 색 선·OCR 제외, 일반화 추가 검증 필요.
- 기본 SAM의 `single_mask=True` 고정 문제 수정: base는 공식 multi-mask/AMG, 학습 bundle/decoder는 기존 single-mask 계약 유지.
- Grid/Sobel/Hybrid/Grid+Sobel × legacy single/native multi × 6 입력 = 48회 공정 비교 실행 중 (`test-output/compare-v220`, Python 세션 84058). nominal 16 points, 실제 개수 기록, 매 실행 encoder cold, pred .5/stability .7/nms .8 동일. 아직 결과 집계·시각 검토 전.
- 프롬프트 preset: 정규화 좌표 또는 ECC 작은 회전/이동 미리보기, SAM 자동 실행 없음. 실제 19.jpg +7° 시험에서 최초 크기 비율 ECC는 1.53°로 실패 → 중심 패딩(비등방 stretch 제거), 중앙 70% 정합, 다중 초기값으로 변경 → **7.0404°**, ECC 0.8758. 상관계수는 물질 대응 정확도가 아니다. 배율 변화는 ECC에서 지원하지 않음.
- UI 서버 8881은 구버전 Python 모듈 일부가 메모리에 있음. 이후 GUI 테스트 전 본인이 실행한 프로세스만 확인 후 재시작 필요. 기존 사용자 8876 프로젝트는 변경하지 않음.

### 조사 근거

- SAM 공식 구현: https://github.com/facebookresearch/segment-anything/blob/main/segment_anything/automatic_mask_generator.py
- SAM 논문: https://arxiv.org/abs/2304.02643
- OpenCV Hough: https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html
- 구조 텐서: https://scikit-image.org/docs/stable/api/skimage.feature.html#skimage.feature.structure_tensor
- ECC 좌표 계약: https://github.com/opencv/opencv/blob/4.x/modules/video/include/opencv2/video/tracking.hpp
- EasyOCR: https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/easyocr.py

외부 구현을 무단 복사한 것이 아니라 공식 API·방법을 참고하여 프로젝트 계산 모듈을 작성했다.

## 미완료

### 03:20 KST — 1차 검증 완료, 게시 준비

- 48회 SAM 비교 완료. 실제 cold SAM 시간 합 805.97 s. 공개5+첨부1, 4전략×2경로. `V220_REVIEW_KO.md`에 개수 표와 한계 기재. 일부 다른 실험 병행으로 시간 순위 판단은 하지 않음.
- 새 base multi-mask로 19 crop/회전 5장 통과. 최대 상대 회전 오차 0.1351°.
- 실제 SAM mask의 모든 layer 배정 해제, 3-cell 가운데 mask 미선택: 일괄 회전 5/5, 잠정 계측 5/5, partial GT+계측 10/10, ZIP unknown 보존 통과. `test-output/selected-scope-v220`.
- 실제 GUI 8881: preset 크기 변환 미리보기, 두 이미지 레이어 미배정 선택 scope, GT+회전 4/4, 계측 2/2. 스크린샷 `evidence-v220/selected-mask-batch.png` (작업 workspace 바로 아래).
- 실제 GUI 8882: 첨부 OCR 6영역, 0.071415 nm/px 표시, 영상 보조 방향 44.1441° 제안·원본/회전 비교창 확인. 사용자 확정 없이 제안 상태 유지.
- Python 전체 75개 + Node 회귀 다시 통과, 이후 방향 추정 알려진 45° 회귀 추가 assertion도 통과.

문서/PR 게시 및 main 앱 코드 동기화가 남았다. 그 후 thin-layer 자동점/큰각도 반례/중앙 계측 구간/QC를 추가 실험한다. 실제 5시간 작업의 최종 보고서는 시간 종료 후 갱신한다.

### 03:30 KST — 1차 v2.2 게시 완료, 후속 반복 대기

- 위 03:20의 게시 대기 상태는 해소됨. GitHub `codex/tem-v2-batch-metrology`에 `3fd554e909574cb3eb3ec2ad2dbb9fa25f7a7db8` 게시, 기존 PR #1 갱신. main은 병합하지 않음. 로컬 Git 작업 트리 깨끗함.
- Desktop 최종 검증: Python 75개 (10.582 s), Node UI 회귀, pip check 통과. SOURCE_SHA256 121개 소스 일치.
- 사용자 앱 8876: 본인이 시작한 이전 서버를 작업 없음 확인 후 재시작. 최신 Desktop 코드, PID 28768 / exec session 24253, 프로젝트 `test-output/crop19-v22/project` 보존. 모델은 재시작 후 다시 로드해야 하며 재설치/재다운로드 불필요. 사용자 브라우저 탭은 임의 새로고침하지 않았음.
- 독립 UI 8881: staging `test-output/ui-v220`, PID 13348 / session 3035. 두 이미지 모두 레이어 미배정이며 선택 scope로 GT·회전·계측 완료.
- 첨부 UI 8882: staging `test-output/attached-ui-v220`, PID 36364 / session 56586. 44.1441° 영상 보조 방향은 미확정 제안. 실제 SAM W 경계가 잘못되어 이 상태의 계측 정확도를 주장하면 안 됨.
- 증거: workspace `evidence-v220/selected-mask-batch.png`, `evidence-v220/attached-direction-44deg.png`. 보고서 `docs/V220_REVIEW_KO.md`는 GitHub에도 게시됨.
- 자동 후속 예약 `tem-v2-5` 활성. 07:39:53 KST까지 이어서 진행하되, 5시간이 지난 것처럼 보고하지 않는다. 종료 후 예약 비활성화 필수.

#### 다음 실행 우선 작업

1. `services/measurement.py`의 계측 위치/구간과 endpoint bias를 확인: 실제 19 +7°에서 median 165.35 nm vs mean 137.30 nm인 현상 재현. 자동으로 짧은 측정을 숨기지 말고 선택 가능한 중앙 구간·유효 구간/QC 및 제외 사유를 설계/테스트.
2. 영상 보조 방향의 큰각도·음성 대조군을 추가 실행. 첨부에서만 성공한 방법을 일반 자동 회전으로 승격하지 않음.
3. 얇은 층에 EDT 큰 영역 점이 편중되는 문제를 분석하고 프로파일/능선 기반 점 배치 등 다른 후보를 비교. Grid/feature/combined 구분 유지; point 수·mask 수 증가를 정확도 향상으로 주장하지 않음.
4. 부분 선택 scope 상태를 회전/일괄 UI에서도 명시. preset 일괄 적용은 현재 미구현이며 구현 시 이미지별 변환 실패를 명시적으로 중단.
5. 새 변경은 staging에서 apply_patch → `_tem_v2_sync.ps1` 승인 실행 → Desktop `tools/update_source_manifest.py` → 회귀 및 실제 구동 → 소스만 PR 갱신. 대량 JSON 대신 파일별로 내용을 읽고 remote tree SHA와 로컬 git write-tree를 비교하여 게시.

현재 로그의 이 항목은 다음 반복을 위한 staging 기록이며, 아직 별도 후속 커밋으로 게시하지 않음.

### 03:50 KST 전후 — 2차 v2.2.1 계측 표본 개선 완료, 게시 준비

- 원인 재현: 실제 1-cell +7° SAM mask의 전체 평균 137.304, 중앙값 165.351 nm, 약 0.595 nm 분절 포함. 마스크/축척을 바꾸지 않고 표본 정의 민감도를 비교.
- 전체(기본 유지)/연결 객체별 중앙 80·60%, 다중 교차·프레임 끝점·명시적 최소 길이 옵션. 제외 행/원시 nm/사유/좌표 보존, 원시 행 수 동일 검증. 자동 이상치 삭제 없음.
- 실제 SAM mask 5장×표본 정책5개=25/25 일괄 계측, ZIP5개 및 unknown 부분GT 확인. `test-output/sampling-v221/results.json`.
- 중앙60%+다중 교차 제외: 1-cell 0/+7° 평균 165.486/165.855 nm, 3-cell 0/+7/−8° 162.963/163.226/163.691 nm. 이는 표본 민감도/재현성이지 물리 정확도 증명 아님. 중앙60%만으로 3-cell0° 구멍 문제는 해결되지 않았음.
- 1px contour 누락 수정. 계측 알고리즘 버전 hash 변경: 기존 측정은 만료→재측정 안내. 기준 회전·축척은 유지.
- 방향 대조27개: 알려진22각도/잡음합성 최대오차0.03154°, 균일/잡음/동심원3개거절, 체크무늬/물결2개낮은신뢰. 실제TEM 일반화 미검증. `test-output/orientation-controls-v221`.
- Python83 tests PASS 11.245s, Node UI 회귀 PASS. API 부분 scope CSV 원시길이/빈 최종길이 검증 포함.
- 최신 독립 GUI8883에서 이전 계측 만료 표시 확인 후 선택scope + 중앙60 + 다중/프레임제외를 실제 클릭, 5장 GT+계측10/10, JS오류없음. 레이어는 모두 미배정, 3cell가운데 미선택 유지.
- 테스트 서버8883 PID29100 / exec session70063, cwd staging, 프로젝트 `test-output/sampling-v221/project`. CUA samplingTab id7, browser1, handoff 표시. 스크린샷 workspace `evidence-v221/selected-sampling-batch.png`, `tilted-three-cell-sampling.png`.
- 보고서 `docs/V221_REVIEW_KO.md`, 사용법/데이터계약/모듈문서 갱신. 아직 게시 전인 기록이며 다음 항목에 실제 commit을 남김.

#### 다음 반복 우선순위 (위 완료 실험 반복 금지)

1. 얇은 층 프롬프트: `feature_prompts.py`의 큰 EDT 영역 편중을 분석, 프로파일/능선/방향 기반 점 후보를 실제 공개 층상 영상에서 비교. GitHub/논문/공식 자료로 근거 확인. candidate 수를 정확도로 오해하지 말기.
2. 실제 TEM 영상의 영상방향 보조 추정: 첨부45° 및 다른공개 영상을 알려진 각도로 회전해 equivariance/실패를 검사. 합성 stripes 성공만으로 일반화 주장 금지.
3. UI 현재 canvas는 한 후보 mask(예:6)를 보여도 분석scope는 [6,8]일 수 있음. SAM 선택집합 미리보기는 있지만 회전/일괄에서도 전체 선택집합 표시 또는 명확한 legend를 제공하면 좋음.
4. preset 일괄 재사용은 여전히 미구현. 시간 범위 내 검증 가능한 경우 별도 실패 처리·미리보기 계획. 07:39:53 KST 이후 새 실험 시작하지 말기.

### 03:52 KST 전후 — v2.2.1 게시 완료

- GitHub branch/PR #1 업데이트: commit `6fd06724cdba169256853a68cb7b6da973a8d6d8`, tree `0ea8640fe81038542c1bc16c75ad56d082720963`, parent `3fd554e909574cb3eb3ec2ad2dbb9fa25f7a7db8`. 로컬 staged tree와 원격 tree 일치 후 게시. 로컬 fetch/update-ref 후 git status 깨끗함. main 미병합.
- Desktop 최종 Python83개13.054s / Node 회귀 / pip check 통과, 소스manifest125개. 가중치·영상·테스트프로젝트는 미업로드.
- 사용자 앱8876 재시작 완료: PID34972 / exec session15630, Desktop cwd, 기존 `test-output/crop19-v22/project` 유지. 진행 중 작업 없음을 확인했고 모델은 미로드였음. 사용자 탭은 임의 새로고침하지 않음.
- GUI8883은 PID29100 / session70063 최신 Python+UI. 알고리즘 hash 변경으로 이전 측정 만료를 실제 확인한 뒤 5장10/10재실행. 3cell+7°의 저장된 scope [6,8], 중앙60/다중·프레임제외, 유효24개/평균163.226nm 표시 확인.
- Node 모사 DOM 실행 시 NODE_PATH는 bundled `C:/Users/DJ.LEE/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`. 설치를 반복할 필요 없음.
- 함수별 자료: `tools/validate_measurement_sampling.py`, `tools/validate_orientation_controls.py`. 전자는 기존 SAM 결과 사용; 이번 반복에서 실제 SAM 신규 추론은 하지 않았음.
- 다음은 위 thin-layer 프롬프트/실제 TEM 방향 비교 우선순위로 계속. 이 마지막 게시 메타데이터는 staging 작업 기록이며 다음 코드 게시 때 포함한다. 자동 예약은 유지하며 종료 시각에 비활성화한다.

### 04:18 KST 전후 — 3차 v2.2.2 검증 완료, 게시 준비

- `algorithms/profile_prompts.py`: 반대 부호 밝기 경계 사이에 점을 놓는 횡단 프로파일. 방향 자동/수동, 원본 px 폭 제한, 512/1024 분석. 학습 ML/물질 분류 아님. SAM 실행과 분리, 기존 Grid/Sobel 유지.
- 실제 SAM24회 비교 완료: 합성0/+25/−45°×4방식 + 공개140/158/hafnia h×4방식. cold 추론 시간 합376.95s. Profile은 생성12띠 모두에 점, oracle 최고IoU 평균.9188; Grid.2688, Sobel.0148, Grid+Profile.4864. 자동 후보 선택 정답률 아님. 공개 전문가GT 없음, 해상도가 다른 레시피 비교.
- 실제 GUI8884: 미리보기는 SAM 미실행/점 미추가, 추가후ML16→실제SAM10후보. 0/−45 두장 Ctrl다중선택→SAM만·Profile만 일괄2/2, 신규6/18후보, 레이어 모두미배정. 신규 실제SAM 총27회(비교24+UI3). JS오류없음. `test-output/profile-ui-v222`, PID25172 / session58264, 모델로드됨.
- 실제 GUI8883: 저장target[6,8] 전체 큰미리보기, 3셀 중양끝2개만초록/중앙unknown 확인. 이전 후보단독canvas와 실제대상혼동 개선. UI2.2.2+Python2.2.1(해당API변경없음), PID29100/session70063.
- 실제TEM 추가회전28사례: 공개43/140/143의21사례 기존최대상대차이.30349°유지. 첨부−15추가의 기존14.78485°오차재현(기존도low-confidence).
- L2다중설정 항상사용하면 첨부equivariance .473°로작아도 기준각자체가약4°다른반례! 채택하지않음. 기존합의유지+실패/불일치때만fallback, fallbacktensor합의2°미만으로엄격제한. 첨부5변형은3.26~3.99°차이+모두낮은신뢰도. 자동수평해결완료아님.
- 방향합성22각도 최대.03154°, 균일/잡음거절, 동심원/체크/물결낮은신뢰도. 동심원이거절대신낮은신뢰도로바뀐한계기록.
- 방향검증첫실행은두번째프로젝트경로오기로JSON저장실패. 도구입력검증/단계저장수정후재실행. 무효실행중복카운트금지.
- Python90개16.778s, Node UI통과. Desktop최종테스트와게시진행중. `docs/V222_REVIEW_KO.md`에수치/실패/장단점/공식SAM·SciPy·OpenCV·μSAM·HQ-SAM자료기록. 외부모델미설치, 원본미변경.
- 증거 workspace `evidence-v222/selected-two-cells.png`, `profile-ui-sam.png`, `profile-batch.png`. CUA profileTab id8, samplingTab id7 handoff.

#### 다음 반복 후보

1. preset 일괄 적용 미구현: normalized/ECC각이미지별미리보기→검토된draft저장→SAM단계별실행, 실패이미지격리/기존후보보존. 기존개별preset은자동SAM아님. 사용자큰요구중남은명확한기능.
2. 얇은층 SAM crop/ROI 또는 대비극성·박스프롬프트 비교. 새 모델 다운로드 전 기존체크포인트로검증가능한범위. `profile`후보수/IoUoracle를semantic정확도로오해하지않기.
3. 첨부45변형 보조회전은여전히미해결. tensor단독각이나프로파일방향을추가해도물질경계검증대체아님. 기준라인 GT없이 "완전해결"이라고하지않기.
4. 07:39:53KST에새실험중지,원본보존·진행작업마무리·최종MD·heartbeat비활성화. 현재시각은아직4시대로5시간완료아님.

### 04:22 KST — v2.2.2 게시 완료

- GitHub branch/PR #1: commit `3d8be3d1ee5cd43d39a6adea9683c3443d7e4b28`, tree `77aca94b74b19f5646662e325dc199d94d22d963`, parent `6fd06724cdba169256853a68cb7b6da973a8d6d8`. 소스19개를 파일별로 읽어 원격 tree SHA와 로컬 staged tree 일치 확인 후 게시. main 미병합, 로컬 Git 깨끗함.
- Desktop 최종 Python90 tests PASS13.046s, Node UI PASS, pip check PASS, 소스manifest131개. 실제 GUI2장 일괄은 신규6/18후보, 모든 후보의 layer_id=None 확인.
- 사용자 앱8876: 활성 작업 없음/모델 미로드 상태를 확인하고 본인 실행 PID34972만 재시작. 새 PID38644 / exec session12236, Desktop cwd, 기존 `test-output/crop19-v22/project` 보존. 사용자 탭 임의 새로고침하지 않음.
- 독립 GUI8884: PID25172 / session58264, staging `test-output/profile-ui-v222`, 실제 모델 로드 상태. CUA tab8(profileTab) handoff, tab7(samplingTab) handoff. 8883 Python은 아직 v2.2.1 메모리이므로 새 profile/방향 검증에는 사용하지 말 것.
- 새 실험 기준 자료는 `docs/V222_REVIEW_KO.md`. 위 다음 반복 후보를 따라 진행하고 종료 시각을 준수한다. 이 게시 메타데이터는 staging 기록이며 다음 게시 때 포함한다.

### 04:54 KST 전후 — 4차 v2.2.3 검증 완료, 게시 준비

- preset 일괄 준비 → 이미지별 점/box 미리보기 → 검토 확정 → 별도 SAM 실행 구현. 자동/수동 object/독립 양성점 경로 구분, 후보 append-only/미배정. 준비와 SAM 동시 job 거절.
- 새 준비 실패/취소 시 예전 검토 draft 사용 차단. preset·source/target 영상/제외·대상 SAM필터 hash 검증. 이미지 삭제/복원에 draft 포함. 미리보기 로드 gate와 검수 선택 해제 유지.
- 실제 기존 normalized/ECC 비교11대상: SAM8완료/3차단. normalized 3cell+7 오른쪽 점이 배경으로 이동, 기존SAM와 최고IoU0.0990. 기존ECC3cell+7/−8은0.731/0.708로거절. 1cell+7은ECC0.8758로성공. 실패시Grid대체없음.
- OpenCV공식 양쪽 mask ECC 조사. 중앙50%+source/target제외로정합: 시제품실제SAM5완료/flat1거절. 3cell+7 양끝oracleIoU .9523/.9923, −8 .9727/.9944. 회사/전문가GT정확도아님.
- 미세질감합성9px이동에서단일해상도실패→128급coarse/512급fine추가. 4알려진각도+이동검증통과. 최종19생성변환5장 최대control위치차0.096926px; flat/무관잡음거절. 반복셀의고상관오대응·배율·큰변형미해결.
- 실제GUI8885:2장Ctrl선택·양쪽제외ECC준비2/2·각영상점확인·검수·SAM2/2신규각2후보. 기존후보보존/모두미배정. 추가0°미검수SAM차단→미리보기확정→실패재시도1/1성공. 이번반복실제SAM총16회(비교8+시제품5+최종GUI3).
- 108 Python tests PASS15.765s(상속공통테스트중복포함), Node기존+신규prompt_batch회귀PASS, pip check PASS. 새GUI로드gate수정후새로고침·재검수작동확인,JS오류없음.
- 실제환경OpenCV5.0.0.93이기존requirements<5와불일치발견. <6으로수정하되4.x전체검증미수행명시. 양쪽maskAPI기능검사/미지원명시적오류. 패키지재설치안함.
- 증거 workspace evidence-v223 및 test-output/prompt-reuse-v223, prompt-reuse-masked-v223/final-geometry.json, prompt-reuse-ui-v223. GUI서버8885 PID17112/session1681, 최신정합Python이나storage삭제후속패치는메모리구버전(단위테스트별도검증). 모델로드상태. CUA reuseTab id9.
- 상세 docs/V223_REVIEW_KO.md, 모듈/설치/데이터계약갱신. Desktop동기화·최종검증·PR게시진행예정. 아직5시간종료아님, 예약유지.

#### 다음 반복 후보

1. ROI/crop SAM을 첨부 얇은층/공개층상영상에 적용해 전체영상 점기반과 비교. 기존부모mask가필요한ROI편집경로와 독립box/prompt 경로의 사용자의도차이검토. 새모델다운로드없이검증가능범위부터.
2. 첨부45도 방향의 색선·화살표 영향, material 경계검증없는 높은신뢰도 자동확정 금지. v222실패반례를그대로기준으로사용.
3. preset잘못된점의영상별수정편의·다중preset은아직제한. 검수생략자동화보다실패격리/명시적경고우선.
4. 07:39:53 KST 이후새실험금지,진행작업안전마무리·최종MD·heartbeat비활성화. 다음에는이반복의16회실험을그대로반복하지말것.

### 04:59 KST 전후 — v2.2.3 게시 완료

- GitHub 기존 branch/PR #1 갱신: commit `8934bd02be4ff2959d0396b4b9eb24b1aa8ea2b4`, tree `7c7ae70ddc0e50f39fb0235a6e91fa045b19a9bd`, parent `3d8be3d1ee5cd43d39a6adea9683c3443d7e4b28`. 27개 소스·문서 파일을 개별 읽기, 로컬 staged tree와 원격 tree 일치 후 게시. fetch/update-ref 후 Git 깨끗함. main 미병합.
- Desktop 최종 Python108 tests PASS16.632s, Node기존+신규 UI PASS. manifest141개. 보고서 V223_REVIEW_KO.md는 실제SAM16회(비교13+GUI3), GUI미검수실패→검수→재시도를 포함. 파이프라인 검수와 전문가GT를 명확히 구분.
- 사용자 앱8876: 진행작업0/모델미로드/정확한CLI 확인 후 본인PID38644만중지. 새PID38008 / exec session64563, Desktop cwd, 기존test-output/crop19-v22/project 유지. HTTP200/2.2.3/새검수API/영상5장 확인. 사용자브라우저는임의새로고침안함. 모델파일재설치불필요.
- GUI8885 PID17112/session1681 유지. 최종정합알고리즘/새GUI테스트완료, 실제모델로드됨. storage.py삭제draft메타데이터후속패치는서버메모리미반영이므로삭제테스트하려면해당서버재시작필요(Desktop108회귀에서는검증완료).
- CUA reuseTab9, profileTab8, samplingTab7 handoff. 증거 evidence-v223/transferred-three-cell-points.png, reuse-sam-batch-complete.png, review-gate-retry-complete.png. 다음반복은새ROI/얇은층검증으로이어간다.
- 자동예약 tem-v2-5 계속활성. 07:39:53 KST 종료에비활성화해야한다. 이마지막게시메타데이터는staging기록이며다음코드게시때포함한다.

### 05:30 KST 전후 — 5차 v2.2.4 검증 완료, 게시 준비

- 부모 없는 독립 ROI 확대 분할, 기본 SAM 3후보 선택, 저장 전 preview, 점 불일치 QC 경고. parent ROI 경로 유지. 새 의존성/모델 설치 없음.
- 실제 SAM 38예측: 7사례×full/crop=14 cold(191.555s), 7 ROI×3후보=21(95.816s; 7 cold+14embedding reuse), 실제GUI3(1cold+2reuse). 합성3px띠0/30/45° localIoU full .05547/.04457/.04474 → crop .75188/.64392/.66667. 자동 물질 분류 성능 아님.
- 첨부TaOx/TiOxNy는 세후보모두 음성점2개위반+이웃층포함 실패. 최고score .994/.990도오답. TiOxNy후보3각−44.38은오버레이가잘못돼성공으로세지않음. 공개140/hafnia는무GT;hafnia기존OCR제외후양성1개뿐.
- inference_domains provenance/상속, 내부crop2px근접foreground+2pxdilation unknown, 자동회전/DP보호. 첫계측도구는45°출력이1~2px안쪽에멈춰exact-touch가정실패→near-edge보완→새폴더최종완료. 원본mask불변. 전체부모ROI edit는새cutdomain붙이지않음.
- 실제SAM후보3만선택한합성3장:회전3/3→미검수계측3/3→부분GT+계측6/6→ZIP. 레이어미배정/다른후보보존/cutunknown확인. 평균4.000/3.332/4.161px vs생성3px, 분절/과대오차남음. 회전추정0/29.92407/44.61723°. 계측정확도성공아님.
- Python116 tests PASS21.895s, Node기존+prompt_batch PASS, pip check PASS. Desktop최종검증/게시예정.
- 실제GUI8886 독립드래그ROI[601,64,899,420], +3/−2,후보3→1→3,이전previewaccept차단,후보22만미배정scope,GT없이회전−29.95847/계측. 최종near-edge서버재시작후이전결과만료→재회전/확정/계측확인. 평균3.5496/중앙4.3932nm(생성1nm/px),유효19/무효21/교차없음125,cut145px. JS오류없음.
- GUI8886 PID20844/exec session9961, staging test-output/roi-ui-v224,모델미로드(이전PID1756에서실제SAM3회후재시작). CUA roiTab224 id10 handoff. 증거 evidence-v224/independent-roi-rotation.png 및 final-roi-rotation.png.
- 상세 docs/V224_REVIEW_KO.md. 도구 compare_roi_prompts.py/compare_roi_alternatives.py/validate_roi_metrology.py. 결과 roi-compare-v224/roi-alternatives-v224/roi-metrology-v224-final. 실패초안 roi-metrology-v224도보존. 모델/영상/결과ZIP미업로드.

#### 다음 반복 후보 (38회 같은 실험 반복 금지)

1. 얇은층 계측에서 invalid_region이 crop끝이 아닌 내부에도 다수 발생. 후보의 실제구멍/분절과 contour끝점 반올림 validity 오판을 구분하기 위해 알려진3px binary띠0/30/45° 직접계측 대조. SAM오차와측정알고리즘오차를분리. 작은값을몰래삭제하거나GTvalidity를전부true로바꾸지말기.
2. 첨부45°ROI분할은미해결. 알려진방향보조사전정렬+좁은box/프로파일 비교후원본좌표복원 검토. 색선/화살표가물질정답이라는가정금지. 별도입력/출력보존.
3. 독립ROI일괄레시피/ROI자동탐색은아직미구현. 기존preset일괄과혼동하지말기. 신규외부모델전공식자료와데이터적합성확인.
4. 종료07:39:53KST(22:39:53UTC)새실험중지/진행중작업안전마무리/최종MD/heartbeat tem-v2-5비활성화. 현재05:30대로종료아님.

### 05:34 KST — v2.2.4 게시 완료

- 기존 branch/PR #1: commit `866abe4e0477a266314e32938863502bdbc4da63`, tree `3b4665d559bf0cbcf8e2d4f8c9cf3b4c7306aeca`, parent `8934bd02be4ff2959d0396b4b9eb24b1aa8ea2b4`. 소스27개 파일별읽기, 원격/로컬tree동일확인후nonforce게시. fetch/update-ref후Git깨끗함. main미병합.
- Desktop 최종 Python116 PASS20.425s, Node기존+prompt_batch PASS, manifest147개. 영상/가중치/ZIP/테스트프로젝트미게시. 최종독립ROI사용/한계/모듈계약은V224_REVIEW_KO.md와관련문서.
- 사용자앱8876 작업0/모델미로드/CLI확인후본인PID38008재시작. 새PID16252 / exec session81562, Desktopcwd, 기존test-output/crop19-v22/project유지. HTTP200/v224/후보선택API/5장확인. 사용자탭임의새로고침없음.
- GUI8886 최종near-edge Python PID20844/session9961,모델미로드, 프로젝트roi-ui-v224. 최종계측UI에서유효19/평균3.550nm/near-edge경고표시확인. UI오류없음. CUA roiTab224 id10 handoff.
- 다음우선순위는위얇은층계측validity대조/첨부45도제한box실험. 38예측반복하지말고이어갈것. 종료까지약2시간남음, heartbeat계속유지. 마지막게시메타데이터는staging기록이며다음게시때포함한다.
- 게시후최종스크린샷확인중IAB큰비교의오른쪽영상이일시적으로검게표시됨. API원본PNG는1587×1211/max225/비검정784387px로정상,JS로그오류없음. 이미지complete속성브라우저조회는2번시간초과. 테스트탭새로고침→저장30°영상다시선택→비교열기후정상수평영상표시확인/최종PNG저장. 원인확정아님, 추후이미지로딩·실패표시보완검토. 사용자8876탭은건드리지않음.

### 05:50 KST 전후 — v2.2.5 contour validity 검증 완료, 게시 준비

- SAM 없는 binary 띠에서도 false invalid 재현. 보간 contour 길이 vs 반올림 픽셀 샘플 validity의 기하 불일치. 같은 contour의 연속 interval coverage로 변경, 실제 invalid/unknown은 그대로, 길이·좌표 불변.
- 4폭×6각도×3validity=72조건: target_valid 무효278→0/유효699→977, all_true진단977유효그대로, 명시적무효띠 무효523→340/유효454→637. 72조건모든원시길이/원본끝점동일. 0.02px무효교차차단회귀. 수식3px띠45°의binary측정3.53553px 등 rasterization 오차는 남음.
- 기존실제SAM3출력 비교: 유효97/62/72→97/143/159, 무효3/88/91→3/7/4. 평균4/3.3321/4.1612→4/3.5298/4.2385px; 새로운정확도성공아님. 신규SAM추론0. 기존38회반복하지않음.
- 새프로젝트roi-metrology-v225: 레이어없는선택후보3장회전3/3→잠정계측3/3→부분GT+계측6/6→ZIP. crop보호81/142/69px모두unknown검증. 기존roi-metrology-v224-final보존.
- CSV/JSON valid_coverage_px/invalid_coverage_px, UI무효길이, 측정hash contour_validity_v3로기존측정만료. 회전hash그대로. 새패키지없음.
- GUI8887 실제이전결과만료→GT없는재계측(mask22만): 유효19→38,무효21→2,교차없음125,평균3.7634224/중앙4.1208274nm,보정각−29.95847°. 생성1nm/px. 무효구간2.4504/3.8151px표시.
- 실제GUI미검수GT차단→선택검수확인→실패재시도GT+계측2/2완료. 확인대화상자가열려navigation비활성인상태에서자동화클릭2회시간초과했으나앱오류아님; 대화상자확인후진행. JS오류없음. 영상비교양쪽정상확인, 이전검은미리보기근본원인미해결.
- Python121 PASS25.218s, CSV보강후scope7 PASS1.905s, Node기존+prompt_batch PASS. Desktop최종검증/게시예정.
- 테스트서버8887 PID21796/exec session29824, stagingcwd/test-output/contour-ui-v225(기존roi-ui-v224복사), 모델미로드. CUA contourTab225 id11 handoff. 증거 evidence-v225/rotation-and-validity.png. 모델/영상/JSON결과는미게시.
- 상세V225_REVIEW_KO.md/관련모듈문서. 결과contour-validity-v225/before.json/after.json,roi-metrology-v225. 단회진단시간11.832→12.156s. 회사/전문가GT없음. 새실험중지시각07:39:53KST는아직도달하지않음.

#### 다음 반복 후보

1. 첨부45°ROI 분할 미해결: 방향 보조 사전정렬+좁은box/프로파일을 원본좌표복원과 함께 검토. 생성띠·공개무GT·첨부물질을구분할것. 스케일/주석을지운것만으로물질GT정확도성공으로간주하지말것.
2. 비교미리보기 로드/실패 안내는추후보완가능. v224일시검은영상은API정상, 이번GUI정상이나원인확정아님.
3. 같은72조건/기존38추론그대로재실행하지말것. 독립ROI일괄레시피는아직없고preset일괄과구분.
4. 종료07:39:53KST(22:39:53UTC) 이후새실험중지·최종문서·heartbeat tem-v2-5비활성화. 지금예약유지.
