# 사용·개발·재검증

## 작업 순서

1. 이미지들을 업로드합니다.
2. 자동 문자·바 검출 결과를 확인한 뒤 제외 영역을 적용하고 스케일을 확정합니다. 실패하면 기존 수동 박스·바 끝점 편집을 사용합니다.
3. SAM 모델을 로드하고 Grid/점/box로 마스크를 생성합니다.
4. Ctrl/Shift로 마스크를 선택하여 레이어에 넣습니다. 여러 마스크가 한 레이어에 속할 수 있습니다.
5. **3 경계·GT를 거치지 않고 4 회전·계측으로 이동할 수 있습니다.** 회전 기준 레이어/경계 구간을 지정하고 회전을 제안·확정합니다.
6. 회전 좌표계의 측정 레이어·방향·구간·간격을 정한 뒤 두께/CD를 계산합니다.
7. 회전·계측 ZIP을 저장합니다. 미검수 마스크 결과는 `provisional_unreviewed_masks`로 표시되며 GT로 내보내지 않습니다.

선택 작업: 정확한 경계나 GT가 필요할 때 레이어 인접 순서·충돌 검사 → Gradient+DP 보정 → 마스크 검수 → GT 내보내기를 사용합니다.
기본 최대 이동은 8 px, 자동 틈 채우기는 0 px입니다. 필요 없는 후보는 미지정으로 유지합니다.
기존 고정 위치 템플릿은 기본 꺼짐이며 자동 OCR 박스와 분리되어 있습니다. 다시 켜면 기존 저장 영역이 추가로 활성화되고 관련 결과는 재계산해야 합니다.

부분 경계 보정은 상단 입력 방식의 ROI 도구로 box를 그린 뒤 `캔버스 ROI 구간만 보정`을 사용합니다.
기존 후보 A/B 보정 화면의 고정점·부분 폭/극성 옵션도 유지됩니다.
자동 경계는 레이어 합집합에서 찾되 결과를 원래 객체별 가장 가까운 마스크에 분배하여 instance 정보를 보존합니다.
비인접 충돌·큰 겹침·연결 구조 변화는 수동 검토로 남깁니다.

## 일괄 처리

`5 일괄 처리`에서 선택/전체 이미지와 필요한 단계를 선택합니다.
SAM 뒤 레이어 대응에는 검수한 기준 이미지가 필요합니다. 후보 번호를 클래스 ID로 사용하지 않습니다.
레이어 대응은 정규화 공간 중첩에 의한 제안으로, 촬영 구조가 크게 다르면 수동 배정이 필요합니다.
자동 처리 결과를 모두 GT로 무조건 확정하지 않습니다.
일괄 회전 제안 → 결과 확인 → 대상 회전 확정 → 계측 순서로 나누세요.
진행 중 취소는 현재 추론 단계가 끝난 뒤 반영합니다. 실패 재시도는 실패한 단계부터 진행해 완료된 SAM을 중복 생성하지 않습니다.
설정을 바꾼 뒤 재실행할 때는 필요한 단계만 선택하세요. 모든 설정의 자동 의존성 스케줄링은 하지 않습니다.

## 테스트

프로그램 폴더에서:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe tools/create_validation_data.py --source "C:\images\19.jpg" --output test-output/fixtures
.\.venv\Scripts\python.exe tools/validate_models.py --checkpoint models/sam_vit_b_01ec64.pth --ocr-dir models/easyocr --fixtures test-output/fixtures --output test-output/real-models
.\.venv\Scripts\python.exe run.py --port 8876 --project test-output/fixtures/ui-project
```

실제 19.jpg crop → 회전 → SAM → 레이어 → 회전 보정 테스트:

```powershell
.\.venv\Scripts\python.exe tools/create_19_demo.py --source "C:\images\19.jpg" --checkpoint models/sam_vit_b_01ec64.pth --ocr-dir models/easyocr --output test-output/crop19
.\.venv\Scripts\python.exe run.py --port 8876 --project test-output/crop19/project
```

이 도구는 1-cell/3-cell, 0°/+7°/−8° 예제를 생성하고 실제 로컬 SAM과 OCR을 실행합니다.
3-cell은 동일 19.jpg의 반복 합성본이지 독립 촬영 영상이 아닙니다. 문구·바는 합성 시험 메타데이터입니다.
GT/경계 보정 없이 회전각의 상대 오차(1° 이내)를 검사하고 `validation.json`에 실제 결과를 기록합니다.
한 마스크는 중앙 경계 구간, 여러 마스크는 각 마스크 위쪽 경계 대표점을 사용합니다.
입력/출력 이미지는 GitHub에 업로드하지 않습니다.

이미 존재하는 검증 프로젝트에는 생성 도구를 다시 덮어쓰지 않습니다. 새 출력 폴더를 지정하세요.
합성 프로젝트는 마스크와 축척을 미확정 상태로 시작합니다. 실제 UI에서 검수·확정하는 흐름을 테스트합니다.
19.jpg 변형본은 동작 검증용이며 정답 경계가 아닙니다. 절대 수치 검증은 정답을 수식으로 만든 합성 층으로 합니다.

화면 확인: Ctrl/Shift 선택, 레이어 드래그, 마스크 삭제/Undo, 이미지 삭제/복원,
OCR 적용, 회전 제안/확정, 두께/CD, ZIP, 새로고침, 일괄 취소/부분 실패/재시도를 확인합니다.
기존 `tests/ui_regression.cjs`는 모사 DOM 테스트입니다. 실제 브라우저 확인과 구분하세요.

v2.2.3 프롬프트 검수 gate 모사 테스트는 `node tests/ui_prompt_batch.cjs`입니다. 별도 Node 패키지는 필요 없습니다.
`tools/validate_prompt_reuse.py --project <기존 검증 프로젝트> --checkpoint <pth> --output <새 폴더> --methods normalized ecc ecc_masked`는
실제 모델을 실행합니다. 출력 폴더를 덮어쓰지 않으며, 기존 SAM와의 oracle IoU는 전문가 GT 정확도가 아닙니다.
`tools/validate_transfer_geometry.py --project <19 crop 프로젝트> --output <새 JSON>`은 알려진 생성 변환의 좌표를 비교합니다.
실제 GUI에서는 미검수 실행 차단 → 미리보기 → 확인 → SAM만 → 기존 후보 보존/레이어 미배정까지 확인하세요.

## 수정 시 주의

v2.2.6 사전정렬 회귀: `python -B -m unittest discover -s tests -p test_roi_alignment.py`.
`node tests/ui_metrology_loading.cjs`로 비교 이미지 실패/timeout/늦은 완료를 검사합니다. 실제 브라우저 영상 표시 검증도 필요합니다.
`tools/compare_oriented_roi.py --source <roi-compare 결과폴더> --checkpoint <pth> --output <새 폴더>`는 실제 SAM 비교입니다.
`tools/validate_oriented_roi_api.py --source <roi-compare 결과폴더> --experiment <oriented-roi 결과폴더> --checkpoint <pth> --output <새 폴더>`는 최종 API와 후보 저장/선택회전까지 실행합니다.
원본을 보존하며 결과폴더는 새 경로를 지정합니다. box여백/점/ROI에 민감하므로 단일 성공 사례만으로 기본값을 자동화하지 마세요.

계측 validity 회귀: `python -B -m unittest discover -s tests -p test_contour_validity.py`.
`tools/validate_contour_validity.py --output <새 JSON> --project <기존 계측 프로젝트>`는 모델 호출 없이 대조군과 저장된 실제 mask를 검사합니다.
진단용 all_true 결과를 프로젝트 GT에 적용하지 않습니다. 원시 길이/좌표가 동일해야 하며 실제 무효 구간은 계속 차단되어야 합니다.
계측 알고리즘 버전 변경 후 GUI에서 이전 결과 만료 → 재측정 → 행 상태/CSV까지 확인하세요.

독립 ROI 회귀는 `python -B -m unittest discover -s tests -p test_roi_domains.py`와 기존 Node UI 테스트에 포함됩니다.
실제 비교는 `tools/compare_roi_prompts.py --attached <첨부 프로젝트> --public <프로파일 프로젝트> --checkpoint <pth> --output <새 폴더>`입니다.
후보별 비교는 `tools/compare_roi_alternatives.py --source <직전 비교 폴더> --checkpoint <pth> --output <새 폴더>`입니다.
계측은 `tools/validate_roi_metrology.py --source <후보별 비교 폴더> --output <새 폴더>`로 실제 SAM 출력과 생성 3px 띠를 비교합니다.
새 학습을 하지 않으며 원본을 읽기만 합니다. 표본 평균 개선을 경계 정확도 개선으로 간주하지 마세요.

- 검수/좌표 규칙 변경 시 `test_metrology.py`, `test_workflow_v21.py`를 함께 확인합니다.
- UI 작업은 테스트용 프로젝트에서 수행합니다. 회사 GT 폴더를 테스트 대상으로 쓰지 않습니다.
- 파일 변경은 새로운 mask ID로 기록합니다. 원본 후보와 연결 정보를 보존합니다.
- 모델·개인 이미지·프로젝트·가상환경·test-output는 `.gitignore`로 제외합니다.
- 상세한 책임 분리는 `ARCHITECTURE_KO.md`, 코드 값은 `DATA_CONTRACT_KO.md`를 참고하세요.
