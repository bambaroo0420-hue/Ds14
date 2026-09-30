# TEM Analyzer v2.2.9 Windows 소스 ZIP

[ZIP 다운로드](https://raw.githubusercontent.com/bambaroo0420-hue/Ds14/codex/tem-v2-batch-metrology/releases/tem-v2.2.9/TEM_Analyzer_v2_v2.2.9_windows_source.zip)

경로: `releases/tem-v2.2.9/TEM_Analyzer_v2_v2.2.9_windows_source.zip`

GitHub Release 자산이 아니라 `codex/tem-v2-batch-metrology` 브랜치의 파일입니다. 예전 비교용 v2.2.8 ZIP은 보존되어 있습니다. 이번 오류 수정본은 **v2.2.9**입니다. main은 병합하지 않았습니다.

## 설치 및 실행

1. ZIP을 새 폴더에 완전히 풀고 내부 `TEM_Analyzer_v2`를 엽니다. 기존 프로젝트와 모델은 백업·보존하세요.
2. Python 3.11 이상 64-bit 환경에서 `install_windows.bat`을 최초 한 번 실행합니다. 회사 오프라인 설치는 내부 `docs/INSTALL_KO.md`의 wheel 준비 및 `--offline` 절차를 따르세요.
3. SAM/OCR 패키지와 모델은 별도 설치입니다. 체크포인트 직접 다운로드 링크도 같은 문서에 있습니다. `.venv`를 다른 PC에서 복사하지 마세요.
4. 매일 실행은 `start_windows.bat`입니다. 재설치/모델 재다운로드하지 않습니다. 오류 확인은 `diagnose_windows.bat`입니다.
5. 이전 프로젝트를 열려면 `start_windows.bat --project "프로젝트 폴더 전체 경로"`. 원래 서버를 종료한 뒤 사용하고 같은 프로젝트를 중복 실행하지 마세요.

## 수정·검토

- Windows 임시 파일 교체 재시도, prepared SAM 메타데이터 최종 1회 저장, 지속 저장 오류 시 편집 중단.
- 이미지 입력 read 오류와 저장 오류 구분, `uvicorn` 등 누락 사전 검사, 실행 가상환경 고정.
- 일괄 스케일 표: 검출 제안 → 미적용 값 저장 → 확인·확정. 1번 화면 갱신, 제외 적용 상태와 구분.
- Python 169 tests, Node 6종, 실제 CPU SAM 7개 후보 및 2장 OCR, 선택 mask의 GT 없는 회전·계측/부분 GT 내보내기를 확인했습니다.
- 상세 구현 여부와 한계: ZIP의 `docs/V229_REVIEW_KO.md`. 회사 정확도·완전 무인 GT는 검증되지 않았고, 곡면 국소 법선 두께와 통합 batch recipe는 미구현입니다.

## 패키지 확인

- 175개 파일, 460,668 bytes. `SOURCE_SHA256.json`의 174개 소스 해시(LF 정규화) 포함.
- ZIP CRC, 원본/동기화 소스 해시, Python 116개 문법 검사 통과. BAT는 Windows CRLF로 보관했습니다.
- SHA-256: `e9d63e6a14f91f3f10ab73a22df4aeff3ae0932c2fce79332c34ccf03082b725`
- 모델, 이미지, 가상환경, 개인 프로젝트, 실제 테스트 산출물은 포함하지 않았습니다. 완전 오프라인 일체형 실행 파일이 아닌 **소스 배포본**입니다.
