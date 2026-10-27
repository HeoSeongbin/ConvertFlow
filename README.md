# ConvertFlow
이미지 업로드 요청과 PDF 변환을 분리하는 비동기 문서 처리 플랫폼입니다. **Phase 3 — 실패 처리 및 재시도**까지 구현하고 Docker에서 검증했습니다.

React → FastAPI → PostgreSQL Outbox → Dispatcher → Redis → Linux Celery Worker → 공유 스토리지로 처리합니다. DB를 상태의 기준으로 사용하고 큐에는 Job UUID만 전달합니다.

## 구현 기능
- PNG/JPEG/BMP/WEBP/TIFF 다중 업로드와 파일별 검증·제거·순서 변경
- 여러 이미지 및 TIFF 전체 페이지를 지정 순서대로 하나의 PDF로 변환
- 원본 크기 / A4 / Letter, 자동·세로·가로, 여백, 비율 유지 맞춤·중앙 자르기, JPEG 인코딩 품질
- 실제 처리 페이지 기반 진행률과 처리 단계, 입력 파일·옵션·결과 메타데이터
- 작업 목록·파일명/UUID 검색·상태 필터·페이지네이션·처리 시간
- 성공·실패 작업 상세와 영속 이벤트 타임라인, 검증한 PDF 다운로드
- 같은 Job 아래 실행별 Attempt와 오류·Worker·시간·재시도 이력 보존
- 일시 오류 자동 재시도: 최대 3회, 지수 backoff + jitter, DB 기반 실행 예약
- Retry Center의 실패 작업 조회·수동 재처리·불가 사유 표시
- 대기/재시도 대기 즉시 취소, 실행 중 협조적 취소와 결과 게시 차단
- 한국어 UI, Light/Dark 모드, 반응형 레이아웃

## 실행
Docker Desktop Linux 엔진을 실행하고 루트에서:
```bash
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
```
[화면](http://localhost:8080) · [Swagger](http://localhost:8000/docs)
`.env.example`의 기본값으로 로컬 실행할 수 있습니다. 호스트 포트는 127.0.0.1에만 연결하며 DB·Redis는 내부 네트워크 전용입니다. Alembic migrate 서비스가 성공한 뒤 API와 Worker가 시작됩니다.

파일을 선택하거나 끌어다 놓고, 위·아래 버튼으로 순서를 바꿉니다. PDF 옵션을 지정한 뒤 변환합니다. TIFF는 각 프레임을 하나의 페이지로 확장합니다. 성공 후 PDF 다운로드를 누르세요. 작업 이력에서 검색하거나 상태를 필터링하고 파일명을 눌러 상세·이벤트를 확인할 수 있습니다.

제한은 파일 20개, 개별 20 MiB, 전체 100 MiB, 작업 전체 100페이지, 페이지당 25M 픽셀, 작업 전체 100M 픽셀입니다. 다중 프레임은 TIFF만 지원합니다. 원본 크기는 96 DPI 기준이며 자동 방향은 원본 크기에서는 원본 비율, A4/Letter에서는 기본 세로입니다. 원본이 작으면 큰 여백은 실패할 수 있으며 오류 원인을 이력에 보존합니다.

## 재시도와 취소
일시적 저장소 오류·리소스 부족·soft time limit은 최초 실행 이후 최대 3회 자동 재시도합니다. 기본 대기 범위는 1차 2.5~5초, 2차 5~10초, 3차 10~20초이며 최대 지연 설정은 300초입니다. DB의 예약 시각이 지나면 Dispatcher가 QUEUED 전환을 먼저 커밋하고 실행 세대를 포함한 메시지를 발행합니다. 브로커에 미래 ETA 메시지를 장기 보관하지 않습니다.

최대 횟수 초과나 일반 변환 실패는 Retry Center에서 원인을 확인한 후 **같은 파일로 재시도**할 수 있습니다. 원본·옵션·Job ID를 유지하고 새 Attempt를 추가하며 이전 오류를 지우지 않습니다. 수동 재시도는 자동 재시도 주기를 새로 시작합니다. 손상된 입력·미지원 형식·잘못된 옵션은 같은 입력으로 재시도하지 않습니다. 원본이 없거나 변경되면 요청을 거부합니다. 권한 오류는 자동 반복하지 않으며 운영자가 권한을 복구한 뒤 수동 재시도할 수 있습니다.

**작업 취소**를 누르면 QUEUED/RETRY_WAIT는 즉시 CANCELLED, PROCESSING은 CANCEL_REQUESTED가 됩니다. Worker는 입력 파일/페이지 처리 경계와 결과 게시 직전 취소를 확인합니다. 이미지 디코딩·인코딩을 즉시 강제 종료하지는 않습니다. 취소가 확정되면 결과를 다운로드할 수 없습니다. 이미 SUCCESS로 확정된 작업은 취소할 수 없습니다. 취소를 실제로 완료한 Worker가 없으면 CANCEL_REQUESTED를 임의로 완료 처리하지 않습니다.

## 작업공간 및 기존 데이터
첫 정상 업로드에서 30일 HttpOnly/SameSite=Lax 쿠키로 로컬 브라우저 작업공간을 만듭니다. 서버는 해시만 저장하고 목록·상세·다운로드를 해당 작업공간으로 제한합니다. 기존 `X-Job-Token` 단일 작업 접근 방식도 유지합니다. 쿠키를 삭제하면 목록 접근 권한이 사라집니다. 이는 사용자 계정 인증을 대신하지 않으며 공개 서비스용이 아닙니다.

0002 마이그레이션은 기존 작업·오류·결과를 보존하고 파일·결과 테이블을 채웁니다. 소유자를 알 수 없는 Phase 1 작업은 임의의 브라우저 목록에 노출하지 않습니다. 기존 접근 토큰으로 계속 조회·다운로드할 수 있습니다. 과거 이벤트를 추측해 만들지 않고 `LEGACY_IMPORTED` 스냅샷만 추가합니다. 다중 파일/이력 유실 방지를 위해 0002 downgrade는 의도적으로 차단합니다. 0003은 이전 실행을 LEGACY Attempt로 보존하며 알 수 없는 Worker는 UNKNOWN, 없는 시각은 null로 남깁니다. Attempt 이력을 잃는 0003 downgrade도 차단합니다.

## 검증
Python 3.12, Node 22 이상을 권장합니다.
```bash
python -m venv .venv
# venv 활성화 후
pip install -r backend/requirements.lock.txt
cd backend
python -m pytest -q
ruff check .
cd ../frontend
npm ci
npm test
npm run lint
npm run build
```
Compose 기동 후 루트에서:
```bash
python scripts/smoke.py
python scripts/smoke_phase2.py
docker compose exec -T api alembic check
docker compose logs -f api worker dispatcher
```
백엔드 **Windows·Linux 각각 64개 테스트**, 프런트 **4개 테스트·타입 검사·빌드**가 통과했습니다. 실제 Redis→Linux Worker로 단일 이미지 및 3페이지 TIFF 병합, 출력 크기·순서, 실패 이벤트, 작업공간 격리를 확인했습니다. 브라우저에서도 순서 변경→A4 가로 변환→다운로드한 PDF 검증과 실패 필터를 확인했습니다. Phase 3에서는 실제 저장소 권한 오류 복구 후 수동 재시도 성공과 실패/성공 Attempt 보존, 대기 작업 취소를 확인했습니다. 별도 격리 테스트 Worker에서 실제 Redis/PostgreSQL을 사용한 자동 재시도·횟수 제한·게시 직전 취소도 검증했습니다. 원격 GitHub Actions는 정의만 갱신했고 실행하지 않았습니다. 자세한 결과는 [진행 현황](docs/PROGRESS.md)을 확인하세요.

실제 Phase 3 장애 주입 테스트는 일반 Dispatcher를 잠시 중지한 전용 테스트 프로세스에서만 실행합니다. 운영 코드에 오류 주입 플래그는 없습니다. 실행·복원 방법은 [검증 절차](docs/TEST-SCENARIOS.md)를 확인하세요.

## 설계와 남은 범위
조건부 DB Claim과 Job별 고유 Result, 상태 갱신과 동일 트랜잭션의 완료 이벤트로 중복 반영을 방지합니다. 임시 PDF를 전체 검증한 뒤 동일 볼륨에서 원자 이동하며 SUCCESS 결과만 다운로드합니다. DB와 파일시스템 사이 원자성을 보장하지는 않습니다.

**다음 Phase 4:** Lease/Heartbeat·fencing을 통한 Worker 재획득, PROCESSING/CANCEL_REQUESTED 복구, Worker 강제 종료·재시작 및 다중 Worker 장애 검증입니다. 현재 실행 세대·Attempt 소유권 검사는 재시도/취소 경합을 보호하지만, Worker가 죽었을 때 실행권한을 자동 재획득하지 않습니다. 자동 만료·청소, 사용자 인증, 모니터링, 성능 벤치마크도 아직 없습니다.

```bash
docker compose down  # 종료, 볼륨 데이터 보존
```
스택: React 19.1 / TypeScript 5.8 / Vite 6.4 / TanStack Query / Axios / Lucide / Vitest, Python 3.12 / FastAPI / SQLAlchemy / Alembic / psycopg / Celery / Redis / Pillow / pypdf, PostgreSQL 16.9 / Redis 7.4.4 / Nginx. 의존성은 기존 lockfile을 유지했으며 새 라이브러리는 추가하지 않았습니다. UI는 현재 단일 콘솔 내 업로드·이력 전환을 사용합니다.

![Phase 3 실패 및 성공 Attempt 보존](docs/screenshots/phase3-attempts.png)

[전체 요구사항](PROJECT.md) · [진행 현황](docs/PROGRESS.md) · [아키텍처](docs/ARCHITECTURE.md) · [ADR](docs/DECISIONS.md) · [API](docs/API.md) · [검증 절차](docs/TEST-SCENARIOS.md)
