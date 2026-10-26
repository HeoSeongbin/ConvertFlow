# Phase 2 API 계약
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
- page≥1, pageSize 1~50, status는 QUEUED/PROCESSING/SUCCESS/FAILED 중 선택, search≤120자.
- 입력 파일명 또는 Job UUID 부분 검색. `%`와 `_`는 와일드카드가 아닌 문자로 처리한다. 현재 PostgreSQL 파일명 검색은 대소문자를 구분한다.
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
이벤트: eventId,sequence,type,message,details,createdAt. after는 마지막 확인 sequence, limit 1~100. 시간은 UTC ISO8601이며 UI가 현지 시간으로 표시한다.

입력 오류는 422 `{"detail":{"code":"...","message":"..."}}`. Pydantic 요청 구조·개수·query 검증 오류는 기본 detail 배열이다. FILE_TOO_LARGE, FILE_LIMIT_EXCEEDED, PAGE_LIMIT_EXCEEDED, PIXEL_LIMIT_EXCEEDED, INVALID_FILE, DECODE_FAILED, UNSUPPORTED_FORMAT, INVALID_OPTIONS 등을 구분한다. Worker 오류는 Job과 FAILED 이벤트에 코드·안전한 메시지·예외 종류를 저장한다. 상세 traceback은 서버 로그에만 기록한다.

retry/cancel/attempts는 Phase 3, recovery 및 Idempotency-Key는 Phase 4, monitoring은 Phase 5에서 제공한다. 현재 같은 입력을 다시 업로드하면 별도 Job이며 이를 자동 재시도라고 부르지 않는다.
