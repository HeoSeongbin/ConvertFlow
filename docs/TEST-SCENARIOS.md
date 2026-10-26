# 검증 시나리오 — Phase 2

## 기준 결과 및 단위/컴포넌트 테스트
이번 작업 전 기존 Linux 백엔드 16개와 프런트 1개 테스트·빌드를 재실행해 통과했다.
최종 `cd backend && python -m pytest -q`: Windows·Linux에서 각각 42 passed. FastAPI/Starlette TestClient의 httpx deprecation warning 1건은 남아 있다. SQLite 기반 테스트와 실제 PostgreSQL 검증을 구분한다.
`ruff check backend scripts`, `cd frontend && npm test && npm run lint && npm run build`: 통과. 프런트 2개 파일 4개 테스트.

백엔드 범위:
- 기존 단일 업로드·상태·PDF 다운로드·접근 토큰·지원 형식·손상 결과·Outbox 재발행 회귀
- 여러 파일 + TIFF 프레임의 실제 출력 페이지 순서와 이미지 색상
- A4/Letter/원본 크기, 방향, 여백의 변환 행렬, contain/cover cropbox
- 출력 품질이 실제 PDF에 포함한 JPEG 크기에 반영되는지 확인
- EXIF 방향과 alpha 흰색 합성 회귀
- 잘못된 옵션, 파일 수/크기/페이지/픽셀 총량 제한과 전체 업로드 정리
- workspace 목록·상세·이벤트·다운로드 격리, 검색·필터·페이지네이션과 토큰 호환성
- 부분 변환 실패 시 진행 수·오류·이벤트 보존, 다운로드 차단, 실패 Job 재전달로 이력 덮어쓰기 방지
- 동시 중복 task 본문 호출 시 Result 및 SUCCESS 이벤트 각 1개 (SQLite). 이는 PostgreSQL 다중 Worker 장애 복구 보장을 의미하지 않는다.
- 0001→0002에서 성공·실패·대기 Job과 오류·결과 해시를 보존하는 마이그레이션 테스트

## 실제 Docker 통합
```bash
docker compose up -d --build --wait --wait-timeout 180
python scripts/smoke.py
python scripts/smoke_phase2.py
docker compose exec -T api python -m pytest -q -p no:cacheprovider
docker compose exec -T api alembic check
docker compose ps
```
Phase 1 smoke는 단일 PNG → Redis → 실제 Linux Celery → PDF 1페이지를 확인한다.
Phase 2 smoke는 PNG+2페이지 TIFF → 3페이지 PDF, red/green/blue 순서, Letter 가로·10mm 여백·cover·품질75, 목록 검색·상태 필터, 이벤트 순서, 타 작업공간의 접근 차단을 확인한다. 또한 작은 원본에 큰 여백을 지정해 실제 Worker FAILED 및 INVALID_OPTIONS 이력, 다운로드 409를 확인한다.

PostgreSQL 검증: 기존 version 0001의 성공 작업 3건을 기록한 뒤 0002 적용. 기존 성공 3건·LEGACY_IMPORTED 3건 보존 확인. `alembic check`는 No new upgrade operations detected. API·Worker·Redis·PostgreSQL·frontend health 및 migration 정상 종료 확인. Dispatcher는 실행 상태이며 별도 readiness probe는 없다.
CI에는 두 smoke를 등록했다. 이번 실행에서 원격 GitHub Actions를 실행한 것으로 표시하지 않는다.

## 실제 브라우저 검증 (이번 세션 CUA/Playwright)
1. cover.png(빨강)와 pages.tiff(초록/파랑) 파일을 다중 선택했다.
2. TIFF를 위로 이동하고 A4 가로·여백10mm로 변환했다.
3. 2파일·3페이지·100%와 입력 순서·options·타임라인을 확인했다.
4. PDF 다운로드 버튼으로 실제 파일을 저장하고 pypdf로 3페이지, A4 가로 및 초록/파랑/빨강 순서를 검증했다.
5. 작업 이력에서 pages.tiff 검색과 상세 선택을 확인했다. 새로고침 뒤 workspace cookie로 동일 작업을 조회했다.
6. 파일 재선택 시 FileList가 지연 updater 전에 초기화되는 문제를 수정한 뒤 새 빌드에서 재선택·변환을 다시 실행했다.
7. 원본 크기·50mm 여백으로 실패를 만들고 INVALID_OPTIONS 메시지, FAILED 이벤트, 실패 필터, 결과 다운로드 버튼 부재를 확인했다.
8. 전체 상태로 돌아가 성공/실패 두 Job이 같이 보이고 성공 결과를 다시 선택할 수 있음을 확인했다.
화면 증거: screenshots/phase2-upload.png, phase2-history.png, phase2-failure.png. 이는 실제 세션 검증이며 저장소에 Playwright E2E runner를 추가한 것은 아니다.

## 후속 검증
Phase 3: 오류별 retry 정책, attempt 추가 및 기존 실패 이벤트 유지, 취소 요청 경합, Retry Center.
Phase 4: PostgreSQL 다중 Worker 동시 Claim, lease/fencing, worker kill·재시작, Redis/DB 장애, 게시 직후 crash, stale attempt 완료 거절. 현재 자동 복구 완료를 주장하지 않는다.
