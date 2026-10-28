from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, update
from app.core.config import settings
from app.models.job import Job, JobFile, Attempt, Outbox, now
from app.storage.local import storage
from app.storage.checksums import checksum as file_checksum
from app.services.events import record_event
from app.services.errors import MANUAL_RETRY_CODES, Failure, retry_delay
from app.services.leases import alive, clock


class Cancelled(Exception):
    pass


class StaleExecution(Exception):
    pass


def lock_job(db, job_id):
    return db.scalar(
        select(Job)
        .where(Job.job_id == str(job_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def cancel_locked(db, job, attempt=None):
    job.status = job.stage = "CANCELLED"
    job.next_retry_at = None
    job.completed_at = now()
    job.error_code = job.error_message = None
    job.active_attempt_id = None
    job.lease_expires_at = None
    if attempt:
        attempt.status = "CANCELLED"
        attempt.finished_at = now()
    record_event(
        db,
        job.job_id,
        "CANCELLED",
        "사용자 요청으로 작업을 취소했습니다.",
        attempt_id=attempt.attempt_id if attempt else None,
        generation=job.run_generation,
    )


def guard(db, job_id, generation, attempt_id):
    job = lock_job(db, job_id)
    if (
        not job
        or job.run_generation != generation
        or job.active_attempt_id != attempt_id
        or not alive(job, clock(db))
    ):
        raise StaleExecution()
    if job.status == "CANCEL_REQUESTED":
        raise Cancelled()
    if job.status != "PROCESSING":
        raise StaleExecution()
    return job


def fail_attempt(
    job_id, generation, attempt_id, failure: Failure, exception_type: str, filename=None
):
    from app.core.db import Session

    with Session.begin() as db:
        job = lock_job(db, job_id)
        if (
            not job
            or job.run_generation != generation
            or job.active_attempt_id != attempt_id
            or job.status not in {"PROCESSING", "CANCEL_REQUESTED"}
        ):
            return
        if not alive(job, clock(db)):
            return
        finish_failure(db, job, failure, exception_type, filename)


def finish_failure(db, job, failure, exception_type, filename=None):
    job_id = job.job_id
    attempt_id = job.active_attempt_id
    attempt = db.get(Attempt, attempt_id)
    if job.status == "CANCEL_REQUESTED":
        cancel_locked(db, job, attempt)
        return
    attempt.status = "FAILED"
    attempt.finished_at = now()
    attempt.error_code = failure.code
    attempt.error_message = failure.message
    attempt.retryable = failure.retryable
    job.error_code = failure.code
    job.error_message = failure.message
    job.active_attempt_id = None
    job.lease_expires_at = None
    record_event(
        db,
        job_id,
        "FAILED",
        failure.message,
        attempt_id=attempt_id,
        errorCode=failure.code,
        exceptionType=exception_type,
        retryable=failure.retryable,
        filename=filename,
    )
    if failure.retryable and job.auto_retry_count < settings.max_auto_retries:
        job.auto_retry_count += 1
        job.run_generation += 1
        job.retry_origin = "AUTO"
        job.status = job.stage = "RETRY_WAIT"
        job.next_retry_at = now() + timedelta(seconds=retry_delay(job.auto_retry_count))
        job.completed_at = None
        job.started_at = None
        db.add(
            Outbox(
                job_id=job_id,
                generation=job.run_generation,
                available_at=job.next_retry_at,
            )
        )
        record_event(
            db,
            job_id,
            "RETRY_SCHEDULED",
            "일시 오류로 자동 재시도를 예약했습니다.",
            attempt_id=attempt_id,
            retryNumber=job.auto_retry_count,
            generation=job.run_generation,
            nextRetryAt=job.next_retry_at.isoformat(),
        )
    else:
        job.status = job.stage = "FAILED"
        job.completed_at = now()


def request_retry(db, job_id, expected_generation: int):
    job = lock_job(db, job_id)
    if job.run_generation != expected_generation or job.status != "FAILED":
        raise HTTPException(
            409,
            detail={
                "code": "RETRY_CONFLICT",
                "message": "작업 상태가 변경되었습니다. 새로 조회해 주세요.",
            },
        )
    if job.error_code not in MANUAL_RETRY_CODES:
        raise HTTPException(
            409,
            detail={
                "code": "NOT_RETRYABLE",
                "message": "같은 입력과 옵션으로 재시도할 수 없는 오류입니다.",
            },
        )
    files = db.scalars(select(JobFile).where(JobFile.job_id == job.job_id)).all()
    if not files:
        raise HTTPException(
            409,
            detail={
                "code": "SOURCE_UNAVAILABLE",
                "message": "재시도할 원본 파일이 없습니다.",
            },
        )
    for file in files:
        path = storage.path(file.storage_path)
        if not path.is_file() or file_checksum(path) != file.checksum:
            raise HTTPException(
                409,
                detail={
                    "code": "SOURCE_UNAVAILABLE",
                    "message": "원본 파일이 없거나 변경되어 재시도할 수 없습니다.",
                },
            )
    updated = db.execute(
        update(Job)
        .where(
            Job.job_id == job.job_id,
            Job.status == "FAILED",
            Job.run_generation == expected_generation,
        )
        .values(
            status="QUEUED",
            stage="QUEUED",
            run_generation=expected_generation + 1,
            retry_origin="MANUAL",
            auto_retry_count=0,
            next_retry_at=None,
            progress=0,
            processed_files=0,
            processed_pages=0,
            started_at=None,
            completed_at=None,
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    if not updated:
        raise HTTPException(
            409,
            detail={
                "code": "RETRY_CONFLICT",
                "message": "이미 재시도가 요청되었습니다.",
            },
        )
    db.refresh(job)
    db.add(Outbox(job_id=job.job_id, generation=job.run_generation))
    record_event(
        db,
        job.job_id,
        "MANUAL_RETRY_REQUESTED",
        "동일 원본과 옵션으로 새 시도를 요청했습니다.",
        generation=job.run_generation,
        previousErrorCode=job.error_code,
    )
    return job


def request_cancel(db, job_id, expected_generation: int):
    job = lock_job(db, job_id)
    if job.run_generation != expected_generation:
        raise HTTPException(
            409,
            detail={
                "code": "CANCEL_CONFLICT",
                "message": "실행 세대가 변경되었습니다. 새로 조회해 주세요.",
            },
        )
    if job.status in {"CANCELLED", "CANCEL_REQUESTED"}:
        return job
    if job.status in {"SUCCESS", "FAILED"}:
        raise HTTPException(
            409,
            detail={"code": "CANCEL_CONFLICT", "message": "이미 종료된 작업입니다."},
        )
    previous = job.status
    updated = db.execute(
        update(Job)
        .where(
            Job.job_id == job.job_id,
            Job.run_generation == expected_generation,
            Job.status == previous,
        )
        .values(status="CANCEL_REQUESTED", stage="CANCEL_REQUESTED")
        .execution_options(synchronize_session=False)
    ).rowcount
    if not updated:
        raise HTTPException(
            409,
            detail={
                "code": "CANCEL_CONFLICT",
                "message": "작업 상태가 변경되었습니다.",
            },
        )
    db.refresh(job)
    if previous in {"QUEUED", "RETRY_WAIT"}:
        cancel_locked(db, job)
    else:
        record_event(
            db,
            job.job_id,
            "CANCEL_REQUESTED",
            "실행 중인 Worker에 취소를 요청했습니다.",
            attempt_id=job.active_attempt_id,
            generation=job.run_generation,
        )
    return job
