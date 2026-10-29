# 개발 진행 현황

기준일: 2026-10-29 (Asia/Seoul)
현재 Phase: **Phase 7 — 자동화 테스트 및 포트폴리오 완료**.
다음 우선순위: 사용자 요청 시 커밋·푸시 후 원격 GitHub Actions 결과를 확인한다. PROJECT의 Phase 0~7 범위는 완료했으며 추가 제품 기능은 별도 범위를 정한다.

## 시작 상태와 범위
AGENTS → PROJECT → PROGRESS → DECISIONS → README를 확인했다. main과 origin/main은 821994c로 같고 작업 트리는 깨끗했다. 실제 소스와 기존 테스트·Compose/CI 정의를 비교해 Phase 6까지 완료, 저장소 Playwright E2E 부재를 확인했다. API/Worker의 변환 책임, PostgreSQL 상태·세대·Lease·Attempt·Result·오류 이력은 변경하지 않는다. 제품 DB migration은 없으며 0005를 유지한다.

## 구현한 검증과 문서
- 고정 Playwright 1.64.1 및 공식 Linux 이미지 SHA256, Compose test profile의 별도 e2e 컨테이너
- Chromium/Firefox desktop·모바일 크기 WebKit의 실제 API→Worker→PDF 4개 시나리오×3, Worker 중지 전용 대기 취소 1개×3
- TIFF/PNG 순서·A4 가로/여백, 실제 Canvas 빨강→초록→파랑·페이지 경계, 다운로드 PDF 바이트, 다른 workspace 404, 이력 UUID 검색·수평 overflow 검사
- 빈 파일·위장 PNG 거부, 실제 변환 실패/Attempt·PDF 미공개, 다운로드 네트워크 차단/복귀, 테마와 선택 작업 reload 보존
- validate_phase7.py: 활성 Job 사전 검사, 기존 smoke·Alembic·E2E·대기 취소·선택적 실제 장애 검증, 단계별 exit code/시간/로그, finally 서비스 복원·ps
- CI 공통 실행기·E2E 타입 검사·Ruff format 검사·실패 자료/보고서 7일 artifact 보존
- README 아키텍처 다이어그램, RUNBOOK 실행/복원/장애 시연, PORTFOLIO 문제·해결·근거·한계, 테스트 설명/ADR-040·041

## 실제 실행 결과
| 항목 | 결과 |
|---|---|
| Windows 백엔드 | 82 passed, 기존 TestClient httpx deprecation warning 1건 |
| Linux API 이미지 | 82 passed, 같은 deprecation 및 /app pytest cache 쓰기 권한 warning 각 1건 |
| 프런트 | 15 passed, strict TypeScript(제품+E2E)·production build 통과 |
| 정적 검증 | Ruff format/check·compileall·git diff --check 통과 |
| 의존성 | Playwright·Node 타입은 개발 의존성만 추가, npm audit 검사 시점 알려진 취약점 0건 |
| Linux 브라우저 | 최종 빈 볼륨 환경 일반 E2E **12 passed (55.1초)** + 대기 취소 **3 passed (7.7초)**, 세 브라우저 모두 통과 |
| 전체 빈 볼륨/장애 | convertflow-phase7-clean-final-20261029에서 up --build --wait·기존 smoke 1/2/6·Alembic check 통과. Phase 3 재시도/취소(4.69초), Phase 4 실제 kill/fencing/중복(55.38초), Compose Worker/Redis/DB 장애(120.64초) 모두 exit 0 |
| 복원 | 실행기 restore·services exit 0. 검증 스택은 down(볼륨 보존)하고 원래 convertflow 스택 복원 완료. API/Worker/frontend/PostgreSQL/Redis healthy, Dispatcher/Observer 실행, Worker 1개, migrate exit 0. 0005(head) 및 기존 Phase 6 Job 939c7a73… SUCCESS 보존 확인 |
| 원격 CI | 정의 갱신, 실제 GitHub Actions 실행 미수행 |

## 발견한 문제와 처리
1. Windows 호스트 Firefox의 browserType.launch spawn UNKNOWN으로 실행 전 실패했다. 공식 Linux 컨테이너에서 Chromium/Firefox/WebKit 모두 실제 실행했다. 호스트 Firefox 정상 작동을 주장하지 않는다.
2. 테스트 컨테이너가 http://frontend에 접근하면 비보안 origin이라 crypto.randomUUID가 없어 파일 선택이 실패했다. frontend 네트워크 namespace 공유+localhost 접근으로 제품의 localhost 보안 컨텍스트를 유지했다. 제품 코드나 브라우저 보안 설정을 완화하지 않았다.
3. 첫 대기 취소 E2E는 동일한 대기 중 문구가 숨겨진 상세에도 있어 strict locator 위반으로 실패했다. 상태 배지를 명시하도록 수정했다. 실패 실행의 finally 복원/ps exit 0을 확인했고 새 프로젝트/빈 볼륨에서 최종 15개 E2E 모두 통과했다.
4. Vitest가 Playwright spec을 수집하지 않도록 e2e 디렉터리를 제외하고 별도 tsconfig로 E2E도 타입 검사한다. 테스트 보고서가 Docker 빌드 컨텍스트/Git에 섞이지 않도록 제외했다.

검증 근거: [단계별 종료 코드·시간](validation/phase7.json). 재시도 Job **249face5-6d2e-452c-a107-077772d598b2**는 Attempt 5개를 보존했다. 인코딩 kill **6149fa0b-61dd-4b2c-bcd7-e08815d186a1**, 게시 kill **eb07ecdf-4ebb-4698-bb03-f969e3f1f198**, stale owner **f1bc1c0a-83cd-4200-b3b8-383dc198992d**, Compose prefork kill **ba2537dc-9605-4c59-8d02-73b3440cb995**, Redis 복귀 **dcaaf45f-c3bb-4f3c-9720-8d235b4b6a72**, PostgreSQL Lease 복구 **5e90e43a-f56f-416e-8af0-3c73311692ff**. 이 Job들은 분리한 검증 프로젝트의 보존 볼륨에 있으며 원래 브라우저 작업공간 데이터와 섞이지 않는다.

## 변경 파일
- frontend/playwright.config.ts·tsconfig.e2e.json·Dockerfile.e2e·e2e/workflow.spec.ts·e2e/README.md·합성 PNG/TIFF fixture
- frontend/package.json·package-lock.json·.dockerignore, docker-compose.yml, .gitignore
- scripts/validate_phase7.py, .github/workflows/ci.yml
- README, docs/ARCHITECTURE·TEST-SCENARIOS·DECISIONS·PROGRESS, 신규 RUNBOOK·PORTFOLIO·validation/phase7.json

## 제약과 후속 작업
실제 모바일 기기/Safari·전문 접근성 감사·장기 soak/누수·실사용 사진 성능·원격 CI 실행은 미검증이다. 빈 볼륨 검증은 같은 Windows/Docker Desktop 호스트에서 캐시된 이미지 레이어를 사용할 수 있는 별도 Compose 프로젝트이며 새 물리 머신 검증은 아니다. 기존 Phase 5 성능 원본과 한계를 유지하고 성능 수치를 새 측정으로 바꾸지 않았다.

계정/운영자 인증, 파일 만료·orphan 청소, 요청 Idempotency-Key, JSON 로그 통일은 남아 있다. 현재 localhost 개발용이다. Phase 7 완료 뒤 커밋·푸시와 원격 CI 결과 확인이 다음 작업이며, 추가 제품 기능은 별도 범위를 정한 뒤 진행한다. 현재 실행 차단 요인은 없다. 검증용 두 프로젝트의 볼륨은 보존했으며 서비스/네트워크는 down으로 종료했다. 이번 요청으로 커밋·푸시는 수행하지 않았다.

---

# Phase 6 기록 (이전 실행)


기준일: 2026-10-28 (Asia/Seoul)
현재 Phase: **Phase 6 — UI/UX 개선 완료**.
다음 우선순위: **Phase 7 — 자동화 테스트 및 포트폴리오**. 이번에는 Phase 6 범위만 구현했다.

## 시작 상태와 구현
AGENTS → PROJECT → PROGRESS → DECISIONS → README를 읽고 소스·Git 상태와 비교했다. main은 Phase 5 로컬 커밋 825723a이며 origin/main tracking보다 1개 앞서고 작업 트리는 깨끗했다. 이전 사용자 요청대로 이 미푸시 상태를 유지한다. 기존 Windows 백엔드 80개 테스트를 먼저 통과했다.

- JobDetail·UploadList·HistoryCards·EventTimeline·PDFPreview를 분리하고 고정 내비게이션/헤더·선택 Job 상세 이동/focus·skip link 제공
- 빈 파일 검사·native 썸네일/Object URL 해제·TIFF placeholder·오류 파일 제거·키보드 순서 변경/안내
- 파일 전송 100% 후 API 검증 대기와 실제 Worker 진행률을 구분. 파일/페이지 수·상태별 안내·오류 원문과 해결 행동 표시
- PDF.js 6.4.299 로컬 asset으로 실제 PDF 페이지를 Canvas에 렌더링. 권한 있는 기존 download API 사용, 32 MiB 이하·한 페이지/약 2M pixels 제한
- 페이지 전환·이전/다음 경계·닫기/재열기, 요청/render/page/document 정리. 모듈 오류는 Error Boundary로 콘솔과 다운로드를 유지
- 최신 이벤트 30개+역방향 before 커서/더 보기·오류/재시도/취소 필터. 기존 after 오름차순 API는 보존하고 종료 상태의 최종 이벤트를 재조회
- Light/Dark 초기 OS 선호·명시적 선택 저장, 모바일 화면 선택/작업 카드, 실행 전 취소를 실행 중/완료 전으로 표시하지 않음
- binary PDF 요청에서도 구조화된 API 오류를 안전하게 읽어 안내, 새로고침/다운로드 fallback 제공

## 실제 검증 결과
| 항목 | 결과 |
|---|---|
| Windows 백엔드 | **82 passed**, 기존 TestClient deprecation warning 1건 |
| 최종 Linux API 이미지 | **82 passed**, 같은 warning 1건 |
| 프런트 | **15 passed**, strict TypeScript·production build 로컬 및 Docker 통과 |
| Ruff·구문·diff | format/check·compileall·git diff --check 통과 |
| 의존성 | PDF.js 6.4.299/package-lock 고정, npm audit 알려진 취약점 0건(검사 시점) |
| Docker Compose | up --build --wait exit 0, 최종 API/Worker/frontend/PostgreSQL/Redis healthy, Dispatcher·Observer 실행, Worker 1개, migrate exit 0 |
| 스키마 | 0005(head), Alembic check 신규 변경 없음. 이번 DB migration 없음 |
| 기존 실연동 | Phase 1 단일 PDF·Phase 2 TIFF 순서/옵션/오류/권한 통과 |
| 신규 커서 실연동 | 실제 32페이지 PDF·36개 이벤트, 최신 SUCCESS·역방향 무중복/무누락·기본 ascending 호환·미인가404 통과 |
| 브라우저 미리보기 | 3페이지 A4 가로/10mm 실제 PDF의 빨강→초록→파랑, 페이지 전환·경계·닫기/재열기·테마 저장 통과 |
| 브라우저 취소·재시도 | 대기 취소 0%/Attempt0, 새 Job storage 권한 오류→복구→같은 Job #1 실패/#2 성공·이력 보존 통과 |
| 390px viewport | 같은 origin iframe에서 업로드·모바일 카드·상태 필터·상세 focus·PDF 페이지 전환·취소 실행 안 함 확인 |
| 오류 격리 | 뷰어 module 일시 누락→안내/다운로드/콘솔 유지→asset 원복·새로고침 후 미리보기 정상 복귀 |
| 원격 CI | Phase 6 smoke 정의 추가, 원격 Actions 실행 미수행 |

검증 Job: 3페이지 브라우저 **939c7a73-1217-401d-92c2-998b77b3520d**, 대기 취소 **8b5156d8-15e7-40ab-bb07-17cdf728f347**, 수동 재처리 **958c9cf2-9b4a-4475-8b55-a39c333cd218**(실패 Attempt 21888a16…/성공 2a8e4dd0…), UI 36개 이벤트 더 보기 **5bc7e29e-4008-40d0-b094-d4638c065734**, 신규 script **32f37684-bb14-4c55-ac4d-bc79af9c5d7a**. 기존 smoke **5ea4e639-c34b-4229-804d-7c42fdecb631**, TIFF **18d29fa5-37f7-42dc-a4e2-d0b5610859f6**. 토큰/쿠키 원문은 보존하지 않았다.

## 발견한 문제와 반영
1. 이전 화면은 스크롤 아래에서 메뉴/선택 Job 상세 이동이 불편했다. 고정 내비게이션과 상세 scroll/focus, 모바일 카드로 개선했다.
2. 기존 타임라인은 모든 이벤트를 매번 읽고 오래된 이벤트부터 표시했다. 최신 30개+커서로 변경하고 66개 회귀/36개 실제 이벤트에서 호환성과 무중복/무누락을 검증했다. UI에서도 30→36개 더 보기 및 수동 재시도/실패 필터 8→2개를 확인했다.
3. 완료 직전 poll에서 과거 이벤트가 반환될 가능성을 검토했다. 종료 상태 query key를 분리해 실제 SUCCESS/FAILED/CANCELLED를 다시 조회한다.
4. 모바일 카드의 null 시간은 처음에 취소도 완료 전으로 표시했다. 실행 전 CANCELLED는 실행 안 함, 실행 중·대기·기록 없음과 구분하고 회귀·실제 모바일 필터로 재검증했다.
5. PDF binary 응답 모드의 JSON 오류가 일반 연결 오류로 사라질 수 있어 작은 ArrayBuffer 오류를 파싱해 원문 안내를 유지했다. 잘못된 body는 안전하게 fallback한다.
6. PDF 모듈을 지연 로드하므로 네트워크/배포 중 모듈 누락이 콘솔 전체를 중단하지 않도록 경계를 두고 실제 asset fault로 확인했다. 설치 버전의 타입에 맞춰 PDF.js API를 적용하고 mjs MIME을 명시했다.

## 변경 파일
- 신규 UI: frontend/src/features/jobs/JobDetail.tsx·HistoryCards.tsx·EventTimeline.tsx·PDFPreview.tsx·PreviewBoundary.tsx·presentation.ts·presentation.test.ts, features/upload/UploadList.tsx, src/vite-env.d.ts
- UI 수정: app/App.tsx, style.css, features/upload/files.ts·files.test.ts, services/api.ts·api.test.ts
- 의존성/서빙: frontend/package.json·package-lock.json·nginx.conf
- Backend: app/api/routes.py(events 조회만), app/main.py(0.6.0), tests/test_phase6.py
- 실연동/CI: scripts/smoke_phase6.py, .github/workflows/ci.yml
- 문서: README, docs/PROGRESS·DECISIONS·API·ARCHITECTURE·TEST-SCENARIOS, screenshots/phase6-*.png

## 남은 제약과 다음 작업
Phase 7에서 저장소 E2E runner·cross-browser/장애 시나리오 자동화·포트폴리오를 정리한다. 이번 브라우저 검증은 세션 기반이며 실제 모바일 기기/Safari/전문 접근성 감사나 자동 Playwright suite가 아니다. 32 MiB 초과 PDF는 다운로드로 확인하고, 미리보기는 시스템이 만든 이미지 PDF의 Canvas width-fit 페이지 표시이며 text 검색·주석·PDF 편집을 제공하지 않는다. PDF bytes를 모두 받으므로 완전 streaming은 아니다.

기존 API/Worker 변환 책임·PostgreSQL 상태·Lease/세대/Attempt·재시도/오류 이력·Result 고유 확정은 변경하지 않았다. Worker 강제 종료 복구를 이번에 새로 구현/검증했다고 주장하지 않는다. 계정/운영자 인증, 자동 파일 만료·orphan 청소, Idempotency-Key, 장기 부하/누수, 로그 JSON 통일·TestClient warning은 여전히 남아 있다.

검증용 모바일 HTML은 컨테이너에서 삭제했고 뷰어 asset과 새 테스트 디렉터리 권한을 원복했다. Worker 정상 실행과 최종 0005 스키마를 확인했다. 현재 실행 차단 요인 없음. 이번 변경의 커밋·푸시는 수행하지 않았다.

2026-10-28 후속 사용자 요청으로 Phase 6 변경을 HeoSeongbin <heosb316@gmail.com> 작성자의 커밋으로 정리하고, 앞서 로컬에 보관한 Phase 5 커밋 825723a와 함께 origin/main에 게시한다. 검증 결과는 위 실제 실행 기록을 따른다.

---

# Phase 5 기록 (이전 실행)

기준일: 2026-10-28 (Asia/Seoul)
현재 Phase: **Phase 5 — 모니터링 및 성능 완료**.
다음 우선순위: **Phase 6 — UI/UX 개선**. 이번 작업은 Phase 5 범위만 구현했다.

## 시작 상태와 구현
AGENTS → PROJECT → PROGRESS → DECISIONS → README를 확인하고 실제 소스·Git 상태와 비교했다. main과 origin/main은 b2fd27c로 같았고 변경 사항이 없었다. Phase 4의 Windows 70개 테스트와 정상 Compose 실행 상태를 먼저 확인했다.

- 별도 Observer 서비스: Celery stats/active, Kombu Redis transport의 기본 큐 ready 메시지 수를 PostgreSQL 관측 테이블에 저장
- Dashboard: workspace 전체 상태 분포, 최근 60분 성공 처리량·실행/접수 시간·실패 Attempt 오류 코드·미발행 예약 통계
- Worker Monitoring: 실제 응답 ONLINE/UNKNOWN, 슬롯·활성 Task 수·현재 workspace 실행 Job·Heartbeat·최근 성과, 수집 시각
- Observer 실패·부분 응답·stale은 null/UNKNOWN, 실제 0과 구별. 다른 workspace의 Job ID·파일명·Task args는 반환하지 않음
- 현재 활성 Job은 DB Attempt의 Worker·메시지 세대·미만료 Lease가 일치해야 표시. 오래된 물리 Task를 새 실행의 Worker로 오귀속하지 않음
- 0005: 관측 테이블, 상태/Lease·workspace/완료·Attempt/완료 복합 인덱스. 기존 Job/Attempt/Event/Result·오류 보존
- RGB 변환의 불필요한 RGBA/white canvas 복사 감소. 입력·출력·다운로드·재시도 checksum을 streaming으로 변경
- 실제 메모리·인덱스·대량 파일·Worker 확장 측정 harness와 원본 보고서, CI 검증 단계 추가

## 실제 검증 결과
| 항목 | 결과 |
|---|---|
| Windows 백엔드 | **80 passed**, 기존 TestClient deprecation warning 1건 |
| 최종 Linux API 이미지 | **80 passed**, 같은 warning 1건 |
| 프런트 | **8 passed**, strict TypeScript·production build 로컬/Docker 통과 |
| Ruff·Python 구문 | format/check·compileall 통과 |
| PostgreSQL/Alembic | 0005, check 신규 변경 없음, 이전 데이터 보존 migration 회귀 통과 |
| Compose | 최종 up --build --wait exit 0. Worker 1개·Observer로 복원 |
| 큐·관측 실연동 | Worker 중지 중 ready 양수, 정상 0, 미응답 UNKNOWN, Observer 중단 후 stale null/UNKNOWN 및 복귀 통과 |
| 경계 입력 | 20파일×5프레임=100페이지, 92.16M pixels, 실제 PDF·단일 Attempt 성공 |
| Worker 확장 | 6 Job 배치, Worker 1개 6개 처리 / 2개 각각 3개 처리, 모든 PDF·단일 Attempt 검증 |
| 활성 작업 | 실제 PROCESSING Task의 Job ID·Heartbeat·Lease 관측, 타 workspace 미노출, 파일 복원 후 동일 Attempt 성공 |
| 기존 실제 회귀 | Phase 1·2 smoke 및 Phase 3 재시도/취소·Phase 4 실제 SIGKILL/SIGSTOP·중복 메시지/스케줄러·fencing 통과 |
| 브라우저 | 기존 업로드→성공→Dashboard 완료 수·평균 시간 반영, Worker ONLINE/UNKNOWN·큐 시각 확인. API 실제 중단 시 오류 안내·UNKNOWN/null 전환도 확인 |
| 원격 CI | 정의만 갱신, GitHub Actions 원격 실행 미수행 |

종료 확인: API 실제 중단 오류 화면 검증 뒤 정상 복원했고 브라우저의 큐 0/Worker ONLINE 재관측을 확인했다. API/Worker/frontend/PostgreSQL/Redis healthy, Dispatcher·Observer 실행, migrate exit 0, Worker 1개다. `alembic current` 0005(head), `alembic check` 신규 변경 없음. 현재 실행 차단 요인은 없다.

실제 활성 관측 최종 Job: **8b2dec4b-bebb-48a2-9699-df56ac160406**. 브라우저 Job: **d58bc506-59fe-4833-a8d9-6d2ea823c9b1**. Phase 1 **23c7690c-2833-4a45-a13c-ff88fc06ae75**, Phase 2 **91ae8852-d412-406d-8b4f-ca880419e53d**. Phase 3 수동 성공 **5a7f6458-4adb-4b75-a71b-96fd38e16b67**(이전 실패 4개 보존). Phase 4 encode kill **9ea26e5b-8704-4080-a1bc-966c763be1ad**, publish kill **a628922a-c464-4f22-adf8-532ff74aed06**, stale owner **269ad9c8-7c07-4eae-94db-c1418b9b7847**. 토큰·쿠키 원문은 기록하지 않았다.

## 실측 성능과 한계
- 8페이지 2048² RGB TIFF, 별도 Linux process 각 3회: peak RSS 중앙값 **163.63→115.41 MiB**(약 29.5% 감소), 실행 시간 **0.2721→0.1428초**. PDF 페이지·이미지 해시 동일.
- 64 MiB 합성 checksum: peak RSS **110.19→46.32 MiB**, digest 동일. 작업당 증분/실 Worker 전체 RSS가 아니라 해당 프로세스 최고 RSS다.
- PostgreSQL TEMP fixture 각 10만 행, warm-cache 3회 EXPLAIN 중앙값: Lease **0.193→0.055ms**, workspace 최근 완료 **1.470→0.046ms**, Attempt 최근 완료 **0.254→0.037ms**. 합성 분포의 쿼리 계획 비교로 운영 성능 보장은 아니다.
- 실제 6 Job×8페이지 1024² 배치: Worker 1개 **2.3691초**, 2개 **3.3718초**. 입력 검증·업로드·DB/poll 오버헤드가 포함된 작은 표본이며 확장 속도 향상은 확인되지 않았다. 기본 1개 유지.
- 원본 JSON·fixture·환경·표본·재현 방법은 **docs/benchmarks/README.md**, phase5-memory/indexes/load/active.json에 보존한다.

## 발견한 문제와 수정
1. Redis의 빈 큐 리스트 키 제거 때문에 Kombu passive 조회가 404를 반환했다. 설치된 transport 구현을 확인하고 표준 선언의 priority-aware 메시지 수를 사용했다. 실제 양수/0/UNKNOWN을 다시 검증했다.
2. SQLite 초 단위 DB 시각 때문에 방금 완료한 Attempt가 최근 집계에서 빠졌다. DB 시각을 밀리초로 개선하고 시간창/누락 시각 회귀를 추가했다.
3. ru_maxrss에 부모 프로세스 fixture 생성 peak가 섞여 메모리 비교가 동일하게 나왔다. 이 결과를 폐기하고 해당 exec의 VmHWM으로 각 3회 재측정했다.
4. 처음의 인덱스 fixture는 조건 선택도 차이가 없어 개선이 없었다. 실제로 구분되는 만료/최근 이력 분포를 명시하고 그 분포의 계획만 보고했다. 일반적인 가속을 주장하지 않는다.
5. 부하 스크립트 comprehension의 assignment-expression 구문 오류를 실행 전에 발견해 수정했다. compileall을 CI에 추가했다. 실패한 실행을 검증 성공으로 집계하지 않았다.
6. Task UUID만으로 Worker에 Job을 귀속하면 오래된 Task가 새 Attempt의 Heartbeat를 표시할 수 있었다. 현재 세대·Attempt Worker·Lease를 대조하고 회귀 및 최종 실제 활성 Task 검증을 수행했다.
7. API 조회 실패 중 유지되는 화면 캐시가 ONLINE/큐 수치를 계속 표시하지 않도록 화면에서도 조회 실패·stale 기준을 적용했다. 실제 0/UNKNOWN과 원본 캐시 보존·만료 경계 테스트를 추가했다.

## 변경 파일
- 신규 Backend: backend/alembic/versions/0005_monitoring.py, app/api/monitoring.py, services/observer.py, storage/checksums.py, tests/test_phase5.py
- Backend 수정: api/routes.py, converters/image_pdf.py, core/config.py, main.py, models/job.py, services/leases.py·lifecycle.py, tasks/convert.py
- 신규 UI: frontend/src/features/monitoring/Monitoring.tsx·Monitoring.test.ts, 수정 app/App.tsx·style.css
- 설정/실연동: docker-compose.yml, .env.example, .github/workflows/ci.yml, scripts/benchmark_memory.py·benchmark_indexes.py·benchmark_phase5.py·smoke_phase5_active.py
- 문서/증거: README, docs/PROGRESS·DECISIONS·API·ARCHITECTURE·TEST-SCENARIOS, docs/benchmarks/*, screenshots/phase5-dashboard.png·phase5-workers.png·phase5-api-unavailable.png

## 남은 제약과 다음 작업
Phase 6에서 업로드·진행률·이벤트·결과 미리보기 등 UI/UX를 개선한다. 이번에 전체 UI 재설계·미리보기·알림·설정 변경 기능은 추가하지 않았다. Worker 물리 실행과 논리 Job 상태, 큐 메시지와 DB 예약은 서로 다른 값이다. 네트워크 수집 시각은 서로 다르며 즉시 일치하지 않는다.

작업공간 capability만 존재하며 공개 운영용 인증/운영자 권한·할당량은 없다. 자동 파일 만료/청소·orphan 정리·Idempotency-Key·장기 부하/누수·실사용 사진 성능·저장소 Playwright runner·로그 JSON 통일·TestClient warning은 남아 있다. PDF Writer는 인코딩 객체를 보관하며 완전 streaming이 아니다. 이전 Worker 이름의 관측 기록도 자동 삭제하지 않는다.

기존 Lease·재시도·취소·원자 게시·Job/Attempt/오류 이력을 보존했고 제품 API에 변환·fault flag를 넣지 않았다. 이번 요청에서 커밋·푸시는 수행하지 않았다.

2026-10-28 후속 사용자 요청으로 검증한 Phase 5 변경을 HeoSeongbin <heosb316@gmail.com> 작성자의 로컬 커밋으로 정리한다. 푸시는 수행하지 않는다.

---

# Phase 4 기록 (이전 실행)

기준일: 2026-10-28 (Asia/Seoul)
현재 Phase: **Phase 4 — 멱등성 및 Worker 장애 복구 완료**.
다음 우선순위: **Phase 5 — 모니터링 및 성능**. 이번 변경은 Phase 4 범위다.

## 시작 상태와 구현
AGENTS → PROJECT → PROGRESS → DECISIONS → README 순서로 확인했다. main은 origin/main의 8fa16ff와 같고 변경이 없었다. 기존 Windows 백엔드 64개 테스트를 재확인했다. Docker Desktop을 기동하고 정상 서비스 상태를 확인한 뒤 구현했다.

- 0004: Job heartbeat_at/lease_expires_at nullable 컬럼·만료 조회 index, 이전 Job/Attempt/오류/결과 보존
- Claim·Heartbeat의 row lock 이후 PostgreSQL DB 시각 사용, 기본 Lease 30초·독립 Heartbeat 5초
- 세대+Attempt+미만료 Lease로 진행/실패/취소 완료/결과 확정 fencing, 만료 Lease 재갱신 금지
- Dispatcher의 3초 주기 회수, SKIP LOCKED 20개 배치, 오류 Attempt·다음 세대·Outbox 원자 저장
- WORKER_LEASE_EXPIRED는 기존 최대 3회 자동 재시도 정책을 사용하고 상한 후 FAILED/수동 재처리
- CANCEL_REQUESTED 소유권 만료 시 재실행 없이 CANCELLED, RECOVERY_REQUIRED 이벤트 보존
- 발행 후 30초 미획득 QUEUED 메시지 재발행, 원자 Claim으로 중복 메시지 억제
- DB connect/SQL/lock timeout, .env/Compose Lease 설정, API heartbeatAt/leaseExpiresAt 추가

## 실제 검증 기록
- Windows pytest **70 passed**, Ruff 통과. 프런트 **4 passed**, strict TypeScript·production build 통과. UI 레이아웃 변경 없음.
- 최종 Linux API 이미지 pytest **70 passed**, 기존 TestClient deprecation warning 1건. PostgreSQL 0004 migration 및 `alembic check` 통과.
- Compose `up -d --build --wait` exit 0. 실제 제품 API/Worker/Dispatcher를 새 버전으로 교체했다.
- 별도 실제 Celery 프로세스+PostgreSQL+Redis: 인코딩 중 SIGKILL, 파일 이동 직후/DB 커밋 전 SIGKILL, SIGSTOP 후 교체 Worker 성공 뒤 SIGCONT, 두 Worker에 동일 메시지 12회, 사망한 취소 요청 Worker 회수 전부 통과. 실패/성공 Attempt 2개, Result/SUCCESS 1개와 실제 PDF 다운로드를 검사했다.
- 정상 Compose prefork Worker 컨테이너 SIGKILL/재시작: **d4dc30b9-0a97-4005-b052-414f9af3c4a2**, 2 Attempt로 성공.
- Redis 중단 중 HTTP 업로드 접수→Outbox 보존→재기동: **b195f523-3340-4f90-ad71-4b75bab85a2b**, 1 Attempt로 성공.
- PostgreSQL 35초 중단→만료 Lease 회수→새 실행: **bed13f6a-009c-49f9-8775-e10a1a38ee76**, 2 Attempt로 성공. API·Dispatcher 재시작 후 결과 유지.
- 위 서비스 장애 harness는 새 테스트 입력만 FIFO로 교체했고 finally에서 파일·서비스를 복원했다. 볼륨/기존 사용자 데이터는 삭제하지 않았다. 원격 GitHub Actions는 정의만 갱신했으며 실행하지 않았다.
- 최종 재검증: 두 복구 스케줄러 동시 호출·게시 전 다운로드409 포함 Phase 4 실연동 통과. 인코딩 kill **0c6036d3-8f93-4138-ad9f-efb6815c5f92**, 게시 직후 kill **ad7ea982-7300-4fb1-96d2-3072809eefff**, stale owner **fb8b0c49-c8c7-4b3f-9660-604ef8e92ff2**, 두 Worker 중복 메시지 **9fb3709a-3e97-4a16-bf13-c6c6bbdd26ec**, 사망한 취소 Worker **ae221996-b61d-4f94-b890-7465ea401fc7**.
- 기존 실연동 회귀: Phase 1 smoke **8e1891b9-d12d-4468-bc27-1211f88b26df**, Phase 2 TIFF·옵션·색 순서/권한 **b9e317c0-43d9-49d7-8716-f6522c48e491**, Phase 3 자동·상한·수동/취소 전부 통과(수동 **c0b93f35-a69a-4055-a705-75fdb41dee21**, 실패4회+성공1회 보존).
- 종료 확인: API/Worker/frontend/PostgreSQL/Redis healthy, Dispatcher 실행, migrate exit 0. `alembic current` 0004(head), `alembic check` 신규 변경 없음, Ruff format/check 및 git diff --check 통과. 현재 실행 차단 요인 없음.

## 발견한 문제와 반영
1. Lease 검사 시각을 row lock 대기 전에 읽으면 대기 시간이 소유권 판정에 반영되지 않는다. Claim·Heartbeat는 잠금 획득 후 DB 시각을 읽도록 했다. 최종 게시도 같은 Job 잠금 안에서 검사한다.
2. 단순 `acks_late`만으로 DB의 PROCESSING이나 유실 메시지를 복구할 수 없다. 만료 Lease 회수와 미획득 QUEUED 재발행을 독립적으로 구현했다.
3. 초기 실연동 harness는 /tmp 실행 시 app 모듈 경로가 없어 시작하지 못했다. 명시적 PYTHONPATH=/app로 수정했다. Compose harness의 오래된 HTTP 연결 재사용 오류는 매 요청 새 연결로 수정 후 전체 재검증했다. 이 실패를 제품 복구 성공으로 집계하지 않았다.

## 변경 파일
- 신규: backend/alembic/versions/0004_leases.py, app/services/leases.py·recovery.py, tests/test_phase4.py
- Backend: core/config.py·db.py, models/job.py, services/lifecycle.py·dispatcher.py·errors.py·jobs.py, tasks/convert.py, main.py, tests/test_migration.py
- 실연동: scripts/smoke_phase4.py·smoke_phase4_compose.py, .github/workflows/ci.yml
- 설정/문서: .env.example, docker-compose.yml, README, docs/PROGRESS·DECISIONS·API·ARCHITECTURE·TEST-SCENARIOS

## 제한과 다음 작업
Phase 5에서 실제 Worker/큐/오류 지표·관측과 성능 측정을 진행한다. 이번에는 가짜 수치나 모니터링 UI를 추가하지 않았다.

Lease는 프로세스가 죽었다고 증명하지 않는다. 만료 후 이전 네이티브 변환이 잠시 겹칠 수 있지만 결과 반영을 차단한다. DB·공유 스토리지·Dispatcher가 복구되어야 재개한다. DB/파일시스템의 원자 커밋, orphan/임시 파일 자동 청소, 파일 수명 정책은 미구현이다. 결과 이동 직후 crash의 이전 Attempt 파일은 비공개 orphan으로 남을 수 있다. 장애 무한 자동 재시도는 하지 않는다.

구버전 Worker는 Lease를 모르므로 배포 전 drain/중지하고 함께 교체해야 한다. 계정 인증·요청 Idempotency-Key·할당량·공개 서비스 보안, 로그 형식 통일, TestClient deprecation, 성능 벤치마크도 남아 있다.

2026-10-28 후속 사용자 요청으로 Phase 4 변경을 HeoSeongbin <heosb316@gmail.com> 작성자의 커밋으로 정리하고 origin/main에 게시한다. 검증 결과는 위 실제 실행 기록을 따른다.

---

# Phase 3 기록 (이전 실행)

기준일: 2026-10-27 (Asia/Seoul)
현재 Phase: **Phase 3 — 실패 처리 및 재시도 완료**.
다음 우선순위: **Phase 4 — 멱등성 및 Worker 장애 복구**. 이번 작업에서 Lease/강제 종료 복구는 구현하지 않았다.

## 시작 상태
AGENTS.md, PROJECT.md, PROGRESS.md, DECISIONS.md, README를 확인하고 실제 소스·Git 상태와 비교했다. 시작 시 main은 origin/main의 3e9e139와 같고 변경 사항이 없었다. Phase 2 백엔드 42개·프런트 4개 테스트와 Ruff가 통과했다. Docker Desktop을 기동해 실제 서비스를 검증했다.

## 이번 완료 기능
- 오류 분류: 입력/옵션/원본 누락·손상과 transient 저장소·리소스·soft time limit을 구분
- 자동 재시도 최대 3회, 지수 backoff·equal jitter·상한, DB next_retry_at/Outbox 예약
- 동일 Job의 수동 재처리, 원본 존재·해시 재검증, 새 Attempt와 오류·Worker·시각·기원 보존
- INITIAL/AUTO/MANUAL/LEGACY Attempt 목록 및 페이지네이션, Event·Result의 Attempt 귀속
- Retry Center: 실패/재시도 대기 목록, 재시도 가능·불가 표시, 상세 재처리 및 이력
- 대기·예약 즉시 취소, 실행 중 취소 요청 및 페이지/게시 경계의 협조적 취소
- 실행 세대가 포함된 메시지, active_attempt_id 검사, expectedGeneration CAS로 오래된 메시지·중복 조작 차단
- 결과 경로에 Attempt UUID 사용, 취소/완료 게시의 Job row lock 직렬화
- 0003 마이그레이션으로 기존 오류·결과·과거 이벤트를 보존하고 LEGACY Attempt 이관

## 실제 검증 결과
| 항목 | 결과 |
|---|---|
| Windows Python pytest | **64 passed**, 기존 httpx TestClient deprecation warning 1건 |
| 최종 Linux API 이미지 pytest | **64 passed**, 같은 warning 1건 |
| Ruff backend/scripts | 통과 |
| 프런트 strict 타입 검사·build | 로컬 및 Docker Node 22에서 통과 |
| Vitest | 2개 파일 **4 passed**, 취소·재시도 대기 polling 정책 포함 |
| docker compose up --build --wait | 최종 exit 0 |
| 서비스 | API/Worker/frontend/PostgreSQL/Redis healthy, Dispatcher 재기동 후 실행, migrate 정상 종료 |
| PostgreSQL/Alembic | 0003, check에서 No new upgrade operations detected |
| Phase 1·2 실제 smoke | 기존 단일 이미지·다중 TIFF·옵션·PDF 다운로드·오류/권한 검증 통과 |
| Phase 3 전용 큐 실연동 | 실제 Redis/PostgreSQL + 별도 Celery solo 테스트 Worker에서 자동 재시도·상한·수동 재처리·이력·취소 전부 통과 |
| 정상 Compose Worker + 브라우저 | 실제 권한 오류 후 복구·수동 재시도 성공, 실패/성공 Attempt 보존, 대기 중 취소 통과 |
| 브라우저 다운로드 | 재처리 PDF의 정상 1페이지, 240×120pt, 원본 비율·이미지 확인 |
| GitHub Actions | Phase 3 격리 통합 step 추가, 원격 실행은 미수행 |
| 의존성 | 새 라이브러리·버전 변경 없음, 기존 lockfile 유지 |

별도 세션 테스트는 SQLite와 실 PostgreSQL을 구분한다. 전용 큐 장애 주입은 제품 설정을 변경하지 않는 별도 테스트 프로세스에서 수행했다. 정상 Compose prefork Worker의 수동 재처리도 따로 확인했다. Worker kill·Lease 복구·다중 Worker 보장으로 확대해 표현하지 않는다.

검증 Job: 자동 재시도 f2463a97-4473-4994-964a-d42fcb458c10, 자동 상한 후 수동 성공 e9f17386-595e-4817-a614-9a6bd1ed3a74(5 Attempt), 예약 취소 6e6dc6e5-676d-4088-8bb6-890505bf9953, 대기 취소 0f7fa2a7-62da-4576-93a8-4fc1db293215, 게시 직전 취소 dbcbd14a-0220-45f3-a959-8521bd5956f4. 브라우저 수동 성공 f7642835-334b-4a17-bf21-31c04f240862, 대기 취소 5f51304d-cb13-4263-ac66-8e81665e82d9. 토큰/cookie 원문은 기록하지 않는다.

## 발견한 문제와 해결
1. 실제 PostgreSQL/Redis에서 RETRY_WAIT→QUEUED 갱신을 커밋하기 전에 발행하면 Worker가 아직 RETRY_WAIT인 행을 건너뛰어 메시지가 소모될 수 있었다. Dispatcher를 QUEUED 준비 커밋과 Outbox publish의 두 트랜잭션으로 분리했다. 별도 DB 연결 가시성 테스트와 실제 즉시 소비 Worker로 재검증했다. 실패한 초기 검증 Job은 오류를 보존한 채 취소 서비스로 종료했다.
2. 과거 메시지가 새 재시도를 잘못 Claim할 수 있었다. 메시지 세대·원자 Claim·active Attempt 소유권과 요청 expectedGeneration을 도입했다. 구형 단일 인자는 1세대로만 처리한다.
3. SQLite의 naive 저장 시각과 요청 중 생성한 UTC-aware 시각으로 취소 응답의 처리 시간 계산이 실패했다. UTC 정규화로 수정하고 Windows/Linux 모두 통과했다.
4. Celery 컨텍스트 밖의 직접 task 테스트에 current_task가 없을 수 있었다. 실제 Worker hostname을 우선하고 컨텍스트가 없을 때만 호스트명으로 대체하도록 수정했다.
5. 원본이 없는 Job이 목록에서 재시도 가능으로 보이지 않도록 후보 파일을 배치 조회해 존재 여부를 반영했다. 원본 변경 여부는 POST retry에서 해시로 최종 검증한다.
6. 자동 재시도 예약 수와 lifetime Attempt 수를 구분해 UI 문구를 명확히 했다. 실행하지 않은 취소 작업의 시작 시각은 실행 안 함으로 표시한다.

## 변경 파일
- 신규: backend/alembic/versions/0003_attempts.py, backend/app/services/errors.py·lifecycle.py, backend/tests/test_phase3.py
- Backend 수정: app/api/routes.py, core/config.py, main.py, models/job.py, services/dispatcher.py·events.py·jobs.py, tasks/celery_app.py·convert.py
- 회귀/이관 테스트: backend/tests/test_flow.py·test_phase2.py·test_migration.py
- 신규 UI: frontend/src/features/jobs/AttemptHistory.tsx
- UI 수정: frontend/src/app/App.tsx, services/api.ts·api.test.ts, style.css
- 통합/CI: scripts/smoke_phase3.py, .github/workflows/ci.yml
- 문서: README, docs/API·ARCHITECTURE·DECISIONS·PROGRESS·TEST-SCENARIOS
- 화면: docs/screenshots/phase3-retry-center.png·phase3-attempts.png·phase3-cancelled.png

## 남은 제약과 다음 작업
Phase 4에서 Lease/Heartbeat·실행권한 재획득·fencing·복구 스케줄러, PostgreSQL 다중 Worker, Worker kill/재시작, Redis/DB 장애 및 결과 게시 직후 crash를 구현·검증한다. 현재 Worker가 죽으면 PROCESSING 또는 CANCEL_REQUESTED가 남을 수 있다. DB가 끊겨 실패 상태 자체를 저장하지 못하는 상황도 즉시 복구하지 않는다.

DB와 파일 이동의 원자성, orphan 결과 정리, 자동 만료·스토리지 청소는 아직 없다. 새로운 API/Worker는 함께 배포해야 하며 실행 중 구버전 Worker 교체의 자동 복구는 지원하지 않는다. 취소는 인코딩을 강제 종료하지 않는다. 입력/옵션 오류나 원본 누락은 재업로드가 필요하다.

로컬 workspace capability만 유지하며 계정 인증·할당량·API multipart 파싱 이전 스트림 제한은 후속 보강 사항이다. worker 로그 JSON 통일·TestClient deprecation, 저장소 내 Playwright E2E runner, 원격 CI 실행 및 성능 벤치마크는 미완료다. 테스트 입력은 생성한 이미지이며 실제 사용자 파일이나 자격 증명을 외부로 보내지 않았다.

2026-10-27 후속 사용자 요청으로 Phase 3 변경을 기존 작성자 HeoSeongbin <heosb316@gmail.com>의 커밋으로 정리하고 origin/main에 게시하는 작업을 진행한다. 검증 결과는 위의 실제 실행 기록을 따른다. 현재 실행 차단 요인 없음.

---

# Phase 2 기록 (이전 실행)

기준일: 2026-10-26 (Asia/Seoul)
당시 완료 범위: Phase 2. 아래는 이전 실행 시점 기록이며 현재 상태는 위 Phase 3 보고를 따른다.
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
