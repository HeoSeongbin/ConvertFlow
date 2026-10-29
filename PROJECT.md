# ConvertFlow — 비동기 문서 변환 및 작업 관리 플랫폼 개발 지시서

## 1. 프로젝트 개요

### 프로젝트명

**ConvertFlow — Asynchronous Document Processing Platform**

### 개발 목적

React + TypeScript + FastAPI + Redis + Celery 기반의 비동기 문서 변환 플랫폼을 개발한다.

사용자가 이미지 파일을 업로드하면 FastAPI 서버가 요청을 접수하고, Redis를 통해 Celery Worker에 작업을 전달한다.

Celery Worker는 백그라운드에서 파일을 PDF로 변환하며 사용자는 React 화면에서 작업 상태, 진행률, 처리 결과, 오류 내역을 확인하고 변환된 결과 파일을 다운로드할 수 있다.

본 프로젝트는 개발자의 포트폴리오에 공개할 개인 프로젝트이며, 비동기 작업 처리, 메시지 큐, Worker 분산 처리, 장애 복구, 중복 작업 방지, 작업 추적 및 모니터링 역량을 보여주는 것을 목표로 한다.

단순 파일 변환 사이트나 UI 목업이 아니라 실제로 동작하는 서비스로 개발한다.

### 핵심 목표

1. 파일 업로드와 실제 변환 작업 분리
2. Redis 기반 작업 메시지 전달
3. Celery Worker를 이용한 비동기 PDF 변환
4. UUID 기반 Job 관리
5. 작업 진행 상태 및 진행률 조회
6. 여러 파일과 다중 페이지 이미지 처리
7. 결과 파일 다운로드
8. 실패 작업 재시도
9. 작업 이력 관리
10. Worker 중단 및 재시작 후 복구
11. 중복 작업 실행에 대한 멱등성 확보
12. 다중 Worker 환경 지원
13. 파일 처리 성능 및 상태 모니터링
14. Docker Compose 기반 실행
15. 자동화 테스트 및 기술 문서화

---

## 2. 핵심 개발 원칙

- React + TypeScript 기반 프론트엔드
- FastAPI 기반 REST API
- Celery 기반 비동기 작업 처리
- Redis 기반 Message Broker
- PostgreSQL 기반 영속 데이터 관리
- SQLAlchemy 및 Alembic 기반 DB 접근과 스키마 관리
- Docker Compose 기반 실행 환경
- 백엔드 API와 Worker 프로세스 분리
- 원본 및 결과 파일의 안전한 관리
- 작업별 UUID 부여
- 데이터베이스를 작업 상태의 기준 저장소로 사용
- 작업의 중복 실행과 결과 중복 반영 방지
- Worker 재시작 및 장애 복구 고려
- 작업 처리 단계별 로그 기록
- 라이브러리 및 변환 코드의 재사용성 확보
- 단위, 통합, 장애 시나리오 테스트
- 문서 기반 프로젝트 관리

처음부터 모든 변환 형식을 구현하지 않고 이미지 → PDF를 안정적으로 완성한 뒤 확장한다.

---

## 3. 기술 스택

### Frontend

- React
- TypeScript (strict mode)
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- Zustand
- Axios
- React Hook Form
- Zod
- Lucide React
- Recharts
- Vitest
- Playwright

### Backend

- Python 3.12 이상 호환 안정 버전
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- psycopg
- Celery
- redis-py
- Pillow
- img2pdf 또는 요구사항에 적합한 이미지/PDF 처리 라이브러리
- Pytest
- HTTPX
- Ruff

### Infrastructure

- Redis
- PostgreSQL
- Docker
- Docker Compose
- GitHub Actions
- Docker Volume
- 구조화된 JSON Logging

라이브러리는 실제 버전 호환성을 검증한 후 선정하고 의존성 버전을 고정한다.

Celery Worker는 Linux 컨테이너에서 실행하도록 구성한다.

---

## 4. 전체 시스템 아키텍처

다음 서비스를 분리한다.

### 4.1 React Frontend

사용자 인터페이스를 제공한다.

책임:

- 파일 업로드
- 변환 옵션 선택
- 작업 등록
- 진행 상태 조회
- 작업 목록
- 작업 상세
- 실패 원인 표시
- 재시도
- 취소 요청
- 결과 다운로드
- Worker 모니터링

### 4.2 FastAPI Backend

HTTP 요청과 작업 관리 API를 담당한다.

책임:

- 파일 수신
- 입력 파일 검증
- 파일 저장
- Job 생성
- 작업 큐 발행
- Job 상태 조회
- 작업 이력 조회
- 결과 다운로드
- 재시도 요청 접수
- 작업 취소 요청
- 오류 응답 처리

파일 변환을 요청 스레드에서 직접 수행하지 않는다.

다만 안전한 업로드 검증 및 파일 저장 처리는 API에서 수행한다.

### 4.3 Redis

Celery의 Message Broker로 사용한다.

작업 메시지 전달을 담당하며 대용량 파일 바이너리 자체를 큐에 저장하지 않는다.

Celery 작업 메시지에는 Job ID와 필요한 최소 메타데이터만 전달한다.

### 4.4 Celery Worker

실제 파일 변환을 수행한다.

책임:

- 작업 획득
- 중복 처리 방지
- 작업 상태 변경
- 원본 파일 로딩
- 이미지 디코딩
- PDF 변환
- 진행률 갱신
- 출력 파일 생성
- 최종 결과 저장
- 오류 기록
- 일시적 실패 재시도

Worker 수를 확장할 수 있어야 한다.

### 4.5 PostgreSQL

영속 상태 저장소다.

- Job 정보
- 파일 메타데이터
- Job 상태
- 처리 시도
- 오류 코드
- 작업 이벤트
- 결과 파일 정보
- 재시도 이력
- 실행 Worker 정보
- 처리 시간

### 4.6 Shared Storage

API와 Worker가 함께 접근할 수 있는 파일 저장소다.

초기 버전에서는 Docker Named Volume을 사용한다.

저장 영역:

- uploads/
- processing/
- results/
- temporary/

개발 환경에서 API와 Worker가 같은 파일을 참조할 수 있어야 한다.

추후 S3 또는 MinIO 기반 Object Storage로 교체할 수 있도록 스토리지 인터페이스를 추상화한다.

---

## 5. 프로젝트 폴더 구조

다음 구조를 기본으로 설계한다.

```text
convertflow/
├── PROJECT.md
├── AGENTS.md
├── README.md
├── docs/
│   ├── PROGRESS.md
│   ├── DECISIONS.md
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── TEST-SCENARIOS.md
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── upload/
│   │   │   ├── jobs/
│   │   │   ├── history/
│   │   │   └── monitoring/
│   │   ├── services/
│   │   ├── stores/
│   │   ├── hooks/
│   │   └── types/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── tasks/
│   │   ├── workers/
│   │   ├── converters/
│   │   └── storage/
│   ├── alembic/
│   └── tests/
├── docker/
├── scripts/
├── .github/
│   └── workflows/
├── docker-compose.yml
└── .env.example
```

FastAPI와 Celery가 공유하는 도메인 로직은 독립적인 서비스 모듈로 분리한다.

API 라우터에 PDF 변환 로직을 직접 구현하지 않는다.

---

## 6. 프로젝트 문서 관리

다섯 개 문서를 핵심으로 관리한다.

### PROJECT.md

프로젝트 최종 요구사항 및 아키텍처 기준 문서.

포함할 내용:

- 프로젝트 목표
- 기술 스택
- 주요 기능
- 시스템 구성
- 파일 처리 흐름
- DB 설계
- API 규격
- 작업 상태 머신
- 중복 실행 방지
- 오류 처리 및 재시도 정책
- Worker 복구 정책
- 파일 보관 및 보안 정책
- 개발 Phase
- 테스트 시나리오
- 최종 완료 기준

### AGENTS.md

에이전트 작업 규칙.

필수 내용:

1. 작업 전 PROJECT.md 읽기
2. PROGRESS.md 읽기
3. DECISIONS.md 읽기
4. 실제 코드와 문서 비교
5. 현재 Phase 확인
6. 기존 정상 기능 보존
7. 범위에 맞는 기능 구현
8. 타입 검사, 린트, 테스트 실행
9. 작업 완료 후 문서 업데이트
10. 검증하지 않은 작업 완료 처리 금지

### README.md

GitHub 사용자 및 포트폴리오 방문자용 문서.

- 프로젝트 소개
- 주요 기능
- 시스템 아키텍처
- 기술 스택
- Docker Compose 실행 방법
- 파일 업로드 사용법
- 결과 다운로드 방법
- 실패 재시도 방법
- Worker 장애 재현 시나리오
- 주요 기술적 결정
- 테스트 실행 방법
- 스크린샷
- 알려진 제한사항

### docs/PROGRESS.md

개발 진행 현황.

- 현재 Phase
- 완료 기능
- 진행 중인 기능
- 미완료 기능
- 발견된 오류
- 해결된 오류
- 테스트 결과
- 다음 작업
- 차단 요인

작업 종료 시 반드시 업데이트한다.

### docs/DECISIONS.md

중요한 기술적 결정과 이유를 ADR 형식으로 기록한다.

특히 다음 결정은 반드시 기록한다.

- Redis와 PostgreSQL 역할 분리
- Celery Task Acknowledgment 정책
- Redis Visibility Timeout
- 작업 멱등성
- DB 작업 상태 전환 방식
- Worker 중단 후 복구 방법
- 공유 파일 스토리지 구조
- 진행률 계산 방법
- 파일 변환 엔진 선정
- 결과 파일 보관 및 삭제 정책

---

## 7. 파일 업로드

### 초기 필수 지원 형식

- PNG
- JPG/JPEG
- BMP
- WEBP
- TIFF/TIF

### 추가 지원 형식

- GIF
- AVIF
- HEIC/HEIF
- PDF

추가 형식은 인코더/디코더와 실제 브라우저 지원 여부를 검증한 후 도입한다.

애니메이션 GIF 및 다중 페이지 TIFF는 프레임/페이지 처리 정책을 명확하게 정한다.

### 업로드 기능

- 파일 선택
- Drag & Drop
- 다중 파일 업로드
- 파일 목록 확인
- 파일 크기 표시
- 업로드 진행률
- 지원 형식 확인
- 파일별 오류 표시
- 파일 삭제
- 전체 삭제
- 변환 옵션 선택
- 업로드 완료 후 작업 시작

### 파일 검증

- 확장자 검증
- 실제 파일 포맷 검증
- MIME 확인
- 손상된 파일 확인
- 최대 파일 크기 제한
- 최대 파일 개수 제한
- 최대 픽셀 수 제한
- 이미지 페이지 수 제한
- 압축 폭탄 방어
- 비정상 파일명 처리

클라이언트 검증 외에 서버 측 검증을 반드시 수행한다.

파일 이름을 그대로 저장 경로로 사용하지 않는다.

UUID 기반 저장 경로를 사용한다.

---

## 8. 이미지 → PDF 변환

### 첫 버전 필수 기능

1. 단일 이미지 → PDF
2. 여러 이미지 → 단일 PDF
3. 이미지 순서 변경
4. 원본 비율 유지
5. PDF 페이지 크기 선택
6. 회전 방향 처리
7. 변환 결과 다운로드

### PDF 옵션

- 원본 크기 기반
- A4
- Letter
- 세로 방향
- 가로 방향
- 페이지 여백
- 이미지 맞춤 방식
- 출력 품질 설정

선택한 옵션이 실제 출력 PDF에 반영되어야 한다.

### 변환 엔진

공통 Converter 인터페이스를 설계한다.

```python
from typing import Protocol

class FileConverter(Protocol):
    def convert(
        self,
        input_paths: list[str],
        output_path: str,
        options: dict
    ) -> None:
        ...
```

실제 구현 시 타입 안정성이 높은 옵션 모델로 개선한다.

### 다중 페이지 처리

TIFF에 여러 페이지가 있으면 각 페이지를 PDF 페이지로 변환할 수 있도록 한다.

여러 이미지를 선택한 경우 사용자가 지정한 순서를 유지한다.

처리 중 각 페이지가 성공했는지 확인한다.

초기 버전에서는 변환 중 오류가 발생하면 전체 작업을 실패시키고 부분 생성된 출력 파일을 결과물로 공개하지 않는다.

---

## 9. 비동기 작업 처리 흐름

다음 처리 흐름을 구현한다.

```text
React
  ↓
FastAPI Upload API
  ↓
파일 검증 및 저장
  ↓
PostgreSQL Job 생성
  ↓
Redis Queue 발행
  ↓
Celery Worker
  ↓
이미지 로딩 및 변환
  ↓
PDF 생성
  ↓
결과 파일 검증
  ↓
PostgreSQL 상태 변경
  ↓
React 상태 조회
  ↓
PDF 다운로드
```

### 핵심 원칙

- API 요청과 실제 변환 작업 분리
- Job 생성 후 UUID 반환
- HTTP 응답에서 PDF 변환 완료를 기다리지 않음
- Celery 메시지에 대용량 파일 직접 포함 금지
- DB에 영속 상태 유지
- Worker 실행 횟수와 논리 Job 구분
- 파일 생성 결과 검증
- 실패 시 원인 기록
- 진행률 조회 API 제공

### 작업 등록의 안정성

DB에 Job이 생성되었는데 Redis 메시지 발행이 실패할 수 있다는 점을 고려한다.

초기 버전에서는 Transactional Outbox 또는 DB 기반 Dispatch Recovery 방식 중 하나를 선택한다.

필요하다면 OUTBOX_EVENT 테이블을 추가한다.

큐 발행에 실패한 Job을 영구적으로 방치하지 않도록 복구한다.

DB 트랜잭션 내에서 Redis 메시지 발행 성공까지 원자적으로 보장한다고 가정하지 않는다.

---

## 10. Job 데이터 및 상태 관리

### Job 데이터

```ts
interface ConversionJob {
  jobId: string;
  status: JobStatus;
  progress: number;
  totalFiles: number;
  processedFiles: number;
  attemptCount: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  errorCode?: string;
  errorMessage?: string;
  downloadAvailable: boolean;
}
```

### 상태 목록

- UPLOADING
- QUEUED
- PROCESSING
- RETRY_WAIT
- SUCCESS
- FAILED
- CANCEL_REQUESTED
- CANCELLED
- RECOVERY_REQUIRED

UPLOAD 단계에서 Job 레코드를 생성하지 않는 구조라면 UPLOADING은 프론트엔드 전용 상태로 분리한다.

### 상태 전환

```text
QUEUED
  ↓
PROCESSING
  ├── SUCCESS
  ├── FAILED
  ├── RETRY_WAIT → QUEUED
  ├── CANCEL_REQUESTED → CANCELLED
  └── RECOVERY_REQUIRED
```

실제 상태 전환은 별도의 명시적인 규칙으로 관리한다.

### 진행률

0~100 범위의 진행률을 제공한다.

단, 진행률은 실제 완료한 처리 단계나 처리한 페이지 수를 기준으로 산정한다.

단순 시간 경과를 기준으로 가짜 진행률을 생성하지 않는다.

예시:

- 0~10%: 입력 검사
- 10~85%: 이미지 페이지 처리
- 85~95%: PDF 인코딩
- 95~100%: 결과 검증 및 저장

라이브러리가 내부 처리 진행률을 제공하지 않는 경우 단계별 진행률과 현재 처리 단계를 구분해서 표시한다.

SUCCESS 상태와 유효한 결과 파일이 확보된 경우에만 100% 완료 처리한다.

---

## 11. Celery Worker 설계

Celery Worker는 API와 독립된 프로세스로 실행한다.

### 설정 검토

- Worker Concurrency
- Worker Prefetch
- Task Acknowledgment
- Task Retry
- Broker Visibility Timeout
- Soft/Hard Time Limit
- Redis 연결 재시도
- Worker 종료 처리
- Worker 장애 복구
- 메모리 사용량
- 작업 결과 보관 기간

### 중요한 조건

`task_acks_late`를 활성화하더라도 Worker가 강제 종료된 모든 상황에서 자동 재실행이 보장되는 것은 아니다.

`task_reject_on_worker_lost` 적용 여부를 검토하고, 중복 실행 가능성에 대한 테스트를 수행한다.

Redis visibility timeout은 작업 시간 및 재전달 정책을 고려해 설정한다.

Worker Prefetch가 길게 실행되는 작업의 공정한 분배에 어떤 영향을 주는지 검증한다.

실제 설정값과 이유를 DECISIONS.md에 기록한다.

### 다중 Worker

초기에는 단일 Worker를 구성한다.

이후 Docker Compose에서 Worker 수를 늘려 여러 작업을 병렬 처리할 수 있어야 한다.

다중 Worker 환경에서 동일 Job의 결과가 중복 확정되지 않아야 한다.

---

## 12. 작업 멱등성 및 중복 실행 방지

매우 중요한 구현 요구사항이다.

Celery는 특정 장애 상황에서 같은 메시지를 다시 전달할 수 있다.

따라서 같은 Job이 두 번 실행되더라도 결과가 손상되지 않아야 한다.

### 요구사항

1. Job ID 기반 중복 감지
2. PostgreSQL 상태 기반 실행 권한 획득
3. 조건부 상태 갱신 또는 원자적 Claim
4. Worker 실행권한 Lease 관리
5. 작업 실행별 Attempt ID 생성
6. 오래된 Worker의 결과 확정 방지
7. 출력 파일 충돌 방지
8. 결과 파일의 원자적 게시
9. 중복 완료 이벤트 방지

### 처리 예시

- Worker A가 Job을 획득
- Worker A의 Lease가 만료
- Worker B가 복구 정책에 따라 Job을 재획득
- Worker A가 뒤늦게 완료
- Worker A의 오래된 Attempt 결과는 최종 상태에 반영되지 않아야 함

이를 위해 Lease 만료 시간과 Fencing Token 또는 동등한 세대 번호 기반 검증을 설계한다.

변환 도중 생성하는 파일은 Attempt별 임시 파일로 구분한다.

정상 완료한 Attempt만 결과 파일을 최종 게시할 수 있도록 한다.

### 추가 중복 요청

동일한 파일을 사용자가 두 번 업로드했다고 해서 무조건 같은 요청이라고 처리하지 않는다.

사용자가 Idempotency Key를 제공하거나 동일 요청을 중복 제출한 것이 확인되는 경우에만 정의된 정책으로 중복 요청을 처리한다.

---

## 13. 실패 처리 및 재시도

### 오류 유형

- INVALID_FILE
- UNSUPPORTED_FORMAT
- FILE_TOO_LARGE
- DECODE_FAILED
- CONVERSION_FAILED
- STORAGE_ERROR
- REDIS_UNAVAILABLE
- WORKER_LOST
- TIME_LIMIT_EXCEEDED
- INTERNAL_ERROR

### 재시도 가능 오류

- 일시적인 파일 스토리지 오류
- 일시적 외부 서비스 오류
- 일시적인 리소스 부족
- 일시적 인프라 연결 오류

### 재시도하지 않을 오류

- 손상된 이미지
- 미지원 형식
- 비정상 입력
- 정책상 크기 제한 초과

### 자동 재시도

- 최대 재시도 횟수
- Exponential Backoff
- Jitter
- 재시도 간격 제한
- 재시도 이력 기록

### 수동 재처리

- 실패한 Job 선택
- 실패 원인 표시
- 재처리 버튼
- 재처리 요청 생성
- 기존 Job과 이력 연결
- 재처리 후 결과 확인

수동 재처리에서 새 논리 Job을 만들지 기존 Job에 새 Attempt를 추가할지 정책을 명확하게 정의한다.

기본적으로 동일한 원본 파일과 변환 옵션을 재사용하는 재처리는 동일 Job 아래 새 Attempt로 관리한다.

원본 파일이 삭제된 경우 재처리할 수 없음을 안내한다.

---

## 14. Worker 중단 및 복구

Worker 중단 상황은 실제 테스트 가능한 핵심 기능으로 구현한다.

### 테스트 시나리오

1. 파일 업로드
2. 작업 QUEUED 확인
3. Worker 작업 시작
4. PROCESSING 확인
5. Worker 강제 종료
6. 현재 작업 상태 확인
7. Worker 재기동
8. 메시지 재전달 또는 복구 스케줄러 동작 확인
9. 동일 Job 중복 처리 여부 확인
10. 최종 결과 확인

### 추가 장애

- Redis 일시 중단
- PostgreSQL 일시 중단
- API 서버 재시작
- Worker 재시작
- 결과 파일 생성 직후 Worker 종료
- DB 성공 상태 업데이트 직전 종료
- 다중 Worker 동시 처리
- 파일 저장소 용량 부족

### 복구 정책

모든 장애에서 즉시 자동 복구된다고 가정하지 않는다.

다음 방식들을 조합한다.

- Lease 및 Heartbeat
- Recovery Scheduler
- DB 상태 검사
- Redis Queue 발행 재확인
- Celery 메시지 재전달
- Attempt 이력
- Fencing Token
- 결과 파일 검증

RECOVERY_REQUIRED 상태를 통해 수동 또는 자동 복구가 필요한 작업을 확인할 수 있게 한다.

---

## 15. PostgreSQL 데이터 모델

다음 테이블을 권장한다.

### conversion_job

논리적인 변환 작업.

- job_id
- status
- progress
- total_files
- processed_files
- attempt_count
- options
- error_code
- error_message
- created_at
- started_at
- completed_at

### conversion_job_file

작업의 입력 파일 목록.

- file_id
- job_id
- original_filename
- storage_path
- file_size
- mime_type
- page_count
- sort_order
- checksum

### conversion_attempt

Worker 실행 시도.

- attempt_id
- job_id
- worker_name
- attempt_number
- fencing_token
- status
- started_at
- finished_at
- error_code
- error_message

### conversion_event

단계별 작업 이벤트.

- event_id
- job_id
- attempt_id
- event_type
- message
- created_at

### conversion_result

출력 결과.

- result_id
- job_id
- output_path
- file_size
- checksum
- page_count
- created_at

### job_dispatch_outbox

작업 발행 및 복구용 이벤트.

- event_id
- job_id
- event_type
- status
- retry_count
- created_at
- published_at

### job_execution_lease

필요 시 Worker 실행권한을 관리하는 테이블.

Lease 관련 컬럼을 conversion_job 또는 conversion_attempt에 통합할 수도 있다.

### 데이터 관리 원칙

- UUID PK
- FK 및 Unique Constraint
- 적절한 Index
- UTC 시간 저장
- 명시적 상태 전환
- DB 트랜잭션
- 중복 갱신 방지
- 실패 이력 보존
- 파일 경로와 실제 파일 일치 검증

---

## 16. 파일 저장 및 결과 다운로드

### 저장 구조

```text
storage/
├── uploads/
│   └── {job_id}/
├── processing/
│   └── {job_id}/{attempt_id}/
├── results/
│   └── {job_id}/
└── temporary/
```

### 파일 처리 규칙

- UUID 기반 경로
- 원본 파일명 직접 경로 사용 금지
- 임시 파일 별도 관리
- 실패 시 불완전 결과 공개 금지
- 원본 파일 보관 정책
- 결과 파일 보관 정책
- 삭제 시 DB와 스토리지 정합성 고려
- 파일 크기 및 해시 검증
- 원자적 파일 이동 또는 교체
- 다운로드 시 경로 조작 방지

### 다운로드

- 단일 PDF 다운로드
- 여러 결과의 ZIP 다운로드
- 결과 파일명에 변환 정보 반영
- 올바른 Content-Type
- 다운로드 실패 시 오류 안내
- 유효한 SUCCESS 결과만 다운로드 허용

향후 파일 만료 및 자동 정리 기능을 추가한다.

---

## 17. REST API

### Upload

- POST /api/v1/jobs

multipart/form-data 요청으로 파일과 변환 옵션을 전달한다.

응답에는 Job ID 및 초기 상태를 반환한다.

장시간 변환 완료를 기다리지 않는다.

### Job 관리

- GET /api/v1/jobs
- GET /api/v1/jobs/{jobId}
- GET /api/v1/jobs/{jobId}/events
- GET /api/v1/jobs/{jobId}/attempts
- POST /api/v1/jobs/{jobId}/retry
- POST /api/v1/jobs/{jobId}/cancel
- GET /api/v1/jobs/{jobId}/download

### Monitoring

- GET /api/v1/monitoring/summary
- GET /api/v1/monitoring/workers
- GET /api/v1/monitoring/queues

### Health

- GET /health/live
- GET /health/ready

실제 API 경로, 오류 응답 형식, 페이지네이션, 상태 코드는 일관되게 설계한다.

Swagger/OpenAPI 문서를 제공한다.

작업 상세 조회 및 다운로드는 서버에서 접근 권한을 검증하도록 설계한다.

---

## 18. React UI/UX

현대적인 파일 처리 관리 콘솔 형태로 개발한다.

### 화면 1. Dashboard

- 전체 작업 수
- 대기 작업
- 처리 중 작업
- 성공 작업
- 실패 작업
- 평균 처리시간
- 최근 작업
- 상태별 차트

### 화면 2. File Upload

- Drag & Drop 영역
- 파일 선택
- 파일 목록
- 파일 크기
- 파일 순서 변경
- 출력 옵션
- 변환 시작
- 업로드 진행률

### 화면 3. Job List

- Job ID
- 파일명
- 작업 상태
- 진행률
- 등록시간
- 소요시간
- 실패 원인
- 검색 및 필터
- 페이지네이션

### 화면 4. Job Detail

- Job ID
- 파일 목록
- 현재 상태
- 진행률
- 변환 설정
- 현재 처리 단계
- Attempt 목록
- 이벤트 타임라인
- 오류 상세
- 결과 다운로드

### 화면 5. Retry Center

- 실패 작업 목록
- 실패 원인
- 재시도 가능 여부
- 재처리 버튼
- 재시도 이력

### 화면 6. Worker Monitoring

- Worker 목록
- 온라인/오프라인 상태
- 처리 중 작업
- 큐 대기 상태
- 최근 처리량
- Worker 상태 갱신 시각

Worker 모니터링 값은 실제 확인 가능한 데이터에 기반한다.

Worker 상태를 확인하지 못하면 UNKNOWN으로 표시한다.

단순히 Heartbeat가 지연되었다는 이유만으로 무조건 Worker가 종료되었다고 단정하지 않는다.

### 화면 7. Settings

- 최대 파일 크기
- 업로드 제한 안내
- 출력 포맷 설정
- 저장 기간 확인
- 시스템 정보

실제 운영 설정 변경 기능은 인증 및 권한 관리가 마련된 이후 제공한다.

### 디자인 원칙

- 한국어 기본 UI
- Light/Dark 모드
- 명확한 상태 표시
- 반응형 레이아웃
- 전문적인 SaaS 관리 콘솔
- 로딩/오류/빈 데이터 상태 구분
- 가독성 높은 로그 및 이벤트 표시
- 접근성 고려

---

## 19. 작업 진행률 조회

초기 버전은 Polling 기반으로 구현한다.

### 방식

- React에서 Job 생성
- Job ID 저장
- TanStack Query로 일정 주기 상태 조회
- 상태 변경 시 UI 갱신
- SUCCESS/FAILED/CANCELLED 등 종료 상태에서 Polling 중단

### 이후 확장

- Server-Sent Events
- 실시간 상태 갱신
- Worker 이벤트 스트림

초기에는 복잡한 실시간 인프라보다 안정적인 Polling 방식을 우선한다.

업로드 진행률과 실제 Celery 변환 진행률을 분리해서 표시한다.

---

## 20. Worker 모니터링

다음 정보를 확인할 수 있어야 한다.

- 등록 Worker
- Worker 상태
- 현재 실행 중인 Job
- 최근 Heartbeat
- 최근 성공/실패 건수
- 작업 큐 대기 건수
- 평균 처리시간
- 처리량

초기에는 Celery Inspect, Celery Events 또는 별도 Heartbeat 방식 중 적절한 방식을 선정한다.

실제 Redis 큐 내부 구조를 직접 추정하여 부정확한 값을 표시하지 않는다.

모니터링 값의 수집 방식과 정확성 제약을 문서화한다.

---

## 21. 테스트

### 단위 테스트

- 파일 포맷 검증
- 변환 옵션 검증
- 이미지 PDF 변환
- 상태 전환
- 진행률 계산
- 오류 분류
- 파일 경로 생성
- 결과 검증

### 통합 테스트

- FastAPI → DB
- FastAPI → Redis
- Redis → Celery Worker
- Worker → Storage
- Worker → DB
- Job Status API
- Result Download

### 동시성 테스트

- 동일 Job 중복 실행
- 두 Worker 동시 Claim
- Lease 만료 후 재획득
- 오래된 Attempt 완료
- 같은 Job 중복 결과 확정
- 동일 Idempotency Key 중복 요청

### 장애 테스트

- Worker 강제 종료
- Worker 재시작
- Redis 연결 중단
- API 재시작
- DB 연결 장애
- 변환 중 오류
- 출력 파일 생성 실패
- 디스크 공간 부족 시뮬레이션
- 중단 후 복구

### UI E2E 테스트

- 파일 업로드
- 변환 실행
- 상태 조회
- 결과 다운로드
- 실패 작업 조회
- 재처리
- 작업 이력 확인

모든 테스트 결과는 실제 실행 결과를 기준으로 기록한다.

---

## 22. Docker Compose

다음 서비스를 기본으로 구성한다.

```text
frontend
api
worker
redis
postgres
recovery-scheduler
```

필요하다면 별도 Dispatcher 서비스를 추가한다.

### 필수 조건

- 서비스별 Dockerfile
- Multi-stage Build 검토
- Named Volume
- 환경 변수
- Healthcheck
- 서비스 재시작 정책
- 컨테이너 내부 네트워크 통신
- 로그 확인
- DB Migration
- Redis 연결 확인

### 실행 목표

```bash
docker compose up -d --build
```

명령 한 번으로 개발용 서비스를 기동할 수 있도록 구성한다.

Compose 서비스가 시작되었다는 사실만으로 실제 애플리케이션 준비 완료라고 판단하지 않는다.

API, DB, Redis, Worker의 준비 상태를 검증한다.

---

## 23. 보안 및 파일 처리 안정성

다음 정책을 적용한다.

- 파일 확장자만 믿지 않음
- 실제 파일 형식 확인
- 최대 업로드 크기 제한
- 최대 파일 개수 제한
- 이미지 픽셀 수 제한
- 압축 폭탄 방어
- 파일 시스템 경로 조작 방지
- 임의 실행 파일 업로드 차단
- 사용자 입력값을 Shell 명령으로 직접 실행하지 않음
- 파일 변환 라이브러리 오류 처리
- Worker CPU 및 메모리 제한
- 비밀키 환경 변수 관리
- 로그에 파일 원문 및 민감 데이터 무분별한 출력 금지
- CORS 허용 출처 제한
- 공개 운영 시 인증/접근 제어 적용

초기 버전은 로컬 개발 환경을 기본으로 한다.

인증이 없는 서비스를 공개 인터넷에 무제한 노출하지 않는다.

---

## 24. 개발 단계

### Phase 0 — 설계 및 문서 관리 체계

- 프로젝트 요구사항 분석
- 기술 스택 선정
- 전체 아키텍처 설계
- 도메인 모델 설계
- 상태 머신 설계
- DB ERD
- API 계약
- 5개 핵심 문서 생성
- 장애 시나리오 설계

완료 기준: 구현을 시작할 수 있는 명확한 설계와 문서 확보.

### Phase 1 — 실행 환경 및 기본 비동기 처리

- FastAPI 프로젝트 생성
- React 프로젝트 생성
- PostgreSQL 연결
- Redis 설정
- Celery Worker 연결
- Docker Compose 작성
- 단일 이미지 업로드
- Job UUID 생성
- Celery 작업 실행
- 이미지 → PDF 변환
- Job 상태 조회
- 결과 다운로드
- 기본 화면 구현

완료 기준: 이미지를 업로드하면 별도 Worker에서 PDF로 변환하고 다운로드할 수 있음.

### Phase 2 — 다중 파일 및 작업 관리

- 여러 이미지 업로드
- 순서 변경
- 다중 페이지 TIFF
- PDF 출력 옵션
- 작업 목록
- 작업 상세
- 진행률 표시
- 작업 이력
- 상세 오류 기록

완료 기준: 여러 파일의 PDF 변환 및 작업 관리 가능.

### Phase 3 — 실패 처리 및 재시도

- 오류 유형 정리
- 자동 재시도
- 수동 재시도
- Attempt 이력
- 실패 원인 표시
- Retry Center
- 취소 처리

완료 기준: 실패 작업을 추적하고 안전하게 재처리 가능.

### Phase 4 — 멱등성 및 Worker 장애 복구

- Job 중복 Claim 방지
- Worker Lease
- Fencing Token
- Redis 작업 재전달 정책
- Recovery Scheduler
- Worker 강제 종료 테스트
- 서버 재시작 복구
- Outbox 복구 검증
- 다중 Worker 동시성 테스트

완료 기준: Worker 장애 이후에도 상태와 결과의 일관성을 유지하며 안전하게 복구 가능.

### Phase 5 — 모니터링 및 성능

- Dashboard
- Worker Monitoring
- 큐 상태 확인
- 처리시간 통계
- 오류 통계
- Worker 확장
- 대량 파일 테스트
- 메모리 최적화
- DB Index 최적화

완료 기준: 작업 및 Worker 상태를 운영 화면에서 확인할 수 있음.

### Phase 6 — UI/UX 개선

- 전체 레이아웃 고도화
- 파일 업로드 UX 개선
- 진행률 UI
- 이벤트 타임라인
- 결과 미리보기
- Dark/Light 모드
- 반응형 UI
- 오류 안내 개선

완료 기준: 실제 사용 가능한 문서 변환 관리 UI 완성.

### Phase 7 — 자동화 테스트 및 포트폴리오

- 단위 테스트
- 통합 테스트
- E2E 테스트
- 장애 복구 테스트
- GitHub Actions
- Docker 실행 검증
- README 완성
- 아키텍처 다이어그램
- Worker 장애 시연 시나리오
- 성능 측정 결과
- 포트폴리오 설명 작성

완료 기준: 새 환경에서도 Docker Compose로 실행하고 주요 기능 및 장애 시나리오를 재현 가능.

---

## 25. 최종 완료 조건

2026-10-29 Phase 7 로컬 검증 기준. 근거와 한계는 docs/PROGRESS.md 및 docs/validation/phase7.json을 따른다. 중복 방지는 같은 Job의 실행/결과 반영 기준이며 업로드 요청 Idempotency-Key는 미구현이다. 새 Compose 프로젝트/빈 볼륨에서 검증했으며 원격 CI·공개 운영 인증·실제 모바일 기기 검증은 포함하지 않는다.

- [x] 파일 업로드
- [x] 파일 형식 검증
- [x] FastAPI 요청 접수
- [x] UUID Job 생성
- [x] Redis Queue 발행
- [x] Celery Worker 실행
- [x] 이미지 → PDF 변환
- [x] 다중 파일 변환
- [x] 다중 페이지 TIFF 처리
- [x] 상태 조회
- [x] 진행률 조회
- [x] 결과 다운로드
- [x] 실패 원인 기록
- [x] 작업 이력 관리
- [x] 자동 재시도
- [x] 수동 재처리
- [x] 작업 취소 처리
- [x] 중복 Job 처리 방지
- [x] Worker 장애 복구
- [x] 다중 Worker 실행
- [x] Worker 상태 모니터링
- [x] 작업 대시보드
- [x] PostgreSQL 영속화
- [x] Docker Compose 실행
- [x] 자동화 테스트
- [x] README 문서화
- [x] PROJECT.md 관리
- [x] AGENTS.md 관리
- [x] PROGRESS.md 최신화
- [x] DECISIONS.md 기록

---

## 26. 에이전트 작업 규칙

당신은 FastAPI, Celery, Redis, PostgreSQL, React 및 Docker 기반 비동기 시스템 구축 경험이 있는 시니어 풀스택 개발자 역할이다.

다음 원칙을 따른다.

1. 작업 시작 전에 프로젝트 관리 문서를 확인한다.
2. 현재 저장소와 Git 상태를 확인한다.
3. PROGRESS.md의 현재 Phase를 확인한다.
4. 해당 Phase의 요구사항을 분석한다.
5. 기존 정상 기능을 보존한다.
6. 아키텍처의 책임 분리를 유지한다.
7. 변경 시 관련 테스트를 추가한다.
8. 작업 후 빌드와 테스트를 실행한다.
9. 테스트 실패를 무시하지 않는다.
10. 변경 내용을 PROGRESS.md에 기록한다.
11. 주요 설계 결정은 DECISIONS.md에 기록한다.
12. README.md를 실제 구현 상태와 일치시킨다.
13. 실행하지 못한 테스트를 성공했다고 표시하지 않는다.
14. 미완료 기능은 미완료 상태로 기록한다.
15. 다음 작업자가 개발을 이어갈 수 있도록 상태를 남긴다.

### 반드시 피할 사항

- API에서 시간이 오래 걸리는 변환 작업을 직접 동기 수행
- Redis를 영구 파일 저장소로 사용
- Celery 메시지에 원본 이미지 바이너리 전달
- Worker 재전달 시 중복 실행 가능성을 무시
- DB와 Redis 간 원자성이 자동 보장된다고 가정
- 단순 시간 경과로 허위 진행률 표시
- 재시도 이력 없이 실패 작업 덮어쓰기
- Worker 강제 종료 테스트 없이 복구 완료 주장
- 데이터 검증 없이 PDF 생성 성공 처리
- 기존 정상 기능을 제거하거나 무단 재작성

---

## 27. 최초 실행 지시

첫 번째 실행에서는 **Phase 0과 Phase 1까지만 작업한다.**

### 수행 순서

1. 현재 프로젝트 저장소 및 Git 상태 확인
2. 기술 스택 버전 및 호환성 검토
3. 시스템 전체 아키텍처 설계
4. DB 및 Job 상태 머신 설계
5. PROJECT.md 생성
6. AGENTS.md 생성
7. README.md 초기 작성
8. docs/PROGRESS.md 생성
9. docs/DECISIONS.md 생성
10. FastAPI 프로젝트 초기화
11. React + TypeScript 프로젝트 초기화
12. Redis 및 PostgreSQL 구성
13. Celery Worker 설정
14. Docker Compose 작성
15. 단일 이미지 업로드 API 구현
16. Job ID 생성 및 상태 저장
17. Celery 작업 발행
18. Worker 이미지 → PDF 변환
19. 결과 파일 저장
20. 상태 조회 및 PDF 다운로드 API 구현
21. React 최소 작업 화면 구현
22. 관련 테스트 및 빌드 실행
23. 문서 최신화
24. 작업 결과 보고

### Phase 1 완료 기준

다음 시나리오가 실제로 동작해야 한다.

```text
1. 사용자가 PNG 파일 업로드
2. FastAPI가 Job ID 반환
3. PostgreSQL에 Job 기록
4. Redis를 통해 작업 전달
5. Celery Worker가 PDF 변환
6. PostgreSQL 작업 상태 갱신
7. React에서 작업 상태 확인
8. SUCCESS 확인
9. PDF 다운로드
10. 다운로드 PDF 정상 열기
```

이 흐름을 자동화 테스트 또는 재현 가능한 검증 절차로 확인한다.

Phase 2 이후의 기능은 이번 실행에서 개발하지 않는다.

다만 향후 멱등성, 복구, 다중 Worker 기능을 추가할 수 있도록 기본 구조를 설계한다.

### 최종 보고

작업 완료 후 다음 내용을 보고한다.

- 생성/수정 파일
- 프로젝트 아키텍처
- 기술 스택 및 버전
- 구현 기능
- Docker Compose 실행 결과
- API 동작 검증
- Worker 실제 실행 검증
- 테스트 및 빌드 결과
- 발견된 오류와 해결 내용
- 남은 제약
- 다음 Phase 작업

**이 프로젝트의 최종 목표는 파일 변환 기능 자체보다 요청 접수, 비동기 처리, 상태 추적, 실패 재처리, 중복 방지, Worker 장애 복구까지 안전하게 관리하는 플랫폼을 만드는 것이다.**

이제 Phase 0부터 분석, 설계, 구현을 진행하라.
