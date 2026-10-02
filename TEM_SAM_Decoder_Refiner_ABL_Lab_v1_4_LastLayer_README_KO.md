# ABL v1.4 마지막 출력층 미세조정 추가판

원본 v1.4를 바탕으로 만든 로컬 수정판입니다. 기존 4개 실험을 유지하고 2개를 추가했습니다.

## 실행

1. 기존처럼 설치하고 00번 준비 노트북으로 `config.local.json`, 데이터, 원본 SAM checkpoint를 준비합니다.
2. `notebooks/01b_train_last_layer.ipynb`를 실행합니다. 첫 셀의 프로젝트 경로를 확인합니다.
3. `runs/last_layer_01`은 새 실행마다 새 이름으로 바꿉니다.
4. `decoder_last_noabl`과 `decoder_last_abl`이 각각 원본 SAM에서 독립적으로 시작합니다.
5. 노트북의 그래프와 val 고정 grid 비교를 확인한 후 선택한 best.pt를 export합니다.

`sam_checkpoint`에는 원본 SAM 가중치를 지정합니다. 이전에 망가진 adaptation 가중치를 넣지 않습니다.
기존 01_train.ipynb/train_all(cfg)의 기본 4개 실험 및 Dice 선택 방식은 유지됩니다.
새 방식은 `train_all(cfg, ['decoder_last_noabl','decoder_last_abl'])`로 명시적으로 선택합니다.

## 실제 학습 범위

`sam.mask_decoder.output_hypernetworks_mlps[0].layers[-1]`의 weight와 bias만 학습합니다.
단일 마스크 출력(`multimask_output=False`)에 쓰이는 MLP의 마지막 Linear입니다.
SAM의 표준 decoder 차원에서는 256×32+32 = 8,224개 파라미터입니다.
Transformer, 업스케일링, 나머지 MLP, 이미지/프롬프트 encoder, IoU head는 고정됩니다.
학습 시작 시 `trainable_parameters.json`에 실제 이름과 개수를 저장합니다.

기본 학습률 1e-6(기존 decoder 1e-5의 1/10), weight decay 0입니다.
ABL 옵션의 가중치는 0.01(기존 0.1의 1/10)이며 기본 2 epoch warmup 이후 적용합니다.
새 노트북 기본값은 최대 15 epoch / patience 4입니다. 이 수치는 시작 설정이며 성능 보장이 아닙니다.
학습 범위가 좁아 원래 못 찾던 경계의 개선 폭도 제한될 수 있습니다.

## 지표를 읽는 방법

매 epoch 같은 검증 이미지와 같은 GT 중심점 prompt로 계산합니다. 이미지별 영역 평균을 구한 뒤 이미지 평균을 냅니다.

| 지표 | 의미 | 좋은 방향 |
|---|---|---|
| val_boundary_f1 | 예측/정답 경계의 일치. 기본 허용거리 2 원본 이미지 pixel | 증가 |
| val_dice / val_iou | 정답 영역과 예측 영역의 겹침 | 증가 |
| val_mean_boundary_distance_px | 양방향 최근접 경계 거리의 평균 | 감소 |
| delta_boundary_f1 / delta_dice | epoch 0 원본 대비 변화, 0.01은 1 percentage point | 양수 |
| regressed_good_targets | 원본에서 잘 찾던 영역 중 Dice 또는 Boundary F1이 허용치보다 하락한 영역 수 | 0 |
| total, bce, dice_loss, abl | 학습 데이터의 최적화 손실 | 감소는 참고만 |

경계를 놓치면 거리 값은 null입니다. 거리 평균에서 누락되므로 거리만 보면 좋아 보일 수 있습니다.
`boundary_distance_valid_targets / validation_targets`, Boundary F1, 누락 영역을 함께 봅니다.
Boundary F1도 허용거리 안의 미세한 차이에는 둔감하므로 overlay로 확인합니다.
확대 배율/픽셀 크기가 다른 영상의 2px는 같은 물리 거리라는 뜻이 아닙니다.
ABL warmup 이후 loss의 정의가 바뀌므로 total loss의 단순 전후 비교는 부적절합니다.

## 새 실험의 best.pt 선택

학습 전 원본을 epoch 0으로 평가하고 best.pt에 먼저 보존합니다.
아래 조건을 모두 만족할 때만 best.pt를 교체합니다.

- Boundary F1이 지금까지 채택된 best보다 0.001 초과 개선.
- 전체 평균 Dice가 원본 대비 0.005 넘게 감소하지 않음.
- 원본 Dice ≥ 0.8 이면서 Boundary F1 ≥ 0.8인 검증 영역 각각에서 두 지표 중 어느 것도 0.02 넘게 감소하지 않음.
- ABL 실험은 ABL 적용 이후 epoch만 후보로 인정.

이는 픽셀 단위 경계 보존 손실이 아니라 검증 결과로 모델을 채택/거절하는 기준입니다.
원본에서 잘 찾던 영역이 검증 세트에 하나도 없으면 그 부분의 보존 검증은 불가능하다고 출력합니다.
원래 잘 찾던 이미지와 어려운 이미지를 모두 검증에 포함해야 합니다.
원본 이미지/시편이 같은 crop은 같은 group으로 묶어 train/val에 섞이지 않게 합니다.

조건을 만족한 epoch가 없으면 `selection.json`의 `baseline_fallback=true`, `epoch=0`이고 best.pt는 원본 decoder입니다.
`last.pt`는 마지막 학습 상태로, 개선/보존 조건을 통과했다는 의미가 아닙니다.
평균 지표 개선은 모든 영역 보존을 보장하지 않습니다. 여기서 보호하는 범위는 설정된 원본 우수 검증 영역뿐입니다.

## 실제 자동분할 확인

중심점 지표는 정답에서 얻은 prompt를 쓰는 진단이므로 자동분할 성능과 다릅니다.
새 노트북의 `compare_all(..., split='val')`은 고정 grid로 원본과 best를 비교합니다.

- region_recall: 실제 영역 중 찾은 비율 — 누락 확인.
- region_precision: 찾은 후보 중 정답과 매칭된 비율 — 과검출 확인.
- image_mean_boundary_f1_all_gt: 누락 GT는 0으로 포함한 경계 점수.
- evaluation/val 아래 grid_predictions.png와 diagnostic_region_*_whiteGT.png: 예측/GT 경계 확인.

기존과 같은 threshold/grid/NMS로 비교하세요. 반복해서 val로 선택한 뒤 별도 test가 있으면 마지막에 한 번 평가합니다.
IoU head는 학습하지 않으므로 모델이 출력하는 IoU 예상 점수를 실제 정확도 지표로 쓰지 않습니다.

## 호환성과 검증 범위

체크포인트는 기존처럼 `method='decoder'`, 전체 decoder state와 원본 SAM hash를 저장합니다.
기존 Predictor/export 형식을 유지하며 학습 범위만 config.decoder_scope에 기록합니다.
CPU 축소 SAM 테스트는 동결/역전파/원본 fallback/체크포인트 재로딩 검증용입니다.
사용자의 TEM 데이터에서 실제 성능이 개선됐다는 검증은 별도 학습 후 필요합니다.

