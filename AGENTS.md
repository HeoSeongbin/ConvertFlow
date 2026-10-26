# ConvertFlow 작업 규칙
1. 작업 전 PROJECT.md, docs/PROGRESS.md, docs/DECISIONS.md를 읽는다.
2. Git 상태와 실제 코드·문서를 비교하고 현재 Phase를 확인한다.
3. 기존 정상 기능을 보존하고 승인된 Phase 범위만 구현한다. 최초 작업은 Phase 0과 1이다.
4. API에 변환 로직을 넣지 않고 DB를 상태 기준으로 사용한다.
5. 변경에 맞는 테스트를 추가하고 타입 검사, Ruff, 테스트, 빌드를 실행한다.
6. 실제 실행하지 않은 검증을 통과 또는 완료로 표시하지 않는다.
7. 작업 종료 시 PROGRESS.md를 갱신하고 결정은 DECISIONS.md에 기록한다.
8. README와 구현 상태를 일치시키고 미완료 기능 및 차단 요인을 명시한다.
9. Worker 장애 복구는 실제 강제 종료 검증 전 완료를 주장하지 않는다.
10. Phase 2 이후 기능은 해당 Phase 작업 요청 시 진행한다.
