# v2.2.8 검토 — 두께·CD를 함께 보존하고 출력

2026-09-30 KST. 신규 SAM 추론 없이 기존 실제 SAM 출력, 알려진 도형, 별도 테스트 프로젝트로 검증했습니다. 회사 영상·전문가 GT는 없습니다.

## 발견한 문제와 수정

두께를 측정한 뒤 CD를 측정하면 최신 결과가 덮여 ZIP에 CD만 남았습니다. 이제 단일/일괄 모두 **방향별 최신값**을 저장합니다. 같은 방향을 다른 구간에서 다시 실행하면 그 방향은 교체됩니다. 여러 레시피/구간 전체 이력 기능은 아닙니다.

4/5 화면의 `두께·CD 저장 결과 함께 내보내기 (각 방향 최신값)`은 기본 켜짐이며 동기화됩니다. 각각 측정을 실행한 후 출력하세요. 한 방향만 있으면 그 방향만 출력합니다. 화면 표와 `measurement.json`은 마지막 실행 결과, 방향별 JSON과 CSV는 선택된 두 방향을 포함합니다.

입력·스케일·회전이 바뀌어 이전 CD만 만료되면 함께 출력은 차단합니다. 만료 결과를 모르게 섞지 않습니다. 다시 측정하거나 옵션을 끄고 최신 한 방향만 내보낼 수 있습니다. 출력 자체는 revision/Undo/프로젝트 파일을 변경하지 않습니다.

## 정량·저장 검증

| 항목 | 실측 결과 | 해석 |
|---|---|---|
| 알려진 binary 사각형 | 두께20px, CD60px, 각3행 | 합성1nm/px에서 GUI20/60nm. SAM 정확도 아님 |
| 저장 실제 SAM 생성45° 얇은 층, 두께 | 유효410, 평균4.685998px, 중앙4.949747px; 무효14, 교차없음1025 | 생성 참값3px 대비 과대오차가 여전히 큼 |
| 같은 SAM의 CD | 유효5, 평균138.832193px, 중앙4.468396px; 무효4, 교차없음1444 | 분절/다중 교차로 평균이 불안정. 유효 표기만으로 의미 있는 물리 CD라고 볼 수 없음 |
| 합쳐진 CSV | 두께1449 + CD1453 = 2902행 | 유효뿐 아니라 모든 상태를 JSON과 대조 |
| 원본↔회전 좌표 끝점 거리 | 최대 오차3.410605131648481e-13px | 수치 변환 일관성. 경계 위치 정확도 아님 |
| 1→2nm/px 시험 변경 | 두께만 재측정 시 오래된 CD 때문에 HTTP400; CD 재측정 후200 | 시험용 보정값이며 TEM 축척으로 채택하지 않음 |
| 원본 보존 | 원본 PNG9개 hash 동일 | 복사 프로젝트에서만 수행 |

`test-output/dual-axis-v228/results.json`, `both-axes.zip`이 증거입니다. ZIP은 초기1nm/px 결과, 최종 복사 프로젝트의 생성 SAM 영상은 만료 검증 후2nm/px입니다. 구분해서 해석하세요.

## 실제 GUI와 다운로드

서버8890의 별도 `dual-axis-ui-v228` 프로젝트에서 known_rectangle_20x60.png를 선택했습니다. 레이어 미배정 target 집합, GT 없이 확정0° 회전, 생성1nm/px입니다.

1. 구간25~35/간격5로 두께 측정: 평균20.000nm, 유효3.
2. CD로 변경 후 실행: 평균60.000nm, 유효3. 두 방향 모두 현재 입력과 일치 표시.
3. 5화면 함께 출력 off → 4화면 off 유지 → 다시 on 확인.
4. 실제 ZIP 버튼 클릭 후 `Downloads/TEM_results.zip` 6096bytes 저장 확인. CSV에 thickness20.0 3행/cd60.0 3행, 두 방향 JSON, include_gt=false 확인.
5. 브라우저 자동화 download 이벤트 대기는20초 timeout이었으나 실제 파일은07:08:26 KST 저장됐습니다. 이벤트 미수신과 다운로드 실패를 구분했습니다. UI/콘솔 오류 없음, Undo6 유지.

화면 증거는 workspace `evidence-v228/dual-axis-ui-viewport.png`입니다. fullPage 캡처는 레이아웃이 비정상으로 나온 도구 캡처 반례라 증거로 쓰지 않았으며 실제 viewport는 정상입니다.

### 추가 실제 GUI — 두 이미지, 두 방향 일괄

07:22 KST, 같은 별도 프로젝트에서 생성45° SAM 영상과 제어 사각형을 Ctrl+클릭으로2개 선택했습니다. 처음 일반 클릭 두 번은 Windows 선택 규칙에 따라 마지막1개만 선택되어 사각형1장만 실행됐습니다. 화면의 `2개 선택`을 확인한 뒤 다음을 수행했습니다.

- GT·SAM·회전 제안 없이 **계측만**: 시작0/끝자동/간격1로 두께2/2완료 → CD2/2완료. 다른 실제 영상3장은 실행하지 않았습니다.
- 사각형 두께20nm/유효60, CD60nm/유효20. 생성 SAM은 시험2nm/px라 두께9.371997nm/유효410, CD277.664386nm/유효5이며 불안정한 CD 반례는 그대로입니다.
- 실제 `대상 이미지 결과 ZIP` 클릭, Downloads/TEM_batch_results.zip797312bytes07:22:33저장. CSV는 사각형두께80/CD60 + SAM두께1449/CD1453 = **3042행**. 두 이미지 각각 두 방향JSON과 include_gt=false 확인.
- JS오류 없음. export전후Undo11로동일. `evidence-v228/batch-two-images-dual-axis.png`에2/2완료 보존. 이 시험은 프로젝트 크기가 작은2장 배치이며 대용량 안정성 보증은 아닙니다.

## 회귀·수정 위치

- 최초 전체139Python PASS30.305초, 이후 일괄 저장 검증 추가 포함 방향별7테스트 PASS2.749초. 최종 배포 전체검증은 ITERATION 기록을 참조하세요.
- Node UI5종 PASS: 기본, prompt batch, loading, rotation compare, export axes. 모사 DOM 검증이며 위 실제 브라우저 검증과 구분합니다.
- Desktop 최종 전체 **140Python PASS27.944초 / Node5종 PASS / pip check PASS**, source manifest167개. httpx testclient deprecation 경고는 기록하고 의존성을 무작정 교체하지 않았습니다.
- 07:28 KST 마감 안전 검증: 부분GT+두방향 출력의 unknown·상태불변, 잘못된 두번째 이미지 전체거절, busy HTTP409 테스트2개 추가. **Desktop 최종142Python PASS29.034초 / Node5종 PASS / pip check PASS**. 애플리케이션 코드는 dfda5d4와 동일하고 테스트·문서만 보강했습니다. 앞140개 기록은 이전 실행 이력입니다.
- 저장·호환: services/measurement.py, routes/workflow.py, storage.py.
- 읽기 전용 출력: v2_api.py. UI: scopes.js, metrology.js, index.html, workflow.js.
- tests/test_measurement_axes.py, tests/ui_export_axes.cjs, tools/validate_dual_axis_export.py.
- 모델/영상/결과ZIP/개인경로의 원시 데이터는 GitHub에 올리지 않습니다.

남은 제한: 자동 물질 식별, 회사 정확도, 얇은 층 경계 편향, 곡면 법선 두께, 여러 구간/객체별 측정 레시피 이력은 별도 개발·검증 대상입니다.
