# 검증 시나리오 — Phase 4

## 단위·컴포넌트 검증
Phase 4 시작 전 기존 백엔드 64개 테스트를 재실행했다. 최종 Windows·Linux 백엔드는 각각 70 passed이며 httpx TestClient deprecation warning 1건이 남아 있다. 프런트 4개 테스트·strict 타입 검사·production build와 Ruff가 통과했다.

```bash
cd backend
python -m pytest -q
ruff check .
cd ../frontend
npm test
npm run lint
npm run build
```

기존 단일/다중 파일·TIFF·옵션·보안·다운로드·Outbox 검증을 유지한다. 신규 범위:
- transient/permanent 오류 분류, equal jitter 지수 증가와 상한
- 자동 재시도 예약 시각·실행 세대·최대 3회 제한·명시적 수동 주기 초기화
- 같은 Job 아래 INITIAL/AUTO/MANUAL Attempt와 원래 오류 보존
- 오래된 단일 인자 메시지·이전 세대 메시지가 다음 실행을 Claim하지 못하는지 확인
- expectedGeneration을 이용한 중복 수동 요청 CAS와 409
- 원본 누락/변경 및 재처리 불가 입력 거부, 목록의 원본 누락 반영
- QUEUED·RETRY_WAIT 취소, 실행 중 페이지/게시/오류 경계의 취소 우선 처리
- 취소 완료를 반복해도 이벤트·Attempt가 중복 생성되지 않음
- Attempt 페이지네이션·소유권·요청 스키마 검증
- SQLite 0001→0002→0003→0004 마이그레이션의 구형 성공/실패/대기·결과 해시·오류·LEGACY Attempt 보존
- 별도 DB 연결에서 publish 이전에 QUEUED가 커밋된 상태로 보이는지 확인

SQLite 동시 호출 검증과 PostgreSQL 실연동을 구분한다. Phase 4는 만료 Lease의 renew/진행/실패 차단, 살아 있는 Lease 유지, 회수 멱등성·상한, 사망한 취소 요청과 유실 메시지 재발행 테스트를 추가했다. 실제 Lease·다중 Worker·hard kill 근거는 아래 별도 실연동 시나리오다.

## 실제 Compose 기본 검증
```bash
docker compose up -d --build --wait --wait-timeout 180
python scripts/smoke.py
python scripts/smoke_phase2.py
docker compose exec -T api python -m pytest -q -p no:cacheprovider
docker compose exec -T api alembic check
docker compose ps
```
실제 Compose prefork Worker로 단일 PNG 및 3페이지 TIFF 병합·정렬·출력 옵션·다운로드·오류 이력을 확인한다. PostgreSQL 스키마는 0004이며 Alembic check에서 신규 변경이 없었다. API/Worker/frontend/Redis/PostgreSQL healthy, Dispatcher 실행, migrate 정상 종료를 확인했다.

## Phase 3 실제 Redis/PostgreSQL 장애 주입
**로컬 개발/격리 CI용이며 기존 활성 Job이 없어야 한다.** 일반 Dispatcher를 멈춘 뒤 API 컨테이너의 별도 테스트 프로세스에서 전용 큐와 Celery solo test worker를 사용한다. HTTP API·실제 Redis·PostgreSQL·스토리지를 사용하며 task_always_eager로 대체하지 않는다. monkeypatch는 해당 테스트 프로세스에만 적용하고 제품 API에는 오류 주입 플래그가 없다.

PowerShell:
```powershell
docker compose stop dispatcher
try {
    Get-Content scripts/smoke_phase3.py -Raw | docker compose exec -T api python -
    $phase3IntegrationExit = $LASTEXITCODE
} finally {
    docker compose start dispatcher
}
if ($phase3IntegrationExit -ne 0) { throw 'Phase 3 integration failed' }
```
Bash / GitHub Actions:
```bash
docker compose stop dispatcher
trap 'docker compose start dispatcher' EXIT
docker compose exec -T api python - < scripts/smoke_phase3.py
```

검증 순서:
1. ENOSPC 1회 후 자동 재시도 성공: INITIAL FAILED + AUTO SUCCESS, 유효한 PDF.
2. ENOSPC 4회로 자동 재시도 상한 도달: FAILED Attempt 4개.
3. 동일 Job을 수동 재처리하고 이전 세대 메시지를 재전달: 오래된 메시지는 무시, MANUAL SUCCESS, 기존 실패 4개 그대로 보존.
4. RETRY_WAIT 중 취소: 실패 이력 1개 유지, 예약한 다음 Attempt는 실행하지 않음.
5. QUEUED 중 취소: Attempt 0개.
6. 실제 PDF 인코딩 직후 게시를 기다리게 한 뒤 API 취소: CANCEL_REQUESTED→CANCELLED, Result 0개·다운로드 409.
7. 종료 후 일반 Dispatcher 재기동.

초기 실연동에서 QUEUED 갱신 미커밋 상태의 메시지가 소비되어 다음 실행이 건너뛰어지는 문제를 발견했다. 준비 커밋과 publish를 분리한 뒤 위 시나리오가 전부 통과했다. 처음 남은 테스트 Job은 취소 서비스를 통해 종료했으며 자동 복구로 표시하지 않았다. CI 정의에도 이 검증을 추가했지만 이번 실행에서 원격 Actions를 실행하지 않았다.

## 실제 브라우저 검증
- Phase 2 검증(다중 선택·재정렬·A4·TIFF·PDF 검증)을 보존한다.
- Phase 3 테스트 Job의 processing 디렉터리만 쓰기 제한해 실제 Compose Worker에 PermissionError를 발생시켰다. FAILED/STORAGE_ERROR, 최초 Attempt 및 Retry Center 재시도 가능·불가 표시를 확인했다.
- 해당 테스트 디렉터리 권한을 원상복구한 뒤 같은 파일로 재시도 버튼으로 재처리했다. 같은 Job에서 #1 실패·#2 수동 재시도 성공이 함께 남고 이전 오류/이벤트가 보존됐다.
- 다운로드한 PDF를 pypdf로 읽어 정상 1페이지·원본 비율·이미지를 확인했다.
- Dispatcher를 잠시 멈추고 새 Job을 등록해 대기 중 취소했다. CANCELLED·진행률0·실행 안 함·Attempt0·CANCELLED 이벤트와 다운로드 버튼 부재를 확인한 뒤 Dispatcher를 재기동했다.
- 최종 빌드를 새로고침하고 저장된 작업을 다시 선택해 이력이 유지되는지 확인했다.
증거: screenshots/phase3-retry-center.png, phase3-attempts.png, phase3-cancelled.png. 이는 실제 세션 검증이며 저장소에 Playwright E2E runner를 추가한 것은 아니다.

## Phase 4 실제 프로세스·PostgreSQL 동시성
다른 실행 중 작업이 없는 localhost 개발 스택에서만 실행한다. 실제 프로세스와 서비스를 중단하므로 공유 운영 환경에서 실행하지 않는다. 볼륨 삭제는 하지 않는다.

PowerShell:
```powershell
docker compose stop dispatcher
try {
  docker compose cp scripts/smoke_phase4.py api:/tmp/smoke_phase4.py
  docker compose exec -T -e PYTHONPATH=/app api python /tmp/smoke_phase4.py
  if ($LASTEXITCODE -ne 0) { throw 'Phase 4 process checks failed' }
} finally { docker compose start dispatcher }
```

Bash:
```bash
docker compose stop dispatcher
trap 'docker compose start dispatcher' EXIT
docker compose cp scripts/smoke_phase4.py api:/tmp/smoke_phase4.py
docker compose exec -T -e PYTHONPATH=/app api python /tmp/smoke_phase4.py
docker compose start dispatcher
trap - EXIT
```

별도 실제 Celery 프로세스는 전용 큐/6초 Lease/1초 Heartbeat를 사용한다. 제품 기본값은 30/5초다. 테스트 프로세스만 gate를 주입하며 제품 API나 설정에 fault flag를 넣지 않는다.

1. 인코딩을 8초 정지해 페이지 callback 없이도 Heartbeat가 유지하는지 확인한 뒤 SIGKILL.
2. PDF 파일 이동 직후 DB 커밋 전 SIGKILL. PROCESSING 다운로드 409, 새 Attempt만 성공 결과로 노출.
3. 이전 Worker를 SIGSTOP하고 Lease 만료·교체 성공 뒤 SIGCONT. 이전 실행의 결과/이벤트 중복 반영 금지.
4. 두 복구 스케줄러를 동시에 호출해 한 세대만 예약하는지 확인.
5. 두 독립 Worker에 같은 메시지를 12회 보내 Attempt/Result가 각각 1개인지 확인.
6. 실행 중 취소 요청 후 Worker 사망: Lease 회수로 CANCELLED, 추가 Attempt/Result 없음.

## Phase 4 정상 Compose prefork·서비스 장애
Phase 4 프로세스 테스트를 마치고 정상 서비스가 모두 실행 중일 때, 저장소 루트의 Python 환경에서:
```bash
python scripts/smoke_phase4_compose.py
docker compose ps
docker compose exec -T api alembic check
```

테스트가 생성한 PNG의 저장 파일만 일시적으로 FIFO로 바꿔 정상 제품 Worker의 입력 read를 정지시킨다. 운영 코드에 monkeypatch를 주입하지 않는다. finally에서 파일을 복구하고 모든 서비스를 시작한다.

- 정상 prefork Worker 컨테이너 SIGKILL→재시작, 만료 Attempt 오류 보존+새 Attempt 성공.
- Redis 중단 중 업로드202/QUEUED·Outbox 보존, Redis 복귀 후 단일 Attempt 성공.
- PostgreSQL 35초 중단으로 기본 Lease 만료, 이전 Worker DB 상태 변경 차단, DB 복귀 후 새 Attempt 성공.
- API·Dispatcher 재시작 후 같은 Job/Result 지속.

70개 단위/회귀 테스트와 위 실제 장애 시나리오는 별개 검증이다. SQLite 테스트만으로 PostgreSQL 다중 Worker 보장을 주장하지 않는다. 원격 CI는 위 단계를 정의했지만 로컬 실행 결과만 보고한다. 다음 Phase 5는 관측 지표·성능 측정이다.
