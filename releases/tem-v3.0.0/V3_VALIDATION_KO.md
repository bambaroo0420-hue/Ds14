# v3.0.0 SAM 2.1 Large — 구현/검증 결과 (2026-10-06)

## 배포 판단

v2를 보존한 별도 v3 소스입니다. **회사 적용 전 검증이 필요한 후보 버전**입니다.
UI/알고리즘 회귀는 통과했으나 이 PC의 메모리 부족으로 Large 전체 자동분할
종단 간 검증은 완료하지 못했습니다. 모든 버튼을 실제 Large로 재시험했다거나
회사 영상 정확도가 향상됐다고 주장하지 않습니다.

## 변경과 유지 범위

|항목|v3 상태|
|---|---|
|SAM 엔진|SAM2ImagePredictor / SAM2AutomaticMaskGenerator, SAM 2.1 Hiera Large 고정|
|모델 설정|Large 경로/auto·CUDA·CPU 유지; SAM1/ABL 가중치는 명시 거부|
|이전 mask 재입력|SAM2 정사각 resize, engine+checkpoint+image context로 logits 격리|
|ROI/회전 ROI/프롬프트 그룹|기존 호출 계약과 좌표 복원 유지|
|Grid/ML/recipe/일괄 처리|기존 준비·실행 로직 유지, SAM 엔진만 교체|
|마스크/레이어/브러시/잠금|기존 UI/API 유지|
|경계/GT/법선/Gradient·DP|기존 알고리즘 유지. SAM 변경이 경계 보정 알고리즘 변경은 아님|
|회전/계측/통계/내보내기|기존 UI/API 유지|
|설치|자체 포함 setup.ipynb, vendored SAM2, 별도 가중치|
|기존 v2|변경하지 않음. 프로젝트 전체 사본에서 v3 시험 권장|

## 실행 결과

- Python 회귀: **280개, 실패 0, 오류 0, skip 0**, 52.279초.
  `test-output/v3-final-regression-serial/all-tests.json` 및 log.
  기존 275개에 v3 모델 제한·가중치 거부·context 격리·실패 시 상태 보존·API 기본값 5개 추가.
- JavaScript: 기존 8개 테스트 스위트 통과 (최종 cache key 수정 후 재실행도 통과).
- Python compileall: tem_analyzer/tools/run.py 문법 검사 통과.
- 실제 브라우저: v3.0.0 헤더, Large 단일 모델 옵션, SAM1 입력 비활성,
  기존 탭/레이어 선택/편집 도구 표시, 별도 프로젝트에 기존 TEM 이미지 업로드 확인.
  Grid 한 변 4 입력 후 버튼을 눌러 16개 점 생성 및 원본 위 시각화 확인.
  브라우저 console error 조회 0건. 이는 모든 버튼의 실제 모델 검사를 의미하지 않습니다.
- 실제 SAM 2.1 **Large** 가중치(898,083,611 bytes), CPU에서 성공한 경로:

|실제 추론|시간(s)|mask 면적(px)|예측 score|
|---|---:|---:|---:|
|점+박스|23.787|147300|0.8712|
|이전 logits 입력, embedding 재사용|0.361|16112|0.8810|
|바이너리 mask seed, embedding 재사용|0.335|16401|0.8361|
|ROI crop 분할/원본 크기 복원|22.345|138757|0.7807|

위 결과는 `output/sam2_cell_transfer/original.png`를 사용한 실행 검사입니다.
이전 mask 시험은 box를 다시 제공하지 않았으므로 면적이 달라집니다. GT 정확도나
객체 보존 점수로 해석하면 안 됩니다. overlay는 `test-output/sam2-large/*.png`에 보관합니다.

## 실패와 조치

1. 처음 모델 로드는 CPU 가중치 복사 중 메모리 부족(RuntimeError).
   mmap + strict assign load로 중복 복사를 줄인 후 위 4경로가 실행됐습니다.
2. 실제 자동 후보 생성 및 회귀 동시 실행에서 OpenBLAS 메모리 오류/프로세스 종료.
   회귀를 순차 실행하여 280개 통과. CPU 자동분할은 points_per_batch=1,
   별도 AMG 사용 전 interactive embedding을 해제하도록 보완했습니다.
3. 마지막 순차 Large 재시험도 완료되지 않고 exit 1 종료(추가 traceback 없음).
   OS 조회 당시 여유 물리 메모리 약 1.69 GiB / 전체 약 15.93 GiB,
   가상 메모리 여유 약 1.79 GiB였습니다. 마지막 종료 원인을 단정하지 않습니다.
   **배치 크기 보완 이후 실제 AMG 성공은 미검증**입니다. 다른 사용자 프로세스는 종료하지 않았습니다.

## 사용 전 필수 작업

1. 여유 RAM/VRAM을 확보한 회사 GPU 환경에서 README 순서로 설치.
2. 사본 프로젝트에서 모델 로드 → 수동 점/box → ROI → 기존 mask 재분할.
3. Grid 2~4의 작은 값으로 자동 후보 생성, ML 추가점/수동 그룹/회전 ROI 실행.
4. recipe 2~3장 적용 및 레이어 배정/잠금/Undo, 경계 미리보기/적용 확인.
5. 기준 층 회전/두께·CD/CSV·ZIP 출력의 실제 위치와 숫자 검수.
6. 전문가 GT로 SAM1 대비 경계거리·두께오차 비교. 모델 score를 정확도로 간주하지 않기.

GPU 실제 추론, 대규모 일괄 실행, 실제 회사 이미지 정확도, SAM1 학습 모델의
SAM2 재학습은 이번 검증 완료 범위가 아닙니다. v3에는 영상 추적/전파 기능이 없습니다.

## 재현

```text
python tools/check_gap_bridge.py --all --output v3-final-regression-serial
python tools/validate_sam2_large.py --checkpoint models/sam2.1_hiera_large.pt --image YOUR_IMAGE.png
python -X utf8 run.py --port 8766 --project projects/v3_test
```

로컬 검증은 기존 v2 가상환경 Python 3.13 / torch 2.14.0+cpu와 기존 로컬
hydra/iopath 의존성을 사용했습니다. 패키지/모델 다운로드 및 GitHub 업로드는 하지 않았습니다.

