# 기술적 결정 (ADR)

## ADR-001 PostgreSQL과 Redis 역할 분리 — 채택
DB는 영속 상태·메타데이터를 보유하고 Redis는 Job UUID 메시지만 전달한다. Celery 결과 백엔드는 사용하지 않는다. API 완료와 변환 완료를 분리한다.

## ADR-002 Transactional Outbox — 채택
Job과 Outbox를 동일 트랜잭션에 저장한다. Dispatcher가 미발행 레코드를 잠그고 발행 성공 이후 published_at을 기록한다. 브로커 장애 시 재시도한다. 발행 후 DB commit 실패는 중복 전달을 허용한다. 정확히 한 번 전달을 주장하지 않는다.

## ADR-003 Acknowledgment 및 시간 제한 — Phase 1 기본값
acks_late=true, reject_on_worker_lost=true, prefetch=1, concurrency=1. Soft 120초, Hard 150초, Redis visibility_timeout=300초. hard limit보다 visibility가 길어 정상 실행 중 조기 재전달을 줄인다. 메시지 유실·재전달과 DB PROCESSING 상태의 복구는 별개의 문제다. 실제 Worker kill 검증과 Lease 복구는 Phase 4에서 수행한다.
공식 참고: [Celery Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html), [Celery configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html).

## ADR-004 상태 전환과 멱등성 — 부분 채택
조건부 UPDATE WHERE status=QUEUED로 Claim한다. 동일 메시지를 두 번 실행한 테스트에서 성공 결과를 덮어쓰지 않는다. 최종 목표는 attempt UUID + lease heartbeat + fencing token이다. 현재 구현은 오래된 Worker와 재획득 Worker의 경합을 처리하지 않으므로 복구를 지원한다고 표현하지 않는다.

## ADR-005 공유 스토리지 — 채택
API·Worker·Dispatcher가 Docker named volume을 공유한다. 원본 이름은 표시용이며 저장 경로는 UUID다. Path.resolve containment 검증과 동일 볼륨 os.replace를 사용한다. 결과 게시와 DB 상태 갱신 사이의 크래시는 Phase 4에서 처리한다.

## ADR-006 진행률 — 채택
실제 완료 단계만 표시: 대기 0, 입력 획득 10, 변환·PDF 검증 95, 결과 게시 및 상태 확정 100. 라이브러리 내부 인코딩 진행률은 제공하지 않는다. 업로드 진행률은 Axios 전송량 기준으로 별도 표시한다.

## ADR-007 변환 엔진 — 채택
단일 이미지 MVP에는 Pillow PDF writer와 pypdf 검증을 사용한다. PNG/JPEG/BMP/WEBP/TIFF 디코더를 허용하며 EXIF 방향과 alpha 합성을 처리한다. 원본 비율을 유지하고 96 DPI로 출력한다. 다중 페이지와 A4/Letter 옵션은 Phase 2다. 대형 파일 메모리 사용은 25M 픽셀 제한 및 Worker 메모리 제한으로 제어한다.

## ADR-008 파일 보관 및 삭제 — 로컬 개발 정책
자동 만료와 삭제는 미구현이며 볼륨 수명 동안 보관한다. 실패 임시 PDF는 정리한다. 원본은 실패 분석을 위해 남긴다. `docker compose down`은 데이터를 보존하고 `down -v`는 모든 볼륨을 삭제하므로 명시적으로 폐기할 때만 사용한다. 자동 정리 도입 시 DB tombstone 후 파일 삭제 및 재시도 정책을 설계한다.

## ADR-009 Phase 범위 및 프런트 스택
Phase 1은 React strict TypeScript, Vite, TanStack Query, Axios, Lucide 및 일반 CSS로 최소 화면을 구성한다. 화면이 하나이므로 Router/Zustand/React Hook Form/Zod/Recharts/Tailwind는 아직 추가하지 않는다. 해당 기능이 생기는 후속 Phase에서 도입한다. 초기 의존성 검사 결과를 반영해 취약점 수정 버전으로 교체하고 lockfile을 저장한다.

## ADR-010 실행 환경
컨테이너 Python 3.12, Node 22, PostgreSQL 16, Redis 7.4 및 Nginx를 사용한다. FastAPI 공식 권고처럼 자체 Python 베이스 이미지를 구성한다: [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/). 호스트 Python 3.14 대신 번들 Python 3.12 환경에서 호환성 테스트를 진행한다. API readiness는 PostgreSQL과 Redis를 확인하며 Worker readiness는 별도 inspect ping으로 확인한다. Worker 목록·큐 추정 수치를 UI에 표시하지 않는다.


## ADR-011 의존성 보안 재검증
초기 설치 후 npm audit 및 pip-audit에서 발견된 항목을 수정했다. Axios 1.20.0, Vite 6.4.5, Vitest 5.0.5, FastAPI 0.162.0, Starlette 1.10.0, Pillow 13.0.0, pypdf 6.21.2, python-multipart 0.0.32, pytest 9.1.1로 갱신 후 테스트·빌드를 재실행했다. 최종 npm audit와 pip-audit는 알려진 취약점 0건을 보고했다. 이는 검사 시점 데이터 기준이며 미래 취약점 부재를 보장하지 않는다. 컨테이너는 전이 의존성 lockfile로 설치한다.


## ADR-012 프록시 서비스 주소 재해석
Nginx가 시작 시 해석한 API IP를 계속 참조해 API 컨테이너 교체 후 502를 반환했다. Docker DNS 127.0.0.11을 resolver로 지정하고 variable proxy_pass로 5초 주기 재해석한다. healthcheck는 IPv4를 사용하고 정적 index 대신 /health/ready의 실제 프록시 응답을 확인한다.


## ADR-013 Phase 2 정규화 및 기존 데이터 보존 — 채택
conversion_job_file, conversion_result, conversion_event를 추가하고 options·파일/페이지 집계·stage를 Job에 추가한다. 0002가 기존 단일 입력/결과를 backfill하며 원래 Job UUID·상태·오류·출력 해시는 보존한다. 구형 컬럼은 호환용으로 유지한다. 과거 단계 이력을 추정하지 않고 LEGACY_IMPORTED만 추가한다. 다중 파일 정보를 잃는 downgrade는 명시적으로 차단한다. 실제 PostgreSQL의 기존 성공 작업 3건과 SQLite의 성공/실패/대기 이관 테스트로 확인했다.

## ADR-014 목록 접근 권한 — 로컬 capability workspace
작업 전체를 공개하는 목록을 만들지 않는다. 정상 업로드 시 secrets.token_urlsafe(32) 쿠키를 설정하고 SHA256만 Job에 저장한다. HttpOnly, SameSite=Lax, 30일, /api/v1 경로이며 localhost HTTP 개발용이라 Secure는 사용하지 않는다. 목록은 cookie 소유 Job만 반환한다. 상세·이벤트·다운로드는 기존 개별 X-Job-Token 또는 cookie를 허용한다. 소유자 미상의 legacy 작업을 최초 접속자에게 주지 않는다. 사용자 계정 인증·비밀번호·공유 권한은 후속 보안 설계 대상이다.

## ADR-015 출력 옵션 및 변환 엔진 확장 — 채택
새 의존성을 추가하지 않고 Pillow의 이미지 디코딩/페이지 인코딩과 pypdf의 변환 행렬·cropbox를 결합한다. TIFF는 파일 내부 프레임 순서, 파일들은 multipart 순서를 유지한다. 원본은 96 DPI, A4는 210×297mm, Letter는 612×792pt다. contain은 비율 유지 전체 맞춤, cover는 중앙 crop 후 여백 내부를 채운다. quality는 Pillow PDF에 포함하는 JPEG 인코딩 품질이다. EXIF 방향과 투명 배경 흰색 합성을 보존한다. Pydantic 옵션 모델로 미지원 필드/범위를 거부한다. 원본 크기에 여백을 넣을 공간이 없으면 전체 Job을 INVALID_OPTIONS로 실패시킨다.
참고: [Pillow TIFF/PDF](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html), [pypdf 변환과 cropbox](https://pypdf.readthedocs.io/en/6.7.2/user/cropping-and-transforming.html).

## ADR-016 페이지 진행률과 변경 불가 이벤트 — 채택
진행률은 10+floor(75×완료 페이지/전체 페이지)이며 인코딩 라이브러리의 시간 기반 가짜 진행률을 만들지 않는다. 페이지 처리 완료 시 Job 갱신과 이벤트 추가를 같은 트랜잭션에 둔다. 완료 Result와 SUCCESS 이벤트도 같은 트랜잭션으로 저장하며 Result의 Job ID에 고유 제약을 둔다. sequence는 Job row update lock 안에서 부여한다. 순차 및 동시 중복 호출에서 결과/완료 이벤트가 1개임을 SQLite 테스트로 확인했으며, PostgreSQL 다중 Worker 장애 보장을 주장하지 않는다.

## ADR-017 다중 업로드 리소스 정책 — 채택
파일 20개, 개별 20 MiB, 합계 100 MiB, 합계 100페이지, 페이지당 25M 및 합계 100M 픽셀을 제한한다. TIFF 외 다중 프레임은 거부한다. 모든 페이지를 검증하고 업로드가 하나라도 실패하면 전체 DB 트랜잭션을 생성하지 않고 이번 요청 파일을 정리한다. Nginx 상한은 multipart 오버헤드를 포함해 101 MiB다. API 직접 포트의 multipart 파싱 이전 스트림 제한·사용자 할당량은 아직 없으며 공개 서비스 전에 보강한다.

## ADR-018 브라우저 파일 선택 생명주기 — 수정
브라우저 재선택 테스트에서 React 지연 updater가 FileList를 읽기 전에 input.value 초기화로 목록이 비는 문제를 발견했다. 이벤트 handler 안에서 File 배열과 entry를 즉시 캡처하고 updater에는 안정된 배열만 전달한다. 새 빌드에서 같은 이미지 재선택·옵션 조정·실행을 재확인했다. 작업 이력은 서버 DB 기준이며 현재 선택 ID만 sessionStorage에 저장한다.

## ADR-019 Phase 2 범위 — 채택
실패 원인은 Job과 Event에 보존하고 임시 결과를 비공개 처리한다. 재시도·취소·Attempt 모델은 Phase 3 범위이며 이번에 제공하지 않는다. 기존에 Attempt/재시도 이력이 없었으므로 이를 만들어낸 것으로 표시하지 않는다. 다음 Phase에서 동일 Job 아래 새 Attempt를 추가하고 기존 실패 이벤트를 유지해야 한다. UI는 단일 콘솔 내 업로드/이력 전환을 사용하며 Router·전역 상태·차트는 필요한 후속 Phase에 도입한다.
