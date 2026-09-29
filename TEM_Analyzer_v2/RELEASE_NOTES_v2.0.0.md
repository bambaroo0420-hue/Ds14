# v2.0.0 · 2026-09-29

Base: Ds14 main `42e858d9aad95b36a013bb05f9ff45e5d384d3d8` (TEM_Analyzer_v1 v1.5).

우선순위 1·2를 `TEM_Analyzer_v2`로 통합했습니다. 기존 v1 폴더는 변경하지 않습니다.

- 복구 가능한 이미지 삭제, 다중 선택, 비동기 상태 보호
- 부모 후보 교체/분할, 영속 Undo/Redo, 수동/레이어 보호
- 기존 mask seed + logits 재사용, 독립 SAM/edge 전처리
- Lab decoder/refiner bundle 검증과 single-mask 모델 경로 통일
- 법선 gradient/DP 경계 미리보기, 피크 비교/프로파일/고정점/부분 설정
- 인접 두 후보의 공유 경계 동시 갱신과 연결 구조 보호
- 배경/unknown/uncertain/excluded GT, valid-aware 학습 ZIP 및 평가 CSV
- 이미지별 OCR/바 매칭과 공통 길이 fallback, 실행 provenance

검증: Python unittest 29회 실행 통과(상속된 기존 워크플로 재실행 포함), smoke test 10항목 통과, Node canvas 회귀 검증 통과. 테스트는 합성 이미지와 모의 모델 응답을 사용합니다. 실제 SAM/적응 가중치, EasyOCR, GPU, 실제 TEM 정확도는 이 환경에서 검증하지 않았습니다. README의 실제 모델 smoke test로 추가 검증할 수 있습니다.

알려진 제한: 8-bit 입력, 루프당 최대 2,500 경계 샘플, 상위 5개 시작점 탐색의 근사 폐곡선 DP. 정상 삭제 복원 UI, RF/이미지 간 자동 전파, 두께 계측은 후속 작업입니다.
