# Phase 5 실측 — 2026-10-28

모든 값은 실제 실행 결과다. 합성 fixture와 소규모 로컬 부하를 사용했으며 운영 용량·일반적인 선형 확장·장기 메모리 누수 검증을 의미하지 않는다. 새 의존성은 추가하지 않았다.

## 메모리와 변환 동등성
Linux API 이미지의 별도 Python 3.12 interpreter에서 각 방식 3회 실행했다. 기준 코드는 Git `b2fd27c`의 `backend/app/converters/image_pdf.py`다. /proc/self/status의 VmHWM은 해당 프로세스 전체 최고 RSS이며 작업당 증분이나 Worker 컨테이너 전체 사용량은 아니다. 측정 뒤 PDF 페이지와 이미지 해시를 비교해 결과가 같은지 검사했다.

| 항목 | Phase 4 중앙값 | Phase 5 중앙값 |
|---|---:|---:|
| 8페이지 2048×2048 RGB TIFF peak RSS | 163.63 MiB | 115.41 MiB |
| 위 converter 실행 시간 | 0.2721초 | 0.1428초 |
| 64 MiB 합성 파일 checksum peak RSS | 110.19 MiB | 46.32 MiB |
| 위 checksum 실행 시간 | 0.0463초 | 0.0309초 |

RGB 경로에서 RGBA·흰 RGB 복사를 생략하고 checksum을 streaming으로 바꿨다. 8페이지와 각 이미지 해시, 파일 checksum이 일치했다. TIFF는 gradient로 생성하며 checksum fixture는 고정 64 MiB binary다. alpha·기타 포맷은 기존 회귀 테스트로 별도 검증한다. 인코딩 PDF 객체 전체 보관은 남는다.

초기 ru_maxrss 비교는 fork/exec 이전 부모의 fixture 생성 peak가 섞여 모든 값이 같게 나왔다. 해당 결과는 채택하지 않았고 VmHWM으로 다시 측정했다. 원본: [phase5-memory.json](phase5-memory.json).

## PostgreSQL 복합 인덱스
제품 테이블을 변경하지 않는 TEMP Job/Attempt fixture를 각각 100,000행 생성하고 rollback했다. 기존 단일 인덱스를 유지한 상태와 0005 복합 인덱스 추가 상태를 같은 조건으로 비교했다. 한 번 warm-up 후 EXPLAIN ANALYZE/BUFFERS 3회의 실행 시간 중앙값이다.

| 쿼리 | 기존 인덱스 | 복합 인덱스 추가 |
|---|---:|---:|
| 만료 Lease 조회 | 0.193ms | 0.055ms |
| workspace 최근 완료 집계 | 1.470ms | 0.046ms |
| Job의 최근 완료 Attempt 집계 | 0.254ms | 0.037ms |

Job fixture는 10% PROCESSING, 소수 만료, 10개 workspace의 분포다. Attempt fixture는 100개 Job에 많은 이력을 집중시켜 시간 조건의 선택도를 확인한다. 이 분포에서의 warm-cache 실행 계획 비교이며 실제 기존 소규모 데이터나 모든 분포에서 같은 이득을 보장하지 않는다. 초기 선택도 차이가 없는 fixture에서는 개선이 확인되지 않았으며 fixture 생성 SQL과 모든 채택 실행 계획을 보존한다. 원본: [phase5-indexes.json](phase5-indexes.json).

## 실제 Compose 부하·큐·확장
호스트 Python HTTP 클라이언트→실제 API/PostgreSQL/Redis/Compose prefork Worker를 사용했다. 컨테이너당 concurrency=1, CPU=1, memory=768 MiB이며 Worker 1개와 2개를 각각 한 배치씩 측정했다.

- 경계 입력: 20파일×5프레임=100페이지, 960²×100=92,160,000 pixels. 정상 PDF 100페이지, 단일 Attempt 성공.
- 부하: 6 Job×8페이지 1024² TIFF, 파일당 132,640 bytes. HTTP 요청 병렬도 3.
- 전체 시간은 업로드 시작→모든 SUCCESS 조회까지이며 PDF 다운로드 검증 시간은 제외한다. poll 간격 0.5초가 포함되고 엄밀한 서버 처리량 측정은 아니다.

| 구성 | 전체 시간 | 환산 Job/분 | 성공 실행 중앙값 | 성공 실행 p95 (nearest rank, n=6) | 실제 작업 분배 |
|---|---:|---:|---:|---:|---|
| Worker 1개 | 2.3691초 | 151.96 | 0.1089초 | 0.1193초 | 6 |
| Worker 2개 | 3.3718초 | 106.77 | 0.1141초 | 0.1719초 | 3 + 3 |

작은 입력의 업로드·DB·수집 오버헤드가 포함되어 이번 측정에서 Worker 2개가 더 느렸다. 부하 반복·큰 실사용 사진·CPU 포화·지속 부하에서의 확장 효과는 추가 측정이 필요하다. 기본 Worker는 1개로 복원했다.

같은 harness에서 Worker 중지 중 실제 큐 양수, 정상 큐 0, workspace 통계 격리, Observer 중단 후 stale UNKNOWN/null 및 재기동 복귀를 확인했다. 별도 활성 Task 검증은 새 테스트 입력만 FIFO로 잠깐 교체하고 실제 Job ID·Heartbeat·활성 Task 1개를 확인한 뒤 파일을 복원해 같은 Attempt를 성공시켰다. 원본: [phase5-load.json](phase5-load.json), [phase5-active.json](phase5-active.json).

## 재현
다른 실행 중 작업이 없는 localhost 개발 스택에서 실행한다. Worker scale/Observer 중단을 포함하며 finally로 Worker 1개와 Observer를 복원한다. 기존 볼륨을 삭제하지 않고 생성한 Job을 실제 이력으로 남긴다.

```bash
python scripts/benchmark_phase5.py --output .storage/phase5-load.json
python scripts/smoke_phase5_active.py
docker compose cp scripts/benchmark_indexes.py api:/tmp/benchmark_indexes.py
docker compose exec -T -e PYTHONPATH=/app api python /tmp/benchmark_indexes.py
```

메모리 비교는 기준 소스를 UTF-8로 저장해 전달한다. PowerShell에서는 `Set-Content -Encoding utf8`로 저장할 수 있다.

```bash
git show b2fd27c:backend/app/converters/image_pdf.py > .storage/phase4_converter.py
docker compose cp .storage/phase4_converter.py api:/tmp/phase4_converter.py
docker compose cp scripts/benchmark_memory.py api:/tmp/benchmark_memory.py
docker compose exec -T -e PYTHONPATH=/app api python /tmp/benchmark_memory.py /tmp/phase4_converter.py
```
