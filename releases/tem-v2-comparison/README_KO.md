# TEM Analyzer v2 비교용 소스 ZIP

PDF에서 비교한 초기 확장 버전(B)과 최종 버전(F)을 각각 독립된 ZIP으로 제공합니다.
앱 기능을 변경하지 않고, 아래 고정 커밋의 `TEM_Analyzer_v2/` 파일만 묶었습니다.

| 파일 | 기준 커밋 | 내용 |
|---|---|---|
| [초기 feat(tem-v2) ZIP](TEM_Analyzer_v2_feat_b9cb34b_source.zip?raw=1) | `b9cb34bc858261f2bf6b6b677e4d85536ed65beb` | 에지 프롬프트·노이즈 제거·공개 이미지 검토를 포함한 PDF B 버전. UI v2.1 계열, 정적 자산 v2.1.2 |
| [최종 v2.2.8 ZIP](TEM_Analyzer_v2_v2.2.8_be05d82_source.zip?raw=1) | `be05d820cb5ccce7dba99e31e1ffc9e074bcba28` | 선택 mask 부분 GT·재사용·ROI·회전 기준 비교·두께/CD 보존과 최종 안전 회귀를 포함한 PDF F 버전 |

첫 번째 feat 커밋 `a2f2773`(PDF A)이 아니라, 기능 확장까지 포함한 두 번째 feat 커밋을 초기 비교 ZIP으로 삼았습니다. 최종 ZIP은 PDF의 기준인 `be05d82`로 고정했으며, 이후 예약 종료 문서만 바뀐 `30c66e7`과 구분합니다.

## 포함 / 제외

- 포함: 실행 소스, 웹 UI, 설치 배치 파일, requirements, 설치·개발·검증 문서, 테스트 코드, 번들 SAM 소스와 해당 라이선스.
- 제외: SAM/EasyOCR 가중치, Python/가상환경, 패키지 wheel, 회사·공개·첨부 이미지, 사용자 프로젝트, 테스트 결과 데이터, 비교 PDF.
- 실행파일(EXE)이나 설치 완료 환경이 아닌 **소스 배포본**입니다. 실제 SAM/OCR 사용에는 설치 문서에 따라 패키지와 모델을 별도로 준비해야 합니다.

## 실행 순서

1. 두 ZIP을 서로 다른 폴더에 압축 해제합니다. 예: `TEM_B/TEM_Analyzer_v2`, `TEM_F/TEM_Analyzer_v2`.
2. 각 폴더의 `docs/INSTALL_KO.md`를 먼저 읽습니다. 모델 공식 다운로드 링크와 회사 오프라인 설치 방법이 포함되어 있습니다.
3. Python 준비 후 각 버전에서 최초 1회 `install_windows.bat`를 실행하고, 사용할 SAM·EasyOCR 패키지와 가중치를 설치합니다.
4. 이후 `start_windows.bat`로 실행합니다. 동일한 `.venv`를 사용하는 한 매번 재설치하지 않습니다.
5. 동시에 비교하려면 다른 포트와 별도 테스트 프로젝트를 사용합니다. 예:

```powershell
# 각 버전 폴더에서 실행. 두 번째 버전은 --port 8766 사용.
.\.venv\Scripts\python.exe run.py --port 8765 --project projects/comparison_B
```

**같은 프로젝트 폴더를 두 버전에서 공유하지 마세요.** 비교용 복사본 또는 새 프로젝트를 사용하고, 최종 버전에서 저장한 프로젝트를 구버전으로 덮어쓰지 마세요. 스케일·회전·GT는 자동 제안과 사용자 확정을 구분합니다. 회사 정확도와 전문가 GT 검증이 완료된 제품이라는 뜻은 아닙니다.

## 무결성 및 검증 범위

SHA-256은 [SHA256SUMS.txt](SHA256SUMS.txt)에 있습니다. 다운로드 후 확인:

```powershell
Get-FileHash .\TEM_Analyzer_v2_feat_b9cb34b_source.zip -Algorithm SHA256
Get-FileHash .\TEM_Analyzer_v2_v2.2.8_be05d82_source.zip -Algorithm SHA256
```

패키징 검사: ZIP CRC, 중복/상위 경로 방지, ZIP 내용과 지정 커밋의 Git blob 바이트 일치, 기존 SOURCE_SHA256 전체 일치, 필수 설치 파일, 제외 대상, Python 문법을 확인했습니다. 초기 108파일(문법 검사 71 Python), 최종 168파일(112 Python)입니다. 이번 배포 과정에서 실제 SAM/OCR/GUI 실험을 새로 실행하지 않았습니다. 기존 기능 검증 근거는 각 ZIP의 `docs/`에 있습니다.

재생성 방법(Windows의 CRLF 자동 변환을 끄고 Git 원문 바이트 보존):

```powershell
git -c core.autocrlf=false archive --format=zip --output=TEM_Analyzer_v2_feat_b9cb34b_source.zip b9cb34bc858261f2bf6b6b677e4d85536ed65beb TEM_Analyzer_v2
git -c core.autocrlf=false archive --format=zip --output=TEM_Analyzer_v2_v2.2.8_be05d82_source.zip be05d820cb5ccce7dba99e31e1ffc9e074bcba28 TEM_Analyzer_v2
```

GitHub의 기존 `codex/tem-v2-batch-metrology` 브랜치 / PR #1에 추가한 소스 배포 파일입니다. `main` 병합이나 새 모델 배포는 하지 않습니다.
