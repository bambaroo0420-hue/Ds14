# 좌표·GT·검수 계약

- 점: 원본 `(x,y)` 픽셀 중심 좌표. 배열: `[y,x]`.
- 정규화 ROI: `[x0,y0,x1,y1]`, 0~1. 마스크 배열의 구간 끝은 제외합니다.
- 픽셀 `(x,y)`의 셀 경계는 `x±0.5`, `y±0.5`입니다.
- 스케일바는 점 두 개의 거리로 계산하며, 검출 바의 실제 점유 픽셀 폭을 사용합니다.
- `nm_per_px = length_nm / bar_pixel_length`. 배율 표기만으로 축척을 계산하지 않습니다.
- 회전은 영상 좌표에서 시계방향 양의 각도. 3×3 `matrix`는 원본→정렬, `inverse`는 정렬→원본입니다.
- 출력 영상은 확장되어 원본을 자르지 않습니다. 회전 여백은 유효 분석 영역이 아닙니다.
- 확대·비선형 변형은 하지 않으므로 정사각형 픽셀의 nm/pixel은 회전 후에도 같습니다.
- 측정은 회전된 마스크의 0.5 등고선과 측정선의 교차를 사용합니다. 표시용 마스크 재샘플링과 분리합니다.
- 두께: 정렬 영상의 x 위치에서 세로 구간. CD: y 위치에서 가로 구간.
- 구멍과 분리 객체는 개별 구간입니다. 사이의 빈 영역을 길이에 포함하지 않습니다.
- 입력 마스크가 픽셀 격자에서 얻어졌으므로 subpixel 좌표 계산이 물리적 subpixel 정확도를 보장하지는 않습니다.

| GT 값 | 의미 |
|---|---|
| 0 | 사용자가 명시한 배경 |
| 1~65532 | 레이어 ID |
| 65533 | 제외 |
| 65534 | 불확실 또는 충돌 |
| 65535 | 미지정 |

`labels.png`는 uint16. `semantic.png`의 무효 픽셀은 0이므로 **반드시 valid.png를 함께 적용**합니다.
`lab_mask.png`는 모든 무효 영역을 65535로 합칩니다. 회전 레이블은 최근접 보간만 사용합니다.
미지정 후보는 레이어 합성에 포함되지 않습니다. 삭제/배정 해제를 배경 지정으로 간주하지 않습니다.

레이어 배정, 마스크 검수, 스케일 확정, 회전 확정은 각각 별도 동작입니다.
Gradient+DP 적용·레이어 대응으로 생성/변경된 마스크는 검수 전 상태입니다.
겹침이 있는 후보는 검수 확정할 수 없습니다. 알려진 무효 영역은 불확실/제외 주석으로 명시할 수 있습니다.
GT ZIP은 검수된 유효 영역을 출력하며, 미지정 부분이 있어도 부분 GT로 사용할 수 있습니다.

회전은 레이어에 배정된 활성 SAM 마스크 또는 저장한 선택 집합(scope)으로 가능합니다. GT·경계 보정·마스크 검수 확정은 필수가 아닙니다.
계측은 회전·축척을 확인한 뒤 실행합니다. 미검수 마스크를 쓰면 `review_status=provisional_unreviewed_masks`이며 최종 정확도를 보증하지 않습니다.
충돌·제외·불확실 영역을 통과하는 측정은 무효로 남깁니다.

기본 결과 ZIP에는 회전 영상/레이어 레이블/유효 마스크,
`alignment.json`, `measurement.json`, 통합 `measurements.csv`가 있습니다.
`aligned_labels.png`는 레이어 마스크이며 GT라는 뜻이 아닙니다. `export_mode.json`에 이를 명시합니다.
`workflow/export`의 `include_gt=true`를 명시한 경우에만 검수 조건을 검사하고 이미지별 GT ZIP을 추가합니다. 기존 경계·GT 화면의 GT 내보내기도 별도입니다.
JSON에는 변환·축척·측정 위치·원본 역변환 끝점·입력 해시가 포함됩니다.
CSV 무효 측정은 빈 길이와 실패 상태로 기록하고 0 nm로 위장하지 않습니다.

v2.2.5 계측은 mask와 `(mask & valid)`를 동일한 0.5 보간 윤곽선으로 변환합니다.
각 측정 선분 전체의 `valid_coverage_px`/`invalid_coverage_px`를 기록하며 후자가 1e-7 px보다 크면 무효입니다.
교차 없음 행은 coverage 필드가 없고 CSV는 빈칸입니다. 원시 길이/좌표는 무효 행에도 보존합니다.
validity를 팽창시키거나 unknown을 채우지 않습니다. 영상 extent의 pixel-cell 경계와 보간 mask contour는 다른 기하입니다.
계측 hash는 `contour_validity_v3`로 갱신되어 기존 계측이 만료되지만 회전 hash는 바뀌지 않습니다.

v2.2 선택 집합은 `scope_id`와 이미지별 `candidate_ids`로 지정합니다. 레이어 미배정 후보도 가능합니다.
부분 GT의 1은 선택 집합의 binary target 합집합이며 물질 ID가 아닙니다. 미선택 영역은 65535이며 자동 배경으로 바꾸지 않습니다.

v2.2.1 `measurement.config.sampling`은 `mode=all|component_center`, `center_fraction`(0 초과~1),
`single_interval_only`(bool), `reject_frame_endpoints`(bool), `min_length_px`(0 이상)를 받습니다.
기본값은 전체/다중 교차 허용/프레임 허용/최소 0입니다. 중앙 비율은 원본 마스크 4-connectivity 연결 객체의
회전 후 contour x 범위(두께) 또는 y 범위(CD)에 적용됩니다. 입력 start/stop/step 위치는 유지되며 벗어난 행도 출력합니다.
`component_id`는 계산상 연결 객체이지 SAM 후보 ID나 물질 ID가 아닙니다. 512개 초과는 명시적 오류입니다.
같은 객체의 구멍/분기는 `multiple_intervals`이며 다른 객체를 같은 선으로 측정하는 것은 이 플래그가 아닙니다.
프레임 판정은 역변환 끝점이 원본 가장자리 pixel centre 바깥 또는 그 위인 경우입니다.
제외 행의 `length_nm=null`, `raw_length_nm`은 무효/제외된 교차 길이이며 최종 계측으로 쓰면 안 됩니다.
`exclusion_reasons`는 적용한 모든 제외 사유, `status`는 첫 사유, `quality_flags`는 비제외 경고도 포함합니다.
평균·중앙값·표준편차는 status=ok 행만 사용합니다. 어떤 수치 이상값도 자동으로 삭제하지 않습니다.
샘플링 범위를 좁혀 평균이 안정돼도 물리 정확도 입증은 아닙니다. 좁은 층·구멍·의도적 분기를 놓칠 수 있습니다.
알고리즘 버전도 계측 해시에 포함하므로 이전 버전 결과는 재계측해야 합니다.

`preprocessing[image_id].template`은 기존 위치 템플릿, `auto_regions`는 OCR 확정 제외 박스입니다.
프로젝트의 `legacy_templates_enabled` 기본값은 false입니다. 꺼진 템플릿은 표시·SAM 입력·레이블에서 모두 무시됩니다. OCR 박스는 이 스위치와 무관하게 적용됩니다.

v2.2.3 `prompt_transfers[image_id]`는 preset ID, source/target image, 원본 pixel-centre 변환 matrix,
변환된 draft, 방식·상관점수·경고, `input_hash`, `draft_hash`, `review_hash`를 보존합니다.
입력 hash는 preset 전체, 기준·대상 영상 bytes/크기, 양쪽 제외 마스크, 대상 SAM 필터에 연결됩니다.
`superseded_by`가 있거나 hash가 다르면 확정/실행 불가입니다. SAM 후보가 추가된 것만으로 좌표 검토를 만료시키지는 않습니다.
실행 이력과 신규 후보 prompts에는 변환·preset·검수 hash를 기록합니다. 원본·마스크를 재정합 warp하는 기능이 아닙니다.
자동점은 제외/영상 밖이면 경고와 함께 제거, 수동점과 box가 유효 범위를 벗어나면 전체 준비를 거절합니다.
회전된 box는 축 정렬 외접 box이며 다른 물질까지 포함할 수 있으므로 검토해야 합니다.
GT 확정과 프롬프트 확정은 독립적입니다. 프로그램 검증 도구의 자동 확인은 전문가의 물질 판정이 아닙니다.

v2.2.4 `candidate.inference_domains`는 원본 정수 픽셀의 `[x0,y0,x1,y1]` 반열린 ROI 배열입니다.
ROI 밖 결과는 0이나 이를 배경 GT로 해석하지 않습니다. 내부 crop 가장자리 2px 이내 foreground를 잡아 2px dilation한 영역은 unknown이며 EXCLUDED가 우선합니다.
실제 원본 프레임 경계는 별도의 기존 프레임 정책입니다. 자연 끝점도 crop에 가까우면 보수적으로 보호할 수 있고 멀리 떨어진 가짜 끝점은 보장하지 않습니다.
원본 mask는 그대로이며, 부모 편집/복제/브러시/DP의 자식은 기존 도메인을 상속합니다. 밖을 보존하는 전체 부모 ROI edit에는 새 도메인을 추가하지 않습니다.
레이어 합성에서는 보호 영역을 다른 마스크가 덮어도 보수적으로 unknown 유지합니다. 자동 완결성 판정이 아니므로 더 넓은 ROI의 독립 재분할로 재검토하세요.
`mask_choice=-1`은 최고 예측점수, 0/1/2는 기본 SAM 다중 후보이며 학습 single-mask 경로는 0만 지원합니다.
`multimask_scores`는 SAM 예측값이지 실측 IoU가 아닙니다. `prompt_violations`는 입력 점 배열의 0-based index이며 결과가 라벨과 다를 때 기록합니다.
프롬프트 준수 판정은 가까운 pixel centre를 사용합니다. ROI 제한/제외 영역 적용 이후 전문가 정확도 검사를 대체하지 않습니다.
독립 preview의 parent는 null입니다. accept 전 mask 파일/후보 생성 없음, 이미지/제외/전처리/모델이 바뀌면 만료됩니다.

v2.2.6 prompt `align_positive` 기본 false, `box_margin` 0~200px. 양성점 최소2/직선 방향성 검사, parent/seed/ROI없음은 거부합니다.
여백0은 자동box없음; 양수일 때 길이 방향30px와 법선 여백으로 box 생성. 수동box와 동시에 사용하지 못합니다.
`roi_alignment`의 local_to_aligned/aligned_to_local은 원본 ROI 내부좌표 행렬입니다. original_roi에 전역 offset을 보존합니다.
원본 크기 mask로 저장하며 bilinear 확률 복원→모델threshold, support 밖0. 원본 점 위반을 다시 검사하고 aligned logits/context는 저장하지 않습니다.
사전정렬 fit/score/경고는 전문가 GT나 최종 회전 확정의 대체물이 아닙니다. 기존 inference_domains의 unknown 정책을 유지합니다.
