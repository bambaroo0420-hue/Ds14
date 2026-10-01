# TEM Analyzer v2.3.0 — ABL 방식 setup r2

[전체 ZIP 다운로드](https://github.com/bambaroo0420-hue/Ds14/raw/refs/heads/codex/tem-v2-batch-metrology/releases/tem-v2.3.0-server-setup-r2/TEM_Analyzer_v2_v2.3.0_server_setup_r2.zip)

[수정한 setup.ipynb 다운로드](https://raw.githubusercontent.com/bambaroo0420-hue/Ds14/codex/tem-v2-batch-metrology/TEM_Analyzer_v2/setup.ipynb)

## 이번 수정

- ABL 1.4처럼 노트북 셀 안에서 현재 커널의 Python으로 직접 pip 설치합니다.
- 첫 셀과 모든 후속 셀에서 `tools.server_setup` 의존성을 제거했습니다. `pip install tools`를 하지 마세요.
- 기존 v2.3.0 전체 프로그램 폴더가 있으면 **setup.ipynb만 교체**해도 됩니다. 모델 경로 등 노트북 설정은 다시 입력하세요.
- 빈 폴더에서 새로 시작한다면 전체 ZIP을 풀어야 합니다. 실제 앱 소스와 requirements는 필요합니다.
- 최초 `INSTALL_PACKAGES=True`, 이후 False. ABL과 같은 `PIP_INDEX_URL`, `TORCH_INDEX_URL`, `WHEELHOUSE` 설정을 사용합니다. 기존 CUDA torch/torchvision과 주요 수치 패키지 버전은 보존합니다.
- 서버 시작은 `START_SERVER=True`. 설치 완료만으로 UI 서버가 자동 시작되는 것은 아닙니다.
- 모델/프로젝트/이미지는 변경하지 않았으며 ZIP에 포함하지 않습니다.

## 가중치 위치

`TEM_Analyzer_v2` 기준:

- ABL 기본 SAM: `models/sam_vit_h_4b8939.pth`
- 선택적인 학습 bundle: `models/abl14/decoder_abl/adaptation.pt` (학습 당시 동일한 기본 SAM 필요)
- OCR 검출: `models/easyocr/craft_mlt_25k.pth`
- OCR 영어: `models/easyocr/english_g2.pth`

## 검증

- Python 테스트 217개 통과(35.275초).
- tools 폴더가 없는 별도 소스 복사본에서 노트북 코드 8개 셀을 CPU 설정으로 실행했습니다. 실제 ViT-B SAM, OCR, 서버 모델 로드, UI/API 접속, 재실행/종료 후 포트 해제를 확인했습니다.
- 첫 셀은 외부 `tools` 모듈 이름 충돌 상황도 테스트했습니다.
- 설치 셀은 빈 오프라인 wheelhouse와 기존 설치 환경에서 실제 실행하여 패키지 다운로드/교체 없이 pip check까지 통과했습니다. 새 회사 환경 설치를 검증한 것은 아닙니다.
- 회사 CUDA GPU·학습 체크포인트·영상 정확도는 별도 확인이 필요합니다. OCR/경계/계측은 여전히 CPU 처리입니다.
- 원격 UI 접속은 회사가 허용한 SSH/VS Code Private 포트 전달 기준입니다. 일반 JupyterHub `/proxy/` 하위 경로만으로 접속하는 방식은 추가 대응이 필요합니다.

파일: `TEM_Analyzer_v2_v2.3.0_server_setup_r2.zip` (605,419 bytes, 212 files)

SHA256: `ce2f80dd8d03dfd1c0dc2baa194666d52a3d53302ec273b19a756b499fb34356`

기존 Windows ZIP과 첫 서버 ZIP은 보존합니다. 이 수정은 설치 흐름 보정이며, 미완료 분석 기능 전체를 구현한 새 기능판은 아닙니다.
