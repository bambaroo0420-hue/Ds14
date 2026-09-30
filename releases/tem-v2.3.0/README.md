# TEM Analyzer v2.3.0 Windows 소스 배포

파일: **TEM_Analyzer_v2_v2.3.0_windows_source.zip**

GitHub 파일 화면에서 Download raw file을 누르거나 [ZIP 직접 다운로드](https://github.com/bambaroo0420-hue/Ds14/raw/refs/heads/codex/tem-v2-batch-metrology/releases/tem-v2.3.0/TEM_Analyzer_v2_v2.3.0_windows_source.zip)를 사용하세요.

1. 기존 프로젝트/모델 폴더를 백업하고 ZIP은 새 폴더에 풉니다.
2. 최초 설치는 `TEM_Analyzer_v2/install_windows.bat`, 이후 실행은 `start_windows.bat`입니다. 같은 가상환경이면 매번 설치하지 않습니다.
3. 가중치·패키지·영상은 포함되지 않습니다. 오프라인 설치와 SAM/EasyOCR 체크포인트 링크는 패키지의 `README_KO.md`, `docs/INSTALL_KO.md`를 확인하세요.
4. `docs/V230_USER_GUIDE_KO.md`는 버튼별 사용법, `V230_IMPLEMENTATION_KO.md`는 상세 변경/실측, `V230_FINAL_REVIEW_KO.md`는 요구사항별 완료/부분/미구현과 최종 코드 검토입니다.

Python 198개와 UI 로직 8개 묶음, 실제 SAM ViT-B/EasyOCR 및 주요 브라우저 조작을 검증했습니다. 회사 이미지/전문가 GT 정확도, 모든 버튼 조합, 45° 얇은 층 자동 GT를 승인한 것은 아닙니다. 내부 구멍 자동 채움과 전체 공정 통합 Recipe 등은 남아 있습니다.

ZIP CRC/소스 해시/구문 검사를 통과한 원본 소스 배포입니다. 전체 ZIP SHA256은 `SHA256SUMS.txt`, 파일 수/용량은 `verification.json` 참조. 사용자 영상·모델·프로젝트·원시 시험 로그는 공개 업로드하지 않았습니다. 기존 v2.2.9 ZIP도 별도 보존하며 main에는 병합하지 않습니다.
