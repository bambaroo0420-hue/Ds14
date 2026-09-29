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
