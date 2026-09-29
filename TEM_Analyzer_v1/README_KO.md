# TEM Analyzer v1: 실행 및 검증

이 앱은 로컬 TEM 이미지에서 스케일/문자 제외 영역을 저장하고, SAM grid·추가 점/box·ROI 재분할 후보를 만들고, 브러시와 레이어로 검수하는 **1단계 분석기**입니다. 경계 보정/GT 및 계측은 데이터 표시 페이지이며 실제 산출 기능은 아직 없습니다.

## 설치

Python 3.10~3.12 권장. `pip install -r requirements.txt` 후 SAM 추론을 쓰려면 GPU/CPU 환경에 맞는 PyTorch 및 Meta `segment-anything`을 별도로 설치하고 공식 ViT-H/L/B 체크포인트를 지정하세요. CPU에서도 추론 가능하나 ViT-H와 grid 32는 오래 걸립니다. GPU A100에서는 `device=auto`가 CUDA를 선택합니다. OCR은 선택 사항이며 EasyOCR와 craft/english_g2 로컬 가중치가 필요합니다. 모델과 가중치를 자동 다운로드하지 않습니다.

```bash
python -m pip install -r requirements.txt
python -m pip install torch torchvision
python -m pip install git+https://github.com/facebookresearch/segment-anything.git
python run.py --port 8765
```

Windows에서 Git 접근이 막히면 공식 SAM 소스 ZIP을 풀어 해당 환경에서 `python -m pip install ./segment-anything` 방식으로 설치하세요. 브라우저에서 `http://127.0.0.1:8765` 접속. 회사 서버 포트가 막히면 서버 로컬 브라우저 또는 허용된 포트/전달 방식을 사용하세요. 앱은 `127.0.0.1`에만 바인딩합니다.

작업 경로는 기본 `projects/default`; 환경 변수 `TEM_PROJECT_DIR`로 변경할 수 있습니다. 이미지와 mask는 그 안에 저장되며 가중치는 포함되지 않습니다. Git에는 projects 폴더를 올리지 않습니다. 중요한 프로젝트는 이 폴더를 별도 복사해 백업하세요.

## 순서

1. 이미지 파일을 추가하고 기본 템플릿의 scale ROI(청록)와 text ROI(분홍)를 확인합니다. 드래그 후 템플릿 저장. 템플릿 위치는 원본 크기 비율로 저장됩니다.
2. OCR 가중치가 있으면 자동 제안 후 확인 버튼, 없으면 수동 스케일을 입력합니다. OCR 결과는 반드시 검수합니다. 스케일이 없어도 SAM 분할은 됩니다.
3. 모델 경로와 ViT-H/L/B 종류를 맞추어 로드합니다. 미세조정한 같은 구조의 mask_decoder state_dict 또는 TorchScript 후단 refiner를 선택적으로 지정합니다.
4. grid 기본 16과 Predicted IoU/Stability/Box NMS 임계값을 설정해 후보를 생성합니다. 자동 후보는 SAM 내부 필터와 NMS를 이미 통과한 결과입니다. 필터로 억제된 후보 복구 UI는 아직 없습니다.
5. 양성/음성점과 box를 추가해 별도 후보를 만듭니다. 후보 선택 후 ROI와 점을 지정하면 원본 crop에서 재추론합니다. 재추론 결과는 parent가 연결된 새 후보로 저장됩니다.
6. 후보 복제, 브러시 추가/삭제 후 새 후보 저장, 레이어 생성/이름 수정, instance 이름을 입력해 레이어에 확정합니다. 경계·GT 페이지에서 미분류·겹침 픽셀 수를 볼 수 있습니다.
7. 프로젝트 상태는 매 변경마다 저장됩니다. 작업을 재개하려면 같은 `TEM_PROJECT_DIR`로 실행합니다.

## 모델 인터페이스

- 기본/학습 decoder: 공식 SAM 전체 모델 로드 후 동일 variant·구조의 `mask_decoder.state_dict`를 strict 로드합니다. ABL은 학습 loss의 유무이므로 추론 로딩 방식은 같습니다.
- 후단 refiner: TorchScript 파일을 로드하고 `forward(image[1,3,256,256], mask[1,1,256,256]) -> logits[1,1,256,256]` 계약을 사용합니다. RGB float32 0~1, mask float32 0/1입니다. 로그잇 >0을 mask로 만들고 원본 크기에 nearest resize합니다. 학습 notebook 출력이 이 계약과 다르면 별도 어댑터를 작성해야 합니다.
- decoder/후단 refiner는 모두 선택 사항입니다. 빈 경로일 때 공식 기본 SAM이 실행됩니다. 학습은 이 앱에 포함되지 않습니다.

## 한계와 안전장치

- OCR 바 검출은 단순 밝은 수평선 후보라 실제 TEM에서 오검출할 수 있습니다. 검수 및 수동 스케일을 제공하지만 OCR/바 제안을 사용자가 세밀히 편집하는 UI는 후속 작업입니다.
- grid 실행은 요청 완료까지 대기합니다. 진행률·취소·추론 작업 큐는 미구현입니다. 큰 영상에서는 먼저 작은 grid와 ROI의 수동 prompt로 시험하세요.
- 여러 후보의 NMS 후 전체 보류/억제 목록은 저장되지 않습니다. SAM 생성기 내부에서 걸러진 후보는 재생성해야 합니다.
- 브러시는 새 후보를 만들어 이전 결과를 보존하지만 영구 Undo/Redo 버튼은 아직 없습니다. 원본 후보를 다시 선택해 돌아갈 수 있습니다.
- 동일 class의 instance 식별과 새 영상으로의 자동 전파, 수평 보정·경계 정밀화·GT export·계측은 미구현입니다. 화면이 그 결과를 주장하지 않습니다.
- 학습된 decoder와 후단 refiner 실가중치 추론, CUDA·A100, 회사 TEM 정확도는 여기서 검증하지 못했습니다.

## 개발 체크

```bash
python -m unittest discover -s tests -v
```

기본 API/저장 테스트는 SAM 가중치 없이 실행됩니다. 실제 회사 PC에서 먼저 1장으로 모델 로드, grid 8/16, 추가 점, 후보 복제, 브러시, 레이어, 저장 재실행을 확인하세요. 평가에는 기본 SAM과 수정 모델의 동일 이미지·동일 prompt 및 엔지니어 수정 시간을 분리해 기록하세요.

ROI 내부 재분할은 생성된 마스크를 부모 마스크 내부로 제한합니다. 부모 밖으로 분할을 넓혀야 한다면 일반 추가 점/box 후보를 사용하세요.

## 회사 서버 테스트 코드

회사 TEM 이미지 없이 합성 영상으로 실행·저장 경로를 확인합니다. 테스트는 임시 프로젝트를 사용하고 끝나면 삭제합니다. 실행 중인 웹 앱 데이터는 건드리지 않습니다.

```bash
cd TEM_Analyzer_v1
python smoke_test.py
```

VS Code **PORTS** 탭에서 전달된 주소도 확인하려면 서버를 별도 터미널에서 실행한 뒤:

```bash
python smoke_test.py --url http://127.0.0.1:8765
```

SAM 체크포인트·Torch·segment-anything이 준비되면 점/box, ROI 재분할 및 작은 grid 2를 추가 검사합니다. A100은 `--device cuda`, CPU는 `--device cpu`를 선택하세요. CPU ViT-H는 매우 느릴 수 있습니다.

```bash
python smoke_test.py --checkpoint /path/to/sam_vit_h.pth --variant vit_h --device cuda
```

학습된 동일 구조 decoder 또는 별도 TorchScript 후단 모델 연결 검사에는 `--decoder /path/to/decoder.pth` 또는 `--refiner /path/to/refiner.ts`를 추가합니다. 현재 경로의 이미지를 읽거나 회사 데이터를 외부로 보내지 않습니다. 성공은 기능 연결 확인이며 회사 TEM 정확도를 의미하지 않습니다.
