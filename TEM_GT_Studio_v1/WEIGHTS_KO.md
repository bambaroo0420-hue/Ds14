# 가중치 수동 설치 — v1.1

프로그램 가중치 자동 다운로드는 사용하지 않습니다. 아래 폴더는 ZIP에 미리 만들어 두었습니다. Git에서는 빈 폴더 보존용 `.gitkeep`만 들어 있습니다. `.pth` 파일을 넣어도 Git에 자동 포함되지 않도록 제외했습니다.

## 1. OCR: 기본 영문·숫자 모드에는 두 파일 필요

아래 ZIP을 **압축 해제**하고 `.pth` 파일을 `models/easyocr/` 바로 아래에 넣으세요. ZIP 그대로 또는 중첩 폴더로 넣으면 인식하지 않습니다.

| 용도 | 다운로드 | 넣을 파일 |
|---|---|---|
| 문자 위치 검출, 공통 필수 | [CRAFT ZIP](https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip) | `models/easyocr/craft_mlt_25k.pth` |
| 영문·숫자 인식, 기본 모드 필수 | [English G2 ZIP](https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip) | `models/easyocr/english_g2.pth` |
| 한글 샘플명까지 인식할 때만 추가 | [Korean G2 ZIP](https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/korean_g2.zip) | `models/easyocr/korean_g2.pth` |

UI의 OCR 폴더 기본값은 `models/easyocr`. `영문·숫자`는 CRAFT+English, `한글·영문·숫자`는 CRAFT+Korean을 사용합니다. 모드를 바꾸어 쓸 경우 세 파일을 모두 넣으세요. 실행 프로그램 설치, PATH, Tesseract는 필요 없습니다. EasyOCR/PyTorch Python 패키지는 필요하며 requirements 설치에 포함됩니다.

## 2. micro-SAM 체크포인트

| 선택 | 다운로드 | 넣을 파일 | UI |
|---|---|---|---|
| 공개 EM 비교용 ViT-B | [Zenodo 공식 페이지](https://zenodo.org/records/10524828) / [가중치 직접 받기](https://zenodo.org/records/10524828/files/vit_b_em_organelles.pth?download=1) | `models/micro_sam/vit_b_em_organelles.pth` | backend=`micro_sam`, model=`vit_b` |

이 EM 가중치는 미토콘드리아 등 **생물학적 전자현미경 데이터로 미세조정된 모델**입니다. 반도체 TEM 전용이 아니며 기존 SAM보다 잘된다고 보장하지 않습니다. 사용자가 가진 다른 ViT-B/L/H 체크포인트도 폴더에 넣고 구조에 맞는 model을 고르면 됩니다. 이 도구의 점/box 추론에는 별도 automatic-instance-segmentation decoder 파일이 필요 없습니다.

micro-SAM 패키지는 공식 설치 방법으로 준비한 환경에서 사용합니다: https://github.com/computational-cell-analytics/micro-sam
기본 requirements만으로 micro-SAM 패키지까지 설치되지는 않습니다. 해당 환경에서 이 앱의 requirements를 설치하세요.

## 3. 기존 SAM 가중치를 사용할 경우 (선택)

이미 가지고 있다면 다시 받을 필요 없습니다. 세 개 모두 받을 필요 없이 하나만 선택합니다.

| 구조 | 공식 다운로드 | 넣을 파일 |
|---|---|---|
| ViT-B | [sam_vit_b_01ec64.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth) | `models/sam/sam_vit_b_01ec64.pth` |
| ViT-L | [sam_vit_l_0b3195.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth) | `models/sam/sam_vit_l_0b3195.pth` |
| ViT-H | [sam_vit_h_4b8939.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth) | `models/sam/sam_vit_h_4b8939.pth` |

## 4. 연결 순서

1. 가중치 파일을 위 폴더에 넣습니다.
2. SAM 모델 설정에서 **가중치 목록 새로고침**을 누릅니다.
3. 파일을 선택하면 폴더 기준 backend와 파일명의 vit_b/l/h가 입력됩니다. 이름이 임의로 바뀐 파일은 직접 확인하세요.
4. CPU/CUDA를 선택하고 **모델 로드**를 누릅니다. 체크포인트가 다른 드라이브에 있으면 절대 경로 입력도 가능합니다.
5. OCR은 해당 폴더와 언어만 선택하고 실행합니다. 기본 CPU 사용, 자동 다운로드 OFF. 누락 파일은 이름을 표시하고 중단합니다.

모든 상대 경로는 앱 폴더 기준입니다. `.pth` 내용의 모델 호환성/정상 여부는 실제 로드 시 검사됩니다. 폴더에 파일이 있다는 것만으로 정상 가중치라고 판단하지 않습니다. EasyOCR는 자체 체크섬 검사를 사용하며 잘못된 파일을 자동 다운로드로 대체하지 않습니다.

## 공식 출처 (2026-09-28 확인)

- EasyOCR 파일명/URL: https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/config.py
- EasyOCR API: https://www.jaided.ai/easyocr/documentation/
- micro-SAM EM 가중치: https://zenodo.org/records/10524828
- SAM 가중치: https://github.com/facebookresearch/segment-anything#model-checkpoints
