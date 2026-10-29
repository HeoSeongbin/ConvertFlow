# ConvertFlow 포트폴리오

이미지 업로드와 PDF 생성을 분리하고, 프로세스와 메시지가 중복되거나 사라져도 작업 이력을 유지하는 비동기 문서 처리 플랫폼이다. React·FastAPI·Celery·Redis·PostgreSQL을 Docker Compose로 실행한다.

## 해결한 문제

**DB 저장과 큐 발행 사이 장애:** Job·원본 메타데이터·Outbox를 하나의 PostgreSQL 트랜잭션으로 저장한다. 별도 Dispatcher가 발행하고 미발행·장기 미획득 메시지를 재전달한다. 브로커 발행과 DB commit의 원자성은 가정하지 않는다.

**중복 전달과 늦게 돌아온 Worker:** 조건부 Claim과 실행별 Attempt, DB 시각 Lease·독립 Heartbeat를 사용한다. 세대·Attempt·미만료 Lease를 검사해 오래된 실행의 결과 게시를 거절한다. 물리 연산이 중복될 수 있어도 최종 Result와 SUCCESS 이벤트는 하나다. exactly-once 실행을 주장하지 않는다.

**재시도로 사라지는 오류:** Job과 Attempt를 분리해 최초/자동/수동 실행의 오류·Worker·시각을 보존한다. 새 세대와 Outbox 예약을 같은 트랜잭션으로 기록하고, API는 변환을 실행하지 않는다.

**모니터링이 본 처리에 미치는 영향:** Observer가 큐·Worker를 수집해 DB에 저장하며 API는 관측 캐시와 workspace 집계를 읽는다. 수집 실패나 오래된 응답은 UNKNOWN으로 표시한다.

**UI와 실제 상태의 차이:** 업로드 바이트 진행률과 페이지 기반 변환 진행률을 분리한다. SUCCESS 및 결과 검증 뒤에만 100%를 표시한다. 인증된 결과를 로컬 PDF.js로 렌더링하고 오류·재시도·취소 타임라인을 제공한다.

## 5분 기능 시연

1. [실행 안내](../README.md)에 따라 Compose를 기동한다.
2. `frontend/e2e/fixtures/pages.tiff`와 `cover.png`를 선택하고 cover를 위로 옮긴다. A4·가로·10mm를 지정해 변환한다.
3. 상세에서 실제 3페이지 완료를 확인하고 미리보기에서 빨강→초록→파랑을 확인한다. PDF를 다운로드한다.
4. 작업 이력에서 UUID를 검색하고 실행 Attempt·이벤트·Dashboard를 확인한다.
5. 작은 cover 이미지를 원본 크기·50mm 여백으로 새 변환한다. 실패 원인과 실행 이력, 결과 다운로드 미제공을 확인한다.

장애 복구 시연은 별도 시간을 두고 [실행 절차](RUNBOOK.md)를 따른다. 기본 Lease 30초와 재시도 지연이 있어 즉시 복구되지는 않는다.

## 검증 근거

- 단위·통합 테스트: 변환 순서/옵션·입력 검증·API 권한·마이그레이션·Claim/Lease/fencing·재시도·취소·관측·역방향 커서
- Playwright: 실제 API→Worker→PDF의 세 브라우저 E2E, 모바일 크기 WebKit, 네트워크 실패와 복귀, 대기 취소
- 실제 프로세스/서비스 장애: SIGKILL·SIGSTOP·prefork Worker 종료·Redis·PostgreSQL 중단과 복귀, 중복 메시지/스케줄러
- [성능 원본](benchmarks/README.md): RGB 변환 peak RSS 중앙값 163.6→115.4 MiB, checksum 110.2→46.3 MiB. 합성 데이터·환경·표본 한계를 함께 공개한다. 작은 6 Job 부하는 Worker 2개가 더 느려 기본 1개를 유지했다.
- 각 실행 결과와 미검증 범위는 [PROGRESS](PROGRESS.md)에 기록한다. CI 정의와 원격 CI 실행 결과는 구분한다.

## 설계 자료와 남은 과제

[아키텍처·ERD](ARCHITECTURE.md) · [ADR](DECISIONS.md) · [API](API.md) · [테스트 시나리오](TEST-SCENARIOS.md)

계정/운영자 인증, 파일 자동 만료·orphan 정리, 요청 Idempotency-Key, 장기 soak·누수, 실제 모바일 기기·Safari 검증은 남아 있다. 파일시스템 이동과 DB commit은 단일 원자 트랜잭션이 아니며 오래된 비공개 파일이 남을 수 있다. 현재 localhost 개발용이며 공개 운영 준비 완료를 주장하지 않는다.
