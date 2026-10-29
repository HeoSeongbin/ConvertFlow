# 검증 시나리오 — Phase 6

## 단위·컴포넌트 검증
Phase 6 시작 전 기존 백엔드 80개 테스트를 재실행했다. 최종 Windows·Linux 백엔드는 각각 82 passed이며 httpx TestClient deprecation warning 1건이 남아 있다. 프런트 15개 테스트·strict 타입 검사·production build와 Ruff가 통과했다. 상세 결과는 PROGRESS.md를 따른다.

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
실제 Compose prefork Worker로 단일 PNG 및 3페이지 TIFF 병합·정렬·출력 옵션·다운로드·오류 이력을 확인한다. 현재 PostgreSQL 스키마는 0005다. API/Worker/frontend/Redis/PostgreSQL health, Dispatcher·Observer 실행, migrate 정상 종료와 Alembic check를 확인한다.

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

Phase 4 당시 70개 단위/회귀 테스트와 위 실제 장애 시나리오는 별개 검증이다. SQLite 테스트만으로 PostgreSQL 다중 Worker 보장을 주장하지 않는다. 원격 CI는 위 단계를 정의했지만 로컬 실행 결과만 보고한다.

## Phase 5 통계·관측·부하
백엔드 신규 회귀는 SQL 집계·최근 시간창·재시도 성공 뒤 오류 보존·쿠키별 격리, 샘플 없는 시간 null, 실제 0과 UNKNOWN 구분, Observer 실패/stale·부분 응답, Task args 검증, 이전 세대/다른 Worker 오귀속 차단, streaming checksum을 다룬다. 프런트는 UNKNOWN/표본 없음 표시를 확인하며 실제 브라우저에서 메뉴·변환 성공·Dashboard 반영을 별도 검증한다.

```bash
python -m compileall -q backend/app scripts
ruff check backend scripts
python scripts/benchmark_phase5.py --output .storage/phase5-load.json
python scripts/smoke_phase5_active.py
```

실행 중 다른 작업이 없는 localhost Compose에서 실행한다. 부하 harness는 Worker를 중지해 큐 ready 양수를 관측하고 20파일/100페이지를 실제 PDF로 만든다. Worker를 1→2개로 바꾸어 각 6 Job 배치의 시간·분산·Attempt/다운로드를 확인하며, Observer 중단 후 30초 stale이면 UNKNOWN/null, 재기동 후 KNOWN으로 복귀하는지 검사한다. 마지막에 Worker 1개와 Observer로 복원한다.

활성 Task harness는 생성한 입력만 FIFO로 교체하고 실제 PROCESSING Job ID·Heartbeat·슬롯·Task 관측을 확인한다. 다른 workspace의 응답에 해당 UUID가 없는지 검사하고 FIFO를 정규 파일로 복원해 같은 Attempt의 SUCCESS를 확인한다. 실패 경로는 Worker 종료 후 파일·서비스를 복원한다. 기존 사용자 입력은 사용하지 않는다.

메모리/인덱스 방법과 전체 원본은 [benchmarks/README.md](benchmarks/README.md)를 따른다. benchmark_memory.py는 Linux 전용이며 각 3회 비교, benchmark_indexes.py는 rollback되는 PostgreSQL TEMP fixture만 사용한다. 테스트·부하·관측 시각은 서로 다르며 수치를 임의의 운영 보장으로 확대하지 않는다.

실제 브라우저에서 Dashboard의 전체/최근 작업 수·평균 처리시간 반영과 Worker ONLINE/UNKNOWN·큐 수집 시각을 확인했다. 증거는 screenshots/phase5-dashboard.png·phase5-workers.png다. 저장소 Playwright runner는 아직 없으며 이번에는 세션 브라우저로 검증했다. 다음 Phase 6는 UI/UX 개선이다.

API만 잠시 중지하고 정상 Observer/Worker를 유지한 상태에서도 브라우저가 이전 ONLINE/큐 캐시를 UNKNOWN으로 낮추고 연결 오류를 표시하는지 확인했다. API를 즉시 복원했다. 증거: screenshots/phase5-api-unavailable.png. 프런트 회귀는 실제 0/누락, API 오류 중 캐시 보존, 30초 만료 경계를 포함한다.

## Phase 6 실제 UI·커서·미리보기
```bash
python scripts/smoke_phase6.py
```
실제 API→Redis→Worker로 32페이지 TIFF를 PDF로 만든다. 최신 30개+before 커서가 기본 ascending 전체 이벤트와 역순으로 일치하고 중복/누락이 없는지, SUCCESS가 최신인지, 외부 workspace 조회/다운로드 404인지 검사한다. SQLite 회귀는 66개 이벤트·cursor validation·Job 상태 불변도 확인한다. preview는 같은 download 권한 검사를 사용하며 별도 서버 변환을 추가하지 않는다.

세션 브라우저 검증:
1. 빈 PNG+TIFF+PNG 선택→빈 파일 경고/제출 비활성→오류 파일만 제거→PNG 위로 이동. 썸네일/TIFF placeholder·순서 안내 확인.
2. A4 가로·10mm로 실제 3페이지 변환. PDF.js의 1/2/3 페이지 색상 순서·이전/다음 경계·닫기/재열기 확인.
3. Dark→Light 변경 후 새로고침에서도 테마 유지. Job 선택은 유지하고 파일 선택은 초기화.
4. 임시 같은 origin 390×844 iframe에서 화면 선택·이력 카드·필터·상세 focus 이동·PDF 페이지 전환 확인. 실행 전 취소는 0%·실행 안 함이며 완료 전/실행 중으로 표시하지 않음. 실제 기기/Safari 검증으로 확대하지 않음.
5. Worker 잠시 중지→새 Job 대기 중 취소→CANCELLED·Attempt0·다운로드 없음. Worker 정상 복원.
6. 새 테스트 Job의 processing 폴더만 권한 오류로 FAILED/STORAGE_ERROR 생성→권한 복구→UI 수동 재시도→같은 Job #1 실패/#2 성공·오류 원문/이벤트 보존.
7. PDFPreview 모듈을 컨테이너에서 잠시 다른 이름으로 보관→뷰어 오류 안내·다운로드/콘솔 유지 확인→즉시 원래 경로로 복원→새로고침/미리보기 정상 복귀.
8. 실제 32페이지 UI Job에서 최신 30개→더 보기→36개 이벤트. 오류 필터는 불러온 8개에서 FAILED+MANUAL_RETRY_REQUESTED 2개를 표시.

페이지 Canvas 크기/DPR 자원 제한, 진행 상태별 안내, 빈 파일, 취소 시간, binary response 오류 메시지는 Vitest로 검증한다. 모바일 iframe과 임시 asset fault는 검증 환경에만 사용하고 제품에 파일/flag를 남기지 않는다. 스크린샷 phase6-*를 증거로 보존한다. 정식 Playwright runner·cross-browser matrix는 Phase 7 범위다.

## Phase 7 자동 E2E 및 새 환경 검증

`python scripts/validate_phase7.py --faults`를 활성 작업이 없는 localhost Compose에서 실행한다. 실행·프로젝트 분리·복원 절차는 [RUNBOOK](RUNBOOK.md)을 따른다. 기존 Phase 1/2/6 API smoke와 Alembic check, 세 브라우저 E2E, Worker 중지 중 @queued 취소, Phase 3 재시도/취소 및 Phase 4 실제 강제 종료/오래된 소유자 fencing·Compose 장애를 순차 실행한다.

브라우저별 5개 시나리오:
1. TIFF+PNG 순서 변경·A4 가로/여백→실제 PDF 3페이지 색상/경계/다운로드, 신규 workspace 404, UUID 이력 검색, 화면 수평 overflow 없음
2. 빈 파일 사전 차단 및 위장 PNG의 실제 API 422
3. 작은 원본과 과도한 여백의 실제 변환 실패, 오류 Attempt 보존·PDF 미공개
4. 다운로드 네트워크 차단→미리보기 오류→차단 해제/재조회 렌더링 복귀, 테마/선택 작업 reload 보존
5. Worker 중지 중 대기 취소, 진행률 0/Attempt 없음/PDF 없음

기본 suite 12개(4×3), 별도 queued 3개(1×3)이며 retries=0이다. Chrome/Firefox desktop와 mobile-WebKit 엔진 에뮬레이션을 사용한다. 실제 모바일 기기·Safari 지원 또는 장기 부하 검증으로 확대하지 않는다. HTML/JSON·실패 trace/스크린샷은 Git 제외 디렉터리에, 공유 가능한 실행 요약만 docs/validation에 보존한다. Windows Firefox spawn UNKNOWN은 Linux 공식 컨테이너로 검증한다. 원격 GitHub Actions 성공은 실제 실행 확인 전 주장하지 않는다.
