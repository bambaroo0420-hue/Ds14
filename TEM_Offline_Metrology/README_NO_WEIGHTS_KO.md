# 가중치 제외 학습 벤치마크

이 ZIP에는 SAM2.1 소스, 학습 노트북 00/13, temflow 코드와 requirements가 포함됩니다.
가중치, 회사 이미지, GT, Python/CUDA 설치 패키지는 포함하지 않습니다.

1. ZIP을 압축 해제합니다.
2. 공식 SAM2.1 Large 가중치를 별도로 다운로드합니다.
   https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
3. 파일 이름을 유지해 다음 위치에 저장합니다.
   TEM_Offline_Metrology/weights/sam2.1_hiera_large.pt
4. 회사 GPU에 맞는 PyTorch/torchvision 및 requirements.txt 의존성을 준비합니다.
5. notebooks/00_train_count_setup.ipynb에서 ROOT를 수정하고 DOWNLOAD_ASSETS=False로 검사합니다.
6. notebooks/13_train_count_benchmark.ipynb에서 데이터 폴더와 클래스 ID를 지정해 실행합니다.

DINO 가중치는 이 학습 벤치마크에 필요하지 않습니다.
가중치 SHA256: 2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318
