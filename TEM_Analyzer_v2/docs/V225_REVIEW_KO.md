# v2.2.5 — 기울어진 얇은 마스크의 계측 유효성 수정

2026-09-30 KST. v2.2.4의 얇은 층 `invalid_region` 원인을 분리한 반복 검토입니다.
새 모델 추론/학습/설치는 없습니다. 기존 실제 SAM 출력과 수식으로 생성한 binary 마스크를 사용했습니다.
회사 이미지와 전문가 GT가 없으므로 회사 계측 정확도를 인증하지 않습니다.

## 수정한 오류와 사용법

기존 길이는 원본 binary mask의 보간된 0.5 윤곽선을 회전해서 계산했지만, 유효성은 선분 위 약 0.5 px 간격의 점을 가장 가까운 픽셀로 반올림해서 검사했습니다.
이 두 기하 표현은 대각선·오목한 모서리에서 다릅니다. 선택 마스크 전체가 유효해도 일부 측정을 무효로 처리했고, 반대로 샘플 사이의 아주 짧은 무효 구간을 놓칠 수도 있었습니다.

현재는 `mask & valid`도 동일한 보간 윤곽선으로 변환하고, 측정 선분 전체가 유효 교차 구간으로 덮이는지 확인합니다. 허용 오차는 1e-7 px입니다.
validity 팽창, unknown 채우기, 작은 측정값 자동 삭제, SAM 마스크/회전행렬/길이 변경은 하지 않습니다.
각 행의 `valid_coverage_px`와 `invalid_coverage_px`를 JSON/CSV에 추가하고 UI에 무효 구간 길이를 표시합니다.

기존 계측은 알고리즘 버전 변경으로 **만료 → 다시 측정** 안내가 나옵니다. 입력이 그대로라면 회전 재확정은 필요 없습니다.
GT 없이 계측하는 기능은 그대로이고, 부분 GT를 요청할 때만 선택 집합 검수가 필요합니다.

## 72개 합성 대조시험

폭 1/3/10/20 px × 각도 0/7/30/45/−30/89° × 유효성 3종. 각 조건에서 중앙 41개 좌표를 측정했습니다.
가느다란 띠가 끊어져 교차 없는 위치도 있으므로 유효+무효 합은 984가 아니라 977개입니다.
`all_true`는 오류 원인 분리용 대조이며 실제 프로젝트에 저장하지 않았습니다.

| 유효성 조건 | 이전 유효 / 무효 | 수정 후 유효 / 무효 | 해석 |
|---|---:|---:|---|
| 선택 마스크 전체 유효 | 699 / 278 | 977 / 0 | 잘못된 무효 판정 제거 |
| 전체 영상 true, 진단 전용 | 977 / 0 | 977 / 0 | 같은 마스크의 기하 대조 |
| 명시적 4 px 무효 세로 띠 추가 | 454 / 523 | 637 / 340 | 잘못된 모서리 제외는 제거, 실제 무효는 보존 |

72조건 모두 원시 길이·원본 역변환 끝점이 수정 전후 동일했습니다. 추가 단위시험에서는 단일 무효 픽셀을 스치는 **0.02 px 무효 선분도 차단**했습니다.
완전 무효, 구멍/분리 객체, 두께/CD 방향도 검사했습니다.
단회 실행 시간은 이전 11.832초 / 이후 12.156초(기존 실제 SAM 3장 재계측 포함)입니다. 체계적 성능 벤치마크는 아닙니다.

## 기존 실제 SAM 출력 3장 — 선택 mask만 일괄 처리

v2.2.4 실제 추론 후보 3번을 그대로 사용했습니다. 영상/후보는 복사한 새 프로젝트에서만 처리했습니다.
0/30/45° 합성 3 px 띠, 1 nm/px는 생성 시험용 축척이지 공개 TEM 축척 추정이 아닙니다.

| 입력 각도 | 회전 추정 각도 | 이전 → 현재 유효 수 | 이전 → 현재 무효 수 | 이전 → 현재 평균(px) |
|---|---:|---:|---:|---:|
| 0° | 0.00000° | 97 → 97 | 3 → 3 | 4.0000 → 4.0000 |
| 30° | 29.92407° | 62 → 143 | 88 → 7 | 3.3321 → 3.5298 |
| 45° | 44.61723° | 72 → 159 | 91 → 4 | 4.1612 → 4.2385 |

모든 원시 길이와 교차 없음 행은 그대로입니다. 통계 표본 구성만 바뀌었으므로 평균 변화가 정확도 향상을 뜻하지 않습니다.
생성 두께 3 px와 여전히 차이가 큽니다. SAM 과대 분할·분절과 binary rasterization 불확실성은 해결되지 않았습니다.
작은 값도 자동 삭제하지 않았고 crop 끝 보호도 유지했습니다.

API 실제 구동: 3장 회전 3/3 → 회전 확인 → GT 없는 잠정 계측 3/3 → 선택 집합 검수 → 부분 GT+계측 6/6 → ZIP 검증.
모든 후보는 레이어 미배정, 미선택 후보 보존. crop 보호 81/142/69 px는 부분 GT에서 모두 unknown(65535)임을 확인했습니다.
이 도구의 검수 호출은 파이프라인 시험이며 전문가 GT 판정이 아닙니다.

## 재현과 증거

```powershell
python -B -m unittest discover -s tests
python -B tools/validate_contour_validity.py --output test-output/new-contour-check.json --project test-output/roi-metrology-v224-final/project
python -B tools/validate_roi_metrology.py --source test-output/roi-alternatives-v224 --output test-output/new-roi-metrology
```

기존 출력 경로는 덮어쓰지 않습니다. 테스트 영상/프로젝트는 로컬 증거이며 저장소에 포함하지 않습니다.

- `test-output/contour-validity-v225/before.json`, `after.json`: 수정 전후 72조건과 기존 SAM 출력 재계측.
- `test-output/roi-metrology-v225/results.json`, `partial-results.zip`: 3장 일괄 검증, 기존 v224 출력은 보존.
- `test-output/contour-ui-v225`: 별도 실제 GUI 시험 프로젝트, 기존 `roi-ui-v224` 보존.
- GUI 단일 이미지에서 기존 결과 만료 표시 → GT 없이 재계측: mask 22만 사용, 보정각 −29.95847°, 유효 19→38, 무효 21→2, 교차 없음125.
  평균 3.5496→3.7634 nm, 무효 구간 2.4504/3.8151 px 표시. 1 nm/px는 생성 축척입니다.
- GUI에서 미검수 부분 GT 실패 → 검수 확인 대화상자 → 실패 단계 재시도 → 부분 GT+계측 2/2 완료. 레이어 배정 없음, 브라우저 JS 오류 없음.
- 전체 Python 121 tests PASS(25.218초, 기존 상속 테스트 중복 포함), 보강된 CSV 포함 scope 7 tests PASS(1.905초), 기존/프롬프트 Node UI 회귀 PASS. Desktop 최종 재검증은 진행 기록 참조.
- Desktop 최종: Python121 PASS24.520초, Node 기존/프롬프트 2종 PASS, pip check PASS, source manifest150개.
- `evidence-v225/rotation-and-validity.png`: 원본과 수평 보정 비교. 이번에는 양쪽 영상 정상 표시. v224의 일시적 검은 미리보기 원인은 확정하지 않았습니다.

## 수정 위치와 한계

- `algorithms/metrology.py`: 같은 윤곽선의 연속 교차구간 coverage. 길이/원본 좌표 변환은 기존과 동일.
- `services/measurement.py`: 계측 hash `contour_validity_v3`, 이전 결과 재사용 차단.
- `routes/workflow.py`, `web/modules/metrology.js`: CSV/행별 무효 길이 표시.
- `tests/test_contour_validity.py`, `tests/test_scopes.py`: 5개 새 시험 + CSV 계약 보완.
- `tools/validate_contour_validity.py`: SAM 오류와 유효성 오류 분리.

얇은 층의 실제 물질 경계 정확도, 첨부45°의 TaOx/TiOxNy SAM 분리 실패, 색선/화살표 영향은 남아 있습니다.
마스크 외곽 보간은 pixel-center 모델의 기하 계약이지 원자 수준의 subpixel 정답을 보장하지 않습니다.
방향이 맞거나 SAM confidence가 높아도 올바른 물질 GT가 된 것은 아닙니다.

## 조사한 공식 기술 자료

픽셀 중심과 0.5 등고선의 선형 보간, 대각선 모호성 설명을 참고해 반올림 픽셀 판정과의 차이를 분리했습니다. 구현 검증은 위 대조시험으로 수행했습니다.
[scikit-image find_contours 공식 문서](https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.find_contours),
[ContourPy 알고리즘 설명](https://contourpy.readthedocs.io/en/stable/description.html).
실제 코드의 contour 추출은 기존 Matplotlib 경로를 유지하며 새 의존성을 추가하지 않았습니다.
