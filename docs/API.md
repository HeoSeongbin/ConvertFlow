# Phase 3 API 계약
기본 경로 `/api/v1`, OpenAPI `/openapi.json`, Swagger `/docs`. 기존 단일 파일 multipart와 X-Job-Token을 유지한다.

## 업로드
`POST /api/v1/jobs` → 202
- multipart `file`을 1~20회 반복한다. 전달 순서가 PDF 파일 순서다. TIFF 프레임은 파일 내부 순서를 유지한다.
- multipart `options`는 JSON 문자열이며 생략 시 아래 기본값이다.
```json
{"pageSize":"original","orientation":"auto","marginMm":0,"fit":"contain","quality":90}
```
pageSize: original/A4/Letter, orientation: auto/portrait/landscape, marginMm: 0~50 유한 수, fit: contain/cover, quality: 1~100 정수. 알 수 없는 필드는 거부한다. 원본 크기의 여백 적합성은 Worker에서도 검사하며 부적합하면 INVALID_OPTIONS 실패를 기록한다.

응답은 Job 요약 + accessToken이다. 첫 정상 요청에서 cf_workspace 쿠키를 생성하며 HttpOnly/SameSite=Lax, 경로 /api/v1, 30일이다. 해시만 DB에 보관한다. 업로드 중 하나라도 실패하면 전체 Job·Outbox를 생성하지 않고 이번 요청의 저장 파일을 정리한다.

제한: 개별 20 MiB, 합계 100 MiB, 20파일, 합계 100페이지, 페이지당 25M 픽셀, 합계 100M 픽셀. 확장자·실제 포맷·MIME을 일치시킨다. PNG/JPEG/BMP/WEBP/다중 페이지 TIFF 지원. 다른 애니메이션 포맷은 거부한다. Nginx 요청 상한은 multipart 오버헤드를 포함해 101 MiB다. API의 파일 크기·총량 검사는 multipart 파싱 후 수행하며 인터넷 공개 전 별도 요청 스트림 제한/할당량이 필요하다.

## 작업 목록
`GET /api/v1/jobs?page=1&pageSize=10&status=SUCCESS&search=filename`
- workspace 쿠키로 소유 범위를 먼저 제한한다. 쿠키가 없으면 빈 목록이다. 단일 Job 토큰으로 전체 목록을 열람할 수 없다.
- page≥1, pageSize 1~50, status는 QUEUED/PROCESSING/RETRY_WAIT/SUCCESS/FAILED/CANCEL_REQUESTED/CANCELLED 중 선택, search≤120자.
- 입력 파일명 또는 Job UUID 부분 검색. `%`와 `_`는 와일드카드가 아닌 문자로 처리한다. 현재 PostgreSQL 파일명 검색은 대소문자를 구분한다.
- `retryCenter=true`는 소유 범위 안의 FAILED/RETRY_WAIT만 조회한다.
- created_at DESC, job_id DESC로 정렬한다.
```json
{"items":[],"total":0,"page":1,"pageSize":10}
```

## 상세·이벤트·다운로드
| Method | 경로 | 응답 |
|---|---|---|
| GET | /api/v1/jobs/{UUID} | 200 Job 상세 |
| GET | /api/v1/jobs/{UUID}/events?after=0&limit=50 | 200 items,nextAfter,hasMore |
| GET | /api/v1/jobs/{UUID}/download | 200 application/pdf |
| GET | /health/live | 200 프로세스 응답 |
| GET | /health/ready | DB·Redis 정상 시 200, 아니면 503 |

상세·이벤트·다운로드는 해당 workspace 쿠키 또는 기존 `X-Job-Token`으로 권한을 검증한다. 미존재·미인가 모두 404, 결과 준비 전 409, 결과 유실·해시 불일치 410이다. 내부 저장 경로와 토큰 해시는 반환하지 않는다.

Job 요약: jobId,status,stage,progress,filename,createdAt,startedAt,completedAt,durationSeconds,totalFiles,processedFiles,totalPages,processedPages,errorCode,errorMessage,downloadAvailable.
상세 추가: options, files(파일명·크기·MIME·페이지 수·순서·checksum), result(크기·페이지 수·checksum 또는 null).
이벤트: eventId,attemptId(이전 기록/실행 전 이벤트는 null),sequence,type,message,details,createdAt. after는 마지막 확인 sequence, limit 1~100. 시간은 UTC ISO8601이며 UI가 현지 시간으로 표시한다.

입력 오류는 422 `{"detail":{"code":"...","message":"..."}}`. Pydantic 요청 구조·개수·query 검증 오류는 기본 detail 배열이다. FILE_TOO_LARGE, FILE_LIMIT_EXCEEDED, PAGE_LIMIT_EXCEEDED, PIXEL_LIMIT_EXCEEDED, INVALID_FILE, DECODE_FAILED, UNSUPPORTED_FORMAT, INVALID_OPTIONS 등을 구분한다. Worker 오류는 Job과 FAILED 이벤트에 코드·안전한 메시지·예외 종류를 저장한다. 상세 traceback은 서버 로그에만 기록한다.

## 재시도·취소
`POST /api/v1/jobs/{UUID}/retry` / `POST /api/v1/jobs/{UUID}/cancel` → 202. 기존과 동일한 workspace cookie 또는 X-Job-Token으로 권한을 검사한다.
```json
{"expectedGeneration": 1}
```
양의 정수인 현재 runGeneration을 반드시 전달한다. 알려지지 않은 필드는 거부한다. 재시도 원본/옵션 변경은 허용하지 않는다. 오래된 화면이나 중복 요청이 새 실행을 다시 변경하지 않도록 서버가 expectedGeneration과 현재 상태를 확인하며 충돌 시 409다. UUID만으로 무인가 요청을 허용하지 않는다.

retry: FAILED이고 수동 재시도 가능한 코드이며 원본 존재·SHA256 검증이 통과하면 같은 Job을 새 세대 QUEUED로 전환하고 새 Outbox를 생성한다. 실제 Worker가 Claim할 때 Attempt를 추가한다. autoRetryCount는 0으로 초기화하며 기존 Attempt/이벤트는 보존한다. 오류 코드는 새 Attempt 시작 시 현재 Job에서 초기화하되 이전 Attempt에 남긴다.
409 코드: RETRY_CONFLICT, NOT_RETRYABLE, SOURCE_UNAVAILABLE. 입력 오류/손상/미지원 형식/잘못된 옵션은 같은 Job으로 재처리하지 않는다.

cancel: QUEUED/RETRY_WAIT→CANCELLED, PROCESSING→CANCEL_REQUESTED. CANCEL_REQUESTED/CANCELLED에 같은 세대로 반복 요청하면 새 이벤트를 추가하지 않는다. SUCCESS/FAILED 또는 세대 불일치는 409 CANCEL_CONFLICT다. Worker가 취소 확인 후 Attempt를 CANCELLED로 종료하고 결과 게시를 막는다. 이미 성공 확정된 결과를 취소로 덮어쓰지 않는다.

Job 추가 필드: runGeneration,attemptCount,autoRetryCount,nextRetryAt,canRetry,canCancel. 상세에는 sourceAvailable,retryBlockedReason도 포함한다. canRetry는 코드 정책 및 원본 존재를 반영하며, 파일 변경 여부는 POST retry에서 해시로 최종 확인한다. autoRetryCount는 전체 생애 실행 횟수가 아니라 현재 수동 재처리 주기의 자동 예약 횟수다. 진행률은 현재/직전 Attempt 기준이며 새 시도 대기 시 0으로 초기화한다.

## Attempt 이력
`GET /api/v1/jobs/{UUID}/attempts?page=1&pageSize=20` → `{items,total,page,pageSize}`. page≥1, pageSize 1~100, attemptNumber 내림차순. 각 항목:
- attemptId,attemptNumber,generation,origin(INITIAL/AUTO/MANUAL/LEGACY)
- workerName,status(PROCESSING/SUCCESS/FAILED/CANCELLED)
- startedAt,finishedAt,errorCode,errorMessage,retryable

retryable은 해당 실패의 **자동** 재시도 정책을 기록한 값이다. 권한 오류 등은 운영자 조치 후 수동 재시도만 허용될 수 있다. 0003 이전 기록은 LEGACY이며 알 수 없는 시각은 null, Worker는 UNKNOWN이다. 대기 중 취소하여 Worker가 실행하지 않은 작업에는 Attempt를 만들지 않는다.

자동 재시도 상태: PROCESSING→RETRY_WAIT→QUEUED→PROCESSING. transient 저장소 오류·RESOURCE_EXHAUSTED·TIME_LIMIT_EXCEEDED를 최대 3회 예약하며 마지막 실패는 FAILED다. 예약은 DB/Outbox에 영속화하고 오류·Attempt를 유지한다. 원본 누락은 SOURCE_MISSING으로 분류하고 자동 반복하지 않는다. Soft time limit만 처리하며 hard kill 복구는 아직 없다.

recovery 및 Idempotency-Key는 Phase 4, monitoring은 Phase 5에서 제공한다. 같은 입력을 새로 업로드하면 별도 Job이며 기존 Job의 재시도와 구분한다.
