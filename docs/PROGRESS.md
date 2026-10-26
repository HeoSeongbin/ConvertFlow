# 개발 진행 현황

기준일: 2026-10-26 (Asia/Seoul)
현재 Phase: **Phase 2 — 다중 파일 및 작업 관리 완료**.
다음 우선순위: **Phase 3 — 실패 처리 및 재시도**. 이번 작업에서 Phase 3 기능은 구현하지 않았다.

## Git 관리 시작
2026-10-26 사용자 요청으로 로컬 main 브랜치와 origin(https://github.com/HeoSeongbin/ConvertFlow.git)을 설정했다. 작성자는 HeoSeongbin <heosb316@gmail.com>이며 프로젝트 로컬 설정만 사용한다. 기존 Phase 2 검증 결과를 첫 커밋에 포함하고 .env·가상환경·node_modules·빌드/임시 파일은 제외한다. 아래 Git 미초기화 언급은 이전 개발 실행 시점의 기록이다.

## 시작 시 문서·소스 비교
AGENTS.md → PROJECT.md → PROGRESS.md → DECISIONS.md → README.md 순서로 확인했다. 코드·API·DB는 기록된 Phase 1과 일치했다. 기존 Linux pytest 16개, 프런트 테스트 1개·빌드·Ruff를 다시 통과한 뒤 Phase 2를 선정했다. 작업 폴더는 여전히 Git 저장소가 아니며 init/commit/push는 수행하지 않았다.

## 이번 완료 기능
- 다중 이미지 업로드, 전달 순서 유지, 프런트 위·아래 이동·개별/전체 제거·파일별 오류 표시
- 다중 페이지 TIFF 전체 검증과 파일/프레임 순서에 따른 단일 PDF 생성
- 타입화된 PDF 옵션: 원본/A4/Letter, 자동·세로·가로, 여백, contain/cover, JPEG 품질
- 파일·페이지 집계 및 완료 페이지에 따른 실제 진행률, 현재 처리 단계와 처리 시간
- 작업 목록·파일명/UUID 검색·상태 필터·페이지네이션, 상세 입력·설정·결과 메타데이터
- QUEUED/PROCESSING/PAGE_PROCESSED/PDF_VALIDATED/SUCCESS/FAILED의 영속 이벤트 타임라인
- 실패 시 오류 코드·메시지·예외 종류·완료한 페이지 수 보존, 부분 PDF 비공개
- conversion_job_file/result/event 정규화, Alembic 0002 및 기존 데이터 backfill
- 작업공간 capability로 목록/상세/이벤트/다운로드를 서버에서 제한하고 기존 개별 Job 토큰 호환 유지
- 기존 원자 Claim을 보존하고 Result Job 고유 제약·같은 트랜잭션의 성공 이벤트로 중복 반영 방지

## 실제 검증 결과
| 항목 | 이번 실행 결과 |
|---|---|
| Windows 백엔드 pytest | **42 passed**, httpx TestClient deprecation 1건 |
| Linux 최종 API 이미지 pytest | **42 passed**, 같은 deprecation 1건, cacheprovider 비활성화 |
| Ruff backend/scripts | 통과 |
| TypeScript strict 검사 | npm run lint 및 빌드 통과 |
| Vitest | 2개 파일 **4 passed** |
| production build | 로컬 Vite 및 Docker Node 22에서 통과 |
| docker compose up --build --wait | 최종 exit 0, API/Worker/PostgreSQL/Redis/frontend healthy, Dispatcher 실행, migrate exit 0 |
| Alembic | PostgreSQL 0001→0002 적용, 최종 check에서 신규 변경 없음 |
| 기존 PostgreSQL 데이터 | 성공 Job 3건 보존, 파일/결과 backfill 및 LEGACY_IMPORTED 3건 확인 |
| Phase 1 실제 smoke | 단일 PNG → Redis → Linux Worker → 유효 PDF 1페이지 통과 |
| Phase 2 실제 smoke | 2파일·3페이지 순서/Letter 가로/10mm/cover/품질75, 목록·이벤트·권한 격리, 실패 이력·다운로드 차단 통과 |
| 브라우저 실제 사용 | 다중 선택·재정렬·옵션·업로드·성공 폴링·다운로드·검색·상세·실패 필터·이벤트 확인 |
| 브라우저 다운로드 PDF | pypdf로 3페이지, A4 가로, 재정렬한 초록/파랑/빨강 확인 |
| 의존성 | 신규 추가/버전 변경 없음. 기존 lockfile 유지. 보안 감사 수치는 이전 실행 기록 참조 |
| GitHub Actions | Phase 2 smoke 정의 추가, 원격 실행은 미수행 |

테스트는 SQLite 컴포넌트 테스트, 실제 PostgreSQL 마이그레이션, Redis/Celery smoke, 실제 브라우저 검증을 구분한다. 동시 중복 호출 테스트의 SQLite 결과를 PostgreSQL 다중 Worker/장애 복구 보장으로 확대 해석하지 않는다.

검증 Job: Phase 2 통합 성공 12cb7ae3-96e1-4ff2-a881-93637f368864, 실패 c2853811-feae-45e7-9608-c45c3f118e5a. 브라우저 성공 3e85fad9-ea2d-424d-949e-ab340c3298f3, 실패 45a3385a-98ee-4a0e-8995-3aad209a3797. 접근 토큰/cookie 원문은 기록하지 않는다.

## 발견한 문제 및 해결
1. 기존 API는 단일 파일·단일 프레임만 허용하고 Job 컬럼에 입력/출력 정보를 담았다. 신규 테이블과 데이터 보존 마이그레이션으로 확장했다.
2. 전체 작업 목록 공개는 기존 작업별 토큰 보안을 약화시킨다. HttpOnly 작업공간 cookie의 해시로 먼저 소유 범위를 제한했다. 기존 소유자 미상 작업은 임의로 편입하지 않았다.
3. 큰 원본 여백은 출력 영역을 음수로 만들 수 있다. 변환 엔진에서 INVALID_OPTIONS로 실패시키고 오류와 이벤트를 남긴다. UI에 사전 안내한다.
4. 브라우저에서 파일을 다시 선택할 때 FileList를 지연 updater가 읽기 전 초기화해 목록이 사라지는 문제를 발견했다. 이벤트 안에서 즉시 배열을 복사하도록 수정하고 최종 빌드에서 재선택·실행을 확인했다.
5. 실패 과정의 부분 PDF 또는 페이지 검증 이전 완료 표시를 막기 위해 전체 페이지 검증·원자 이동·DB 확정 전에는 SUCCESS/100을 설정하지 않는다. 실패한 task를 다시 호출해도 실패 이력은 바뀌지 않는다.

## 생성·수정 파일
- Backend: app/core/config.py, app/main.py, app/models/job.py, app/api/routes.py, app/converters/image_pdf.py, app/tasks/convert.py, app/services/validation.py
- 신규 Backend 서비스/스키마: app/services/jobs.py·events.py, app/schemas/__init__.py·options.py
- DB: backend/alembic/versions/0002_multi_image.py
- 테스트: backend/tests/test_flow.py 수정, test_phase2.py·test_migration.py 추가
- Frontend: src/app/App.tsx, src/services/api.ts, src/style.css, nginx.conf
- 신규 Frontend: src/features/upload/files.ts·files.test.ts
- 통합/CI: scripts/smoke_phase2.py, .github/workflows/ci.yml
- 문서: README.md, docs/PROGRESS.md·DECISIONS.md·ARCHITECTURE.md·API.md·TEST-SCENARIOS.md
- 화면: docs/screenshots/phase2-upload.png·phase2-history.png·phase2-failure.png

## 남은 제약 및 다음 작업
- Phase 3: 오류 분류 정비, 일시 오류 backoff/jitter 자동 재시도, 동일 Job 아래 새 Attempt와 재시도 이력, 수동 재처리, Retry Center, 취소 요청/취소 완료를 구현한다. 현재 retry/cancel/attempts API는 없다. 기존 실패 이벤트를 지우거나 덮어쓰면 안 된다.
- Phase 4: Lease/heartbeat/fencing, PROCESSING 복구, Worker kill, 다중 Worker 및 DB/Redis 장애 테스트. 현재 자동 복구를 지원한다고 표시하지 않는다.
- 파일과 DB 사이 원자성, orphan 결과 정리 및 자동 만료·청소는 미구현이다. 0002 downgrade는 다중 파일/이력 유실 방지 목적으로 차단했다.
- workspace cookie는 로컬 capability이며 계정 인증이 아니다. cookie 삭제 시 작업 목록 접근 권한이 사라진다. 기존 Phase 1 작업은 개별 토큰으로 접근한다.
- API 직접 포트의 multipart 파싱 이전 스트림 제한·사용자 할당량, 공개 서비스 인증은 미구현이다. 로컬 loopback 실행을 유지한다.
- 브라우저 상호작용을 실제 검증했지만 저장소에 Playwright E2E runner는 추가하지 않았다. CI는 단위/빌드/실제 Compose smoke 정의만 있으며 원격 실행 이력은 없다.
- Celery/Uvicorn 자체 로그 JSON 통일과 httpx TestClient deprecation은 후속 정비 항목이다. 모니터링·성능 수치·PDF 미리보기는 이번 범위가 아니다.
현재 Phase 2 실행 차단 요인 없음.

---

# Phase 0·1 기록 (이전 실행)

기준일: 2026-10-26 (Asia/Seoul)
당시 완료 범위: Phase 0 및 Phase 1. 아래는 이전 실행 시점의 기록이며 현재 상태는 위의 Phase 2 보고를 따른다.
초기 폴더에는 파일과 Git 저장소가 없었다. Git init/commit/push는 수행하지 않았다.

## 완료 기능
- 원본 개발 지시서를 PROJECT.md에 보존하고 AGENTS.md, README, 아키텍처, ADR, API, 검증 문서를 생성했다.
- FastAPI와 Linux Celery Worker를 별도 프로세스로 구성했다.
- PostgreSQL Job + Outbox 영속화와 Alembic 초기 마이그레이션을 추가했다.
- Redis에는 UUID만 전달하고 Dispatcher가 미발행 Outbox를 재시도한다.
- 단일 PNG/JPEG/BMP/WEBP/TIFF 업로드, UUID 저장 경로, 실제 포맷·MIME·확장자·파일 크기·픽셀·프레임 검증을 구현했다.
- Pillow PDF 변환, EXIF 방향·투명 배경 처리, pypdf 결과 검증, atomic rename, 해시 저장을 구현했다.
- 조건부 Claim으로 QUEUED 작업만 실행하며 시간 기반 가짜 진행률을 사용하지 않는다.
- 상태 조회와 토큰 기반 PDF 다운로드 및 결과 손상 검증을 구현했다.
- 한국어 React 화면에 파일 선택·Drop·업로드 진행률·상태 폴링·오류·다운로드·테마·반응형 레이아웃을 구현했다.
- Compose, Linux 이미지, 공유 볼륨, loopback 바인딩, healthcheck, 자동 migration, CI 정의, smoke 스크립트를 추가했다.

## 실제 검증 결과
| 항목 | 결과 및 범위 |
|---|---|
| Windows Python 3.12 pytest | 16 passed, 1 deprecation warning |
| Linux API 이미지 pytest | 16 passed, httpx deprecation 및 읽기 전용 앱 경로의 pytest cache warning |
| Ruff backend/scripts | 통과 |
| 프런트 strict 타입 검사 | npm run lint 통과 |
| 프런트 production build | Vite 6.4.5 통과, Docker Node 22에서도 통과 |
| Vitest | 1 passed, 종료 상태 폴링 정책 검증 |
| npm audit | 최종 알려진 취약점 0건 |
| pip-audit | 최종 알려진 취약점 0건 |
| pip check | Windows 및 Linux에서 의존성 충돌 없음 |
| docker compose config | 통과 |
| docker compose up --build --wait | 최종 exit 0. API/Worker/PostgreSQL/Redis/frontend healthy, Dispatcher 실행, migrate exit 0 |
| 실제 통합 smoke | HTTP PNG 업로드 → DB → Outbox → Redis → Linux Celery → SUCCESS → PDF 다운로드 → pypdf 1페이지 검증 통과 |
| 실제 DB/로그 확인 | Worker received/converting/success 및 DB SUCCESS, progress 100, output_size 2716 확인 |
| 브라우저 화면 | http://localhost:8080 표시 확인, docs/screenshots/upload.png 저장 |
| GitHub Actions | 정의만 작성. 원격 CI 실행은 미수행 |
| 전체 브라우저 업로드 E2E | 미수행. API 전체 흐름 및 화면 렌더링을 각각 검증 |

단위/컴포넌트 테스트는 SQLite를 사용하며 실제 PostgreSQL·Redis 전달 검증과 구분했다. 실제 통합 smoke는 별도 Redis/Celery Linux 컨테이너를 사용한다. Worker task를 직접 호출하는 단위 테스트를 실제 Celery 전달 성공의 근거로 사용하지 않았다.

## 발견한 오류와 해결
1. 시스템 Python 3.14 대신 번들 Python 3.12.14 venv로 안정 호환 환경을 만들었다. ensurepip 실패는 시스템 pip의 --python 대상 설치로 해결했다.
2. 샌드박스 임시 SQLite 접근 실패는 승인된 환경 재실행으로 해결했다. Linux 이미지에서도 별도로 통과했다.
3. Docker 엔진 미기동 및 CLI desktop start의 레지스트리 오류는 설치된 Docker Desktop 실행으로 해결했다.
4. 초기 의존성 취약점은 수정된 Axios/Vite/Vitest/FastAPI/Starlette/Pillow/pypdf/multipart/pytest 버전으로 교체했다.
5. Nginx localhost IPv6 healthcheck 실패를 IPv4 127.0.0.1로 수정했다.
6. API 컨테이너 재생성 후 Nginx의 이전 upstream IP 캐시로 발생한 502를 Docker DNS resolver와 variable proxy_pass로 수정했다. 프런트 healthcheck도 실제 API readiness를 확인한다. API를 강제 재생성한 후 smoke를 다시 통과했다 (Job c30e883b-b5b3-4802-8f6f-866e4e6fef82).

## 생성·수정 파일
- 루트: PROJECT.md, AGENTS.md, README.md, docker-compose.yml, .env.example, .gitignore
- 문서: docs/PROGRESS.md, DECISIONS.md, ARCHITECTURE.md, API.md, TEST-SCENARIOS.md, screenshots/upload.png
- Backend: requirements.txt 및 requirements.lock.txt, Dockerfile, .dockerignore, alembic.ini, alembic/env.py, alembic/versions/0001_initial.py
- Backend 코드: app/main.py, api/routes.py, core/config.py·db.py·logging.py, models/job.py, converters/image_pdf.py, services/validation.py·dispatcher.py, storage/local.py, tasks/celery_app.py·convert.py 및 패키지 __init__.py
- 테스트: backend/tests/conftest.py 및 test_flow.py
- Frontend: package.json 및 package-lock.json, tsconfig.json, vite.config.ts, index.html, Dockerfile, nginx.conf, .dockerignore, src/main.tsx, app/App.tsx, services/api.ts·api.test.ts, style.css
- 검증/CI: scripts/smoke.py, .github/workflows/ci.yml

## 최종 주요 버전
Python 3.12, React 19.1.0, TypeScript 5.8.3, Vite 6.4.5, TanStack Query 5.76.1, Axios 1.20.0, Vitest 5.0.5.
FastAPI 0.162.0, Starlette 1.10.0, Pydantic 2.11.4, SQLAlchemy 2.0.41, Alembic 1.15.2, psycopg 3.2.9, Celery 5.5.2, redis-py 5.2.1, Pillow 13.0.0, pypdf 6.21.2. 전체 전이 버전은 lockfile 참조.
PostgreSQL 16.9, Redis 7.4.4, Nginx 1.27, Docker frontend build Node 22.

## 남은 제약
- 단일 파일·단일 프레임만 지원한다. TIFF 다중 페이지와 출력 옵션은 Phase 2다.
- 전체 작업 목록·사용자 계정·이벤트·Attempt 이력·재시도·취소·모니터링·미리보기는 미구현이다.
- Worker 중단 후 PROCESSING 자동 복구, Lease, fencing, 동시 다중 Worker 보장은 미구현이다. Worker kill 복구 테스트를 수행하지 않았다.
- 파일과 DB 사이 원자성은 없으며 결과 게시 직후 crash 처리도 Phase 4다.
- 파일 자동 만료·청소가 없다. 작업별 capability 외에 사용자 인증은 없다. 공개 서비스가 아닌 loopback 로컬 실행용이다.
- 클라이언트는 현재 탭의 작업 접근 정보만 보존한다. 서버 목록 기능은 아직 없다.
- 앱 JSON formatter를 제공하지만 Celery/Uvicorn의 자체 로그 형식까지 통일하지 않았다.
- 요구된 전체 스택 중 Router/Zustand/Hook Form/Zod/Recharts/Tailwind는 단일 화면 Phase 1에 도입하지 않았으며 ADR-009에 기록했다.
- pytest httpx 관련 deprecation warning은 기능 실패가 아니며 후속 테스트 런타임 정비 항목이다. 성능 벤치마크와 장애 복구 보장은 아직 없다.

## 다음 작업과 차단 요인
현재 실행 차단 요인 없음. 다음 Phase 2에서 파일/결과 테이블 분리, 다중 업로드와 순서, 다중 페이지 TIFF, 출력 옵션, 목록·상세·이력을 구현한다. Phase 3 재시도·취소, Phase 4 Lease/fencing/장애 복구는 이후 진행한다. 이번 실행은 Phase 2 기능을 구현하지 않았다.
