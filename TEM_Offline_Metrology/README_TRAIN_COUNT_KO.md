# Train Count Benchmark 실행 패키지

기존 업로드에는 노트북만 있었으며, 이번 보완에 실행용 temflow 코드와 설치 노트북을 추가했습니다.
13번은 학습 이미지 수 0 / 5 / 10 / 전체를 비교합니다. DINO는 필요하지 않습니다.

## 준비 순서

1. Ds14 저장소의 Code → Download ZIP으로 받거나 git clone합니다. 노트북 한 파일만 받지 마세요.
2. TEM_Offline_Metrology/notebooks/00_train_count_setup.ipynb를 실행합니다.
3. 인터넷 연결 PC에서 prepare_training_assets.py를 실행하면 공식 SAM 소스의 고정 revision과 SAM2.1 Large 가중치를 준비합니다.
4. 회사로는 준비된 TEM_Offline_Metrology 폴더 전체를 복사합니다. Python 패키지/CUDA는 별도로 준비해야 합니다.
5. 회사 서버의 PyTorch/torchvision CUDA 조합을 유지하고 requirements.txt의 의존성을 사내 미러 또는 승인된 오프라인 wheel에서 설치합니다.
6. 13_train_count_benchmark.ipynb의 ROOT, DATA_ROOT, 클래스 ID를 수정해 실행합니다.

```text
TEM_Offline_Metrology/
  notebooks/00_train_count_setup.ipynb
  notebooks/13_train_count_benchmark.ipynb
  temflow/                 # 실행 코드
  vendor/sam2/             # 준비 스크립트로 다운로드
  weights/sam2.1_hiera_large.pt  # 준비 스크립트로 다운로드
  requirements.txt
```

온라인 준비:
```bash
python prepare_training_assets.py
```
오프라인 파일 검사:
```bash
python prepare_training_assets.py --check-only
```

공식 소스: https://github.com/facebookresearch/sam2

고정 revision: 2b90b9f5ceec907a1c18123530e92e794ad901a4

가중치: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt

가중치 SHA256: 2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318

SAM 코드/가중치의 라이선스는 공식 Apache-2.0이며 다운로드 시 vendor/SAM2_LICENSE를 함께 보관합니다.
SAM 코드와 약 898MB 가중치는 이 GitHub 폴더에 직접 포함되지 않으며 준비 스크립트가 다운로드합니다.

## 데이터

DATA_ROOT 아래 train/images, train/gt, validation/images, validation/gt, test/images, test/gt를 준비합니다.
원본과 GT는 확장자를 제외한 파일명이 같아야 합니다. GT 클래스 매핑은 13번 설정 셀에서 지정합니다.
데이터를 자동 분할하지 않으며 입력 파일은 변경하지 않습니다.

## 결과와 검증 범위

Validation macro IoU가 가장 좋은 가중치를 학습 종료 시 best_decoder.pt에 저장하고 test를 평가합니다.
Optimizer/RNG를 저장하는 중단 재개용 체크포인트는 아닙니다. 0장 기준선 및 학습 결과를 같은 test prompt로 비교합니다.
현재 코드는 공식 SAM 모듈을 사용하는 자체 학습 루프이며 공식 Trainer는 아닙니다.
코드/데이터 처리의 로컬 검사는 수행했으나 회사 GPU 환경에서의 전체 학습은 미검증입니다.
