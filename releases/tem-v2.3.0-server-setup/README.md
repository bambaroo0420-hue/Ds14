# TEM Analyzer v2.3.0 — 서버 setup 포함 ZIP

[전체 소스 ZIP 다운로드](https://github.com/bambaroo0420-hue/Ds14/raw/refs/heads/codex/tem-v2-batch-metrology/releases/tem-v2.3.0-server-setup/TEM_Analyzer_v2_v2.3.0_server_setup.zip)

기존 v2.3.0에 `setup.ipynb` 및 서버 설치/실행 지원을 추가한 패키지입니다. 기존 Windows ZIP은 교체하지 않았습니다. 모델 가중치, 회사 이미지, 개인 프로젝트, 가상환경은 포함하지 않습니다.

## 사용 순서

1. ZIP 전체를 회사 서버의 쓰기 가능한 작업 폴더에 압축 해제합니다.
2. ABL 1.4의 `weights/sam_vit_h_4b8939.pth`를 `TEM_Analyzer_v2/models/sam_vit_h_4b8939.pth`로 복사합니다. 이미 서버에 있으면 노트북에 절대 경로를 지정해도 됩니다.
3. 학습 Decoder/Refiner를 사용할 때만 export한 `adaptation.pt`를 `models/abl14/decoder_abl/adaptation.pt` 등 실험별 폴더에 넣고 노트북의 `ADAPTATION`을 지정합니다. 기본 SAM은 학습 당시와 동일해야 합니다.
4. OCR 사용 시 `models/easyocr/`에 `craft_mlt_25k.pth`, `english_g2.pth`를 넣습니다. 이 두 파일은 ABL에는 없으므로 이전 Analyzer에서 복사하거나 공식 링크로 준비합니다.
5. Python 3.11 이상/64-bit의 기존 CUDA 커널로 루트 `setup.ipynb`를 엽니다. 최초 보충 설치만 `INSTALL_PACKAGES=True`, 웹 서버 실행은 `START_SERVER=True`로 설정합니다. 설치·검사·시작 셀을 순서대로 실행합니다.
6. 회사가 허용한 SSH/VS Code **Private** 포트 전달로 웹 UI에 접속합니다. 다음부터 패키지 설치는 생략합니다.

노트북만 다운로드하면 지원 스크립트와 앱 소스가 없어 실행되지 않습니다. ABL의 `.venv`, `temlab`, `vendor`, requirements 또는 config를 Analyzer에 덮어쓰지 마세요. 같은 프로젝트를 두 서버에서 동시에 편집하지 마세요.

## 검사 및 한계

- Python 회귀/설치 안전장치 테스트 213개 통과.
- ZIP을 다시 풀어 노트북 코드 8개 셀을 CPU 설정으로 실행: 실제 ViT-B SAM 및 EasyOCR, 서버 시작/모델 로드, HTML/JS/CSS/API 접속, 재실행 시 서버 재사용, 종료 후 포트 해제 확인.
- 회사 CUDA 서버/학습 checkpoint/회사 이미지 정확도는 별도 검증이 필요합니다. 실제 CUDA 설치는 기존 환경을 바꾸지 않고 서버에서 확인하도록 설계했습니다. CUDA 필수 모드는 CUDA가 없으면 중단합니다.
- 현재 OCR, Gradient/DP, 회전·계측은 CPU 처리입니다. SAM·Decoder/Refiner만 GPU 가속 대상이며 배속을 보장하지 않습니다.
- 일반 JupyterHub `/user/.../proxy/` 경로는 현재 UI의 루트 절대 경로 때문에 추가 대응이 필요합니다. SSH 없이 프록시만 가능한 환경에서는 바로 실행 가능한 것으로 간주하지 마세요.
- 기존 v2.3.0의 미완료 기능을 모두 구현한 새 기능판은 아닙니다.

## 파일과 검증값

- [노트북 소스](../../TEM_Analyzer_v2/setup.ipynb)
- [설치·파일 배치·서버 접속 안내](../../TEM_Analyzer_v2/docs/INSTALL_KO.md)
- [검증 메타데이터](TEM_Analyzer_v2_v2.3.0_server_setup.verification.json)
- [SHA256](TEM_Analyzer_v2_v2.3.0_server_setup.sha256)

ZIP: `TEM_Analyzer_v2_v2.3.0_server_setup.zip` (599,559 bytes, 212 files)

SHA256: `f931b31d9553eed017415929951de17893707c7c03e88532443eda82d17e50dd`
