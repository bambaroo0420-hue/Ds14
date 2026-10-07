# v2.2 1차 개선·실구동 검토

2026-09-30. 요청한 5시간 반복 작업의 **첫 검증 묶음**이다. 5시간 전체 완료 보고서는 `ITERATION_VNEXT_KO.md`를 확인한다.

## 사용자 의도와 변경

| 요구 | v2.2 처리 | 남은 한계 |
|---|---|---|
| Grid와 ML을 분리하여 SAM | 점 준비는 별도, 최종 SAM에 합쳐 실행. 배치는 Grid/feature/Grid+feature 선택 | K-means는 비지도 군집, Canny/Sobel 등은 영상처리이지 학습된 물질 판별기가 아님 |
| 모든 층을 분류하지 않고 필요한 mask만 | 이미지별 named scope에 mask ID 저장. 레이어 배정 없이 회전·계측·부분 GT | scope는 한 binary target 합집합, 물질 semantic class나 instance GT가 아님 |
| 비슷한 이미지에 prompt 재사용 | preset 저장, 크기 비율 또는 ECC 정합 미리보기, 이후 별도 SAM 실행 | ECC는 동일 pixel sampling·유사 시야·작은 회전/이동용. 배율/구조 변경·대각 45° 대응 보장 안 함. 배치 preset 자동 적용은 아직 없음 |
| 텍스트/scale OCR 실패 개선 | 확대 재검출 선택, 과대 박스·숫자 없는 bar 기본 비선택, OCR box가 bar를 포함한 경우 처리 | 모든 화살표/색 선/문자를 완전히 지우는 기능 아님 |
| 잘못된 0° 자동 회전 방지 | 프레임/제외 경계를 fit에서 제거, 자동 모드 반대 경계 fallback 시 경고 | SAM mask 자체가 틀리면 mask 경계 회전도 틀림 |
| 큰 기울기 대안 | 영상 Hough 방향 합의+구조 텐서 보조 추정 | 실제 특정 layer 경계가 아닌 영상 주 방향. 항상 검토 필요 |
| 실제 버튼 동작 | 독립 서버에서 preset·scope 저장, 미배정 mask 회전·계측, 두 이미지 일괄 GT/회전/계측 클릭 | 회사 이미지·전문가 GT 정확도 미검증 |

기본 SAM까지 `single_mask=True`로 고정되었던 경로도 수정했다. 공식 base SAM은 multi-mask/AMG, 학습 decoder/refiner bundle은 학습 당시 single-mask 계약을 유지한다. 기존 프로세스는 재시작하고 모델을 다시 로드해야 새 경로를 사용한다. 재다운로드/재설치는 필요 없다.

## 선택 mask만 쓰는 방법

1. `2 SAM·레이어`에서 이미지 선택 → 후보 목록 Ctrl/Shift 다중 선택.
2. `특정 마스크만 분석 · 부분 GT`에서 집합 ID(기본 `target`)로 저장. 이미지마다 동일 ID를 사용해도 실제 mask ID들은 각각 별도로 저장된다.
3. 회전·계측·GT·일괄 출력 범위를 `저장한 선택 마스크 집합 사용`으로 둔다.
4. 회전 제안 → 결과와 scale 확인·확정 → 계측. GT나 layer는 필요 없다. 미검수이면 `provisional_unreviewed_masks` 표시.
5. 부분 GT가 필요할 때만 집합 미리보기 검수 확정 → GT 검사/ZIP 포함 체크.
6. 일괄은 GT 검사/회전 제안과 계측을 나누어 실행한다. 회전 제안 후 확정해야 계측할 수 있다.

선택 마스크끼리 겹친 부분은 같은 binary target으로 합친다. 미선택 마스크는 이 target에 대한 의미를 판단하지 않는다. 불필요한 영역을 배경으로 자동 채우지 않는다. 선택 밖은 **65535 unknown**, 명시적 제외는 65533, uncertain은 65534다. `valid.png`를 반드시 함께 사용한다. 부분 GT는 유효 음성 배경이 부족하므로 완전한 지도학습 데이터와 동일하지 않다.

마스크를 편집해 새 ID가 만들어지거나 삭제/비활성화되면 scope를 다시 저장해야 한다. 자동으로 다른 후보를 골라 대체하지 않는다. 입력/선택 변경은 검수와 회전·계측을 만료시킨다. 현재는 관련 없는 후보 변경도 보수적으로 만료시킬 수 있다.

## 실제 검증

- Python 회귀 **75개 통과**, 12.021 s. Node UI 회귀 통과.
- 합성 두 이미지: layer 미배정 상태, 특정 mask만 선택해 일괄 GT→회전→확정→계측, 알려진 20/10 nm 값 일치.
- 실제 SAM `19.jpg` crop/회전 5장 재검증. +7° 단일 cell 상대 회전 오차 0.1351°, 3-cell +7° 오차 −0.0228°, −8° 오차 0.0063°. 원래 영상의 고유 기울기를 0° baseline으로 보정한 상대 오차다.
- 그 결과를 복사한 별도 프로젝트에서 **모든 layer 배정을 해제**하고 3-cell의 가운데 cell을 미선택으로 남겨 검사. 회전 5/5, 잠정 계측 5/5, 부분 GT 검사+계측 10/10 완료. ZIP 안 미선택 영역 unknown 보존 확인.
- GUI에서 공개 이미지 43/140의 선택 mask만으로 부분 GT 검사+회전 4/4, 계측 2/2 완료. preset을 다른 이미지에 옮겨도 SAM이 자동 실행되지 않음을 확인.

이 fixture는 반복 복사/합성 표기/알려진 기하 회전으로 만든 기능 시험이다. 실제 독립 촬영 데이터나 전문가 mask GT가 아니다. GUI에서 수행한 검수 확정 역시 검수 버튼과 저장 계약의 테스트이며 재료 정확도 인증이 아니다.

계측 평균은 마스크의 끝부분/구멍/짧은 분리 구간에 민감하다. 19 +7° 단일 cell에서 중앙값은 약 165.35 nm지만 전체 구간 평균은 약 137.30 nm였다. **회전 성공을 두께 정확도 성공으로 확대 해석하면 안 된다.** 필요한 측정 구간을 지정하고, 후속 개선에서 내부 구간/QC를 더 시험한다.

## 48회 실제 SAM 비교

6개 입력 × 4종 프롬프트 × 2 decoder 경로. 아래 숫자는 **후보 개수**이지 정확도가 아니다.

| 입력 | 이전 single Grid / Sobel / Hybrid / Grid+Sobel | 공식 multi Grid / Sobel / Hybrid / Grid+Sobel |
|---|---|---|
| 43 | 5 / 3 / 7 / 4 | 8 / 5 / 10 / 7 |
| 55 | 3 / 3 / 5 / 4 | 4 / 6 / 9 / 9 |
| 76 | 8 / 2 / 8 / 5 | 8 / 2 / 15 / 8 |
| 140 | 3 / 4 / 3 / 6 | 5 / 6 / 6 / 9 |
| 143 | 8 / 2 / 12 / 6 | 9 / 3 / 14 / 10 |
| 첨부 45° | 2 / 1 / 2 / 2 | 1 / 1 / 3 / 1 |

nominal 16점, 제외 영역 때문에 Grid 실제 14~16점. 모든 실행은 encoder cold, 원본 입력 동일, pred .5/stability .7/nms .8. 기본 UI의 엄격한 .9/.92와 다르다. 소요시간 합 805.97 s, 실행별 15.24~22.13 s. 다른 OCR/19 검증이 일부 병행되어 **속도 순위 비교에는 부적합**하다.

시각 검토상 후보 다양성은 늘었지만 얇은 층을 놓치거나, 문자/삽입 패널/큰 배경을 포함한 후보도 남는다. Grid+feature가 모든 이미지에서 최선이라고 결론내릴 수 없다. 저장된 mask를 실제 필요한 대상으로 골라 검수하는 과정이 필요하다.

## 첨부 45° 실패 재검토

- 확대 OCR로 이전에 confidence 필터에 걸렸던 TiO…3 nm 영역까지 포함하여 6개 영역 제안.
- `5 nm`와 70.01298 px bar 연결, **0.07141533 nm/px**. OCR box가 bar를 품은 경우 유효 문자 높이를 분리하여 해결. 검출 값은 미확정 상태 유지.
- `TaOx ~7 nm` 같은 재료 두께 설명을 scale label로 사용하지 않도록 전체 문자열 형식을 제한.
- SAM W mask는 여전히 잘못된 경계. 기존 0°/잔차 0의 프레임 오판은 막았으나 새 기본 mask 회전 3.22°도 실패다.
- 영상 방향 보조 추정은 **44.1441°**, 수동 두 점 44.6067°와 0.463° 차이. 두 값 모두 전문가 GT에 대한 오차가 아니며, 보조 추정은 lattice/주석 영향을 받을 수 있다.
- 글씨 제외는 원본 파괴/복원이 아니다. 분석 입력은 기존 방식으로 주변 유효 픽셀을 채우고 segmentation/계측에서 제외한다. 근처에 인공 경계가 생길 수 있다.

## 재현·모듈

- `services/scopes.py`: target 저장/검수/부분 label 계약.
- `services/prompt_transfer.py`: preset·pixel-centre 변환·ECC. 최초 비율 늘이기 방식은 실제 19 +7°에서 1.53°로 실패했고, 중심 패딩+중앙 영역+다중 초기값으로 수정해 7.0404°/ECC .8758 확인.
- `algorithms/orientation.py`: Hough와 구조 텐서 방향 제안. `residual_px=null`이며 가짜 0 px 경계 정확도를 만들지 않는다.
- `tools/compare_prompt_modes.py`, `create_19_demo.py`, `validate_selected_scope_batch.py`: 실제 모델·일괄 검증. 새로운 출력 폴더를 지정해야 기존 결과가 보존된다.
- 로컬 증거: `test-output/compare-v220`, `crop19-v220`, `selected-scope-v220`, `attached-review-v220`. Git에는 포함하지 않는다.

## 참조한 1차 자료

[SAM 공식 구현](https://github.com/facebookresearch/segment-anything/blob/main/segment_anything/automatic_mask_generator.py), [SAM 논문](https://arxiv.org/abs/2304.02643), [OpenCV Hough](https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html), [ECC API 계약](https://github.com/opencv/opencv/blob/4.x/modules/video/include/opencv2/video/tracking.hpp), [구조 텐서 문서](https://scikit-image.org/docs/stable/api/skimage.feature.html#skimage.feature.structure_tensor), [EasyOCR 구현](https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/easyocr.py).

## 다음 반복의 우선순위

얇은 층의 공간 분산 프롬프트, 다른 공개/변형 영상의 큰 각도 반례, 실제 전문가 GT 없는 상태에서의 과장 방지, 중앙/내부 계측 구간과 짧은 잘림 구간 QC, GUI에서 현재 분석 scope를 회전/배치 화면에도 더 명확히 표시하는 작업을 검토한다.
