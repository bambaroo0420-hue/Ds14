# v2 상태·좌표 계약

- 모든 마스크와 좌표는 업로드된 원본 해상도 기준이다. crop SAM 입력만 로컬 좌표로 변환하고 결과를 원본 좌표에 복원한다.
- 원본 PNG와 후보 mask 파일은 불변이다. 편집은 새 ID를 만든다. active=false 부모는 합성/출력에서 빠지지만 이력과 mask는 남는다. candidate soft delete도 undo를 위해 파일을 보존한다.
- API는 단일 asyncio gate로 읽기/쓰기를 직렬화한다. mutation 전 snapshot을 저장하고 실패 응답이면 metadata를 복원한다. 편집 history는 20개, redo와 함께 project.json에 저장한다. 업로드/이미지 삭제는 history를 초기화한다.
- 이미지 삭제는 journal 생성 → 원본/마스크/logits를 trash로 이동 → metadata 저장 순서다. 중간 실패는 이동을 되돌리고 metadata를 유지한다. 파일 이동 중 프로세스가 종료되면 다음 Project 로드 때 journal을 기준으로 복구한다.
- 각 이미지의 적용 템플릿과 SAM/edge 전처리를 따로 저장한다. 새 이미지는 제외 영역을 적용하지 않은 상태로 시작한다. 전처리/제외 영역 변경은 검수 상태를 무효화한다.
- SAM low logits는 모델 SHA + adaptation SHA + 분석용 이미지 SHA/shape가 같을 때 재사용한다. 불일치하거나 crop이면 기존 mask를 SAM input_size로 resize/pad하고 low-resolution seed로 변환한다.
- 경계 미리보기는 메모리의 token/revision에 묶인다. 다른 편집 후 적용은 거부한다. A/B 마스크의 합집합을 보존하고 공통 경계 근처에서만 이동한다. 보호/무효 영역은 유지하며 연결 성분/구멍 수 변화는 거부한다. 실제 적용 mask와 이상적인 DP 곡선은 제약 때문에 다를 수 있다.
- semantic 합성은 활성 후보와 명시적 annotation의 결과다. 서로 다른 layer의 충돌은 uncertain이며 valid=false다. annotation이 직접 지정된 픽셀은 annotation 상태가 우선한다. layer 잠금 픽셀에는 annotation을 쓰지 않는다.
- export는 reviewed active 후보만 사용한다. invalid를 background로 학습시키지 않도록 valid.png와 lab_mask.png를 함께 제공한다. raw labels의 특수 코드와 Lab용 단일 ignore 코드를 구분한다.

구현 파일: storage.py(보존/이력), preprocessing.py(입력), sam_service.py(모델), boundary.py(법선/DP), labels.py(GT 상태), v2_api.py(트랜잭션/공유 경계/출력), web/v2.js(검수 UI).
