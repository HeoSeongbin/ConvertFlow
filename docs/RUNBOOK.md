# 실행·자동 검증·장애 시연

## 새 환경

Docker Desktop Linux 엔진/Compose v2, Git, Python 3.12가 필요하다. 호스트에서 단위 테스트를 실행하려면 Node 22.13+ 또는 24+를 추가한다. E2E는 고정한 Playwright Linux 이미지 안에서 실행하므로 호스트 브라우저 설치가 필요 없다. 최초 실행에는 이미지·패키지 다운로드가 필요하다.

```bash
git clone https://github.com/HeoSeongbin/ConvertFlow.git
cd ConvertFlow
docker compose up -d --build --wait --wait-timeout 180
docker compose ps --all
python -m venv .venv
# Windows: .venv\Scripts\activate / bash: source .venv/bin/activate
pip install -r backend/requirements.lock.txt
python scripts/validate_phase7.py
```

UI는 http://localhost:8080, API는 http://localhost:8000/docs다. DB migration은 migrate 서비스가 실행한다. `.env.example` 기본값으로 localhost에서 시작할 수 있다. 다른 서비스가 8000/8080을 사용하면 먼저 종료한다.

## 자동 검증

```bash
python scripts/validate_phase7.py --faults
```

사용자가 진행 중인 Job이 없는 개발 스택에서 실행한다. 실행기는 활성 작업을 사전 검사하고 API smoke·스키마·Chromium/Firefox/모바일 크기 WebKit E2E 후 Worker를 잠시 중지해 실제 대기 취소를 검사한다. `--faults`는 기존 Phase 3·4 전용 프로세스 및 실제 Compose 서비스 장애 테스트도 실행한다. Worker·Dispatcher·Redis·PostgreSQL이 잠시 중단된다. 정상/실패 모두 finally에서 서비스를 복원하며 볼륨을 삭제하지 않는다. 터미널/호스트 자체가 강제 종료되면 아래 복원 명령을 직접 실행한다.

```bash
docker compose up -d --wait --wait-timeout 180
docker compose ps --all
docker compose exec -T api alembic current
```

로그·각 단계 exit code/시간은 `artifacts/phase7`, E2E HTML은 `frontend/playwright-report`, 실패 trace/스크린샷은 `frontend/test-results`에 기록한다. 결과는 Git에서 제외한다. trace에는 테스트 작업의 cookie/접근 정보가 포함될 수 있으므로 공개 포트폴리오에 업로드하지 않는다. CI artifact는 7일 보관한다.

E2E만 실행:

```bash
docker compose run --rm --build e2e
```

`@queued`는 Worker가 정지된 동안 실행기가 별도로 호출한다. 평상시 E2E는 이를 제외한다. 실행기는 retries=0으로 실패를 숨기지 않는다. 모바일 WebKit은 브라우저 엔진·viewport 에뮬레이션이며 실제 iPhone/Safari 기기 검증이 아니다.

## Worker 강제 종료 시연

```bash
python scripts/smoke_phase4_compose.py
```

이 스크립트는 새 테스트 입력만 FIFO로 교체해 실제 Worker 읽기를 대기시킨 뒤 SIGKILL한다. 원본을 복원하고 Worker를 재시작한다. Lease 만료 후 이전 Attempt의 WORKER_LEASE_EXPIRED와 새 Attempt의 SUCCESS, 실제 PDF를 확인한다. 이어 Redis 중단 중 Outbox 보존, DB 중단이 Lease보다 길어진 경우의 복구, API·Dispatcher 재시작 뒤 이력 보존을 검증한다. 오류 주입용 제품 API/환경 플래그는 없다. 파일 복원과 서비스 시작을 finally에서 시도한다.

중복 메시지·이전 소유자 fencing·결과 게시 경계 강제 종료까지는 `validate_phase7.py --faults`를 사용한다. 전체 검증은 수 분이 걸릴 수 있다. 성공 출력 전에는 복구 성공으로 판단하지 않는다.

## 기존 데이터와 분리한 기동

동일 포트 충돌을 피하기 위해 현재 스택을 먼저 `docker compose stop`으로 중지한 뒤 별도 프로젝트 이름을 사용한다. PowerShell에서는 `$env:COMPOSE_PROJECT_NAME='convertflow-clean-check'`, bash에서는 `export COMPOSE_PROJECT_NAME=convertflow-clean-check`를 설정한다. 새 이름은 별도 DB/Redis/storage 볼륨을 만든다. 위 기동·검증 명령을 실행하고 `docker compose down`으로 해당 스택을 종료한다. 환경변수를 제거한 뒤 원래 스택을 `docker compose up -d --wait --wait-timeout 180`으로 복원한다. `down -v`는 사용하지 않는다.

## 문제 진단

- ready 실패: `docker compose logs migrate api postgres redis`로 migration/연결을 확인한다.
- QUEUED 지속: Dispatcher·Worker·Redis 로그와 Outbox/관측 시각을 확인한다. DB 상태를 수동 SUCCESS로 바꾸지 않는다.
- UNKNOWN: Observer 관측 지연/실패일 수 있다. Worker 종료라고 단정하지 않는다.
- storage 오류: 로그의 새 Job UUID와 파일 경로/권한을 확인하고 복구 후 UI 수동 재시도를 사용한다. 이전 Attempt는 남는다.
- E2E 브라우저 실행 실패: 고정 Docker 이미지 실행 결과와 호스트 실행 결과를 구분한다. Windows 호스트 Firefox의 `spawn UNKNOWN`은 Linux 검증으로 대체해 재현한다.
