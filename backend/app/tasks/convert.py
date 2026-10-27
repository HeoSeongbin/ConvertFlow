import hashlib
import logging
import os
import socket
from uuid import uuid4
from celery import current_task
from sqlalchemy import update, select
from app.core.db import Session
from app.models.job import Job, JobFile, Result, Attempt, now
from app.storage.local import storage
from app.converters.image_pdf import ImagePDFConverter, validate_pdf
from app.tasks.celery_app import celery_app
from app.schemas.options import ConversionOptions
from app.services.validation import InvalidInput, validate_image
from app.services.events import record_event
from app.services.errors import classify_error, Failure
from app.services.lifecycle import (
    guard,
    lock_job,
    cancel_locked,
    fail_attempt,
    Cancelled,
    StaleExecution,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="convertflow.convert")
def convert_job(job_id: str, generation: int = 1):
    attempt_id = str(uuid4())
    with Session.begin() as db:
        claimed = db.execute(
            update(Job)
            .where(
                Job.job_id == job_id,
                Job.status == "QUEUED",
                Job.run_generation == generation,
            )
            .values(
                status="PROCESSING",
                stage="INPUT_VALIDATION",
                progress=10,
                processed_files=0,
                processed_pages=0,
                started_at=now(),
                completed_at=None,
                error_code=None,
                error_message=None,
                attempt_count=Job.attempt_count + 1,
                active_attempt_id=attempt_id,
            )
        ).rowcount
        if not claimed:
            return
        job = db.get(Job, job_id)
        worker = (
            getattr(getattr(current_task, "request", None), "hostname", None)
            or socket.gethostname()
        )
        db.add(
            Attempt(
                attempt_id=attempt_id,
                job_id=job_id,
                attempt_number=job.attempt_count,
                generation=generation,
                origin=job.retry_origin,
                worker_name=worker,
                status="PROCESSING",
                started_at=job.started_at,
            )
        )
        record_event(
            db,
            job_id,
            "PROCESSING",
            "Worker가 변환을 시작했습니다.",
            attempt_id=attempt_id,
            attemptNumber=job.attempt_count,
            generation=generation,
        )
    temporary = None
    current_file = None
    try:
        temporary = storage.path(f"processing/{job_id}/{attempt_id}/output.pdf")
        with Session.begin() as db:
            job = guard(db, job_id, generation, attempt_id)
            options = ConversionOptions.model_validate(job.options)
            files = db.scalars(
                select(JobFile)
                .where(JobFile.job_id == job_id)
                .order_by(JobFile.sort_order)
            ).all()
            total_pages = job.total_pages
        if not files:
            raise InvalidInput("INVALID_FILE", "입력 파일 정보가 없습니다.")
        sources = []
        for file in files:
            with Session.begin() as db:
                guard(db, job_id, generation, attempt_id)
            current_file = file.original_filename
            source = storage.path(file.storage_path)
            if hashlib.sha256(source.read_bytes()).hexdigest() != file.checksum:
                raise InvalidInput(
                    "INVALID_FILE", "입력 파일 무결성 검증에 실패했습니다."
                )
            info = validate_image(source, file.original_filename, file.mime_type)
            if info.page_count != file.page_count:
                raise InvalidInput("INVALID_FILE", "입력 페이지 정보가 변경되었습니다.")
            sources.append(source)
        current_file = None

        def on_page(file_index, page_index, completed):
            with Session.begin() as db:
                job = guard(db, job_id, generation, attempt_id)
                job.stage = "PAGE_PROCESSING"
                job.progress = 10 + int(75 * completed / total_pages)
                job.processed_pages = completed
                job.processed_files = file_index + int(
                    page_index == files[file_index].page_count
                )
                record_event(
                    db,
                    job_id,
                    "PAGE_PROCESSED",
                    "이미지 페이지 처리 완료",
                    attempt_id=attempt_id,
                    fileIndex=file_index,
                    pageIndex=page_index,
                    processedPages=completed,
                    totalPages=total_pages,
                )

        logger.info(
            "job=%s attempt=%s generation=%s stage=converting",
            job_id,
            attempt_id,
            generation,
        )
        page_count = ImagePDFConverter().convert(sources, temporary, options, on_page)
        validate_pdf(temporary, total_pages)
        if page_count != total_pages:
            raise InvalidInput(
                "CONVERSION_FAILED", "PDF 페이지 수 검증에 실패했습니다."
            )
        with Session.begin() as db:
            job = guard(db, job_id, generation, attempt_id)
            job.progress = 95
            job.stage = "RESULT_VALIDATION"
            record_event(
                db,
                job_id,
                "PDF_VALIDATED",
                "전체 PDF 페이지 검증 완료",
                attempt_id=attempt_id,
                pageCount=page_count,
            )
        relative = f"results/{job_id}/{attempt_id}.pdf"
        output = storage.path(relative)
        checksum = hashlib.sha256(temporary.read_bytes()).hexdigest()
        size = temporary.stat().st_size
        with Session.begin() as db:
            job = guard(db, job_id, generation, attempt_id)
            os.replace(temporary, output)
            db.add(
                Result(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    output_path=relative,
                    file_size=size,
                    checksum=checksum,
                    page_count=page_count,
                )
            )
            attempt = db.get(Attempt, attempt_id)
            attempt.status = "SUCCESS"
            attempt.finished_at = now()
            job.status = job.stage = "SUCCESS"
            job.progress = 100
            job.processed_files = job.total_files
            job.processed_pages = page_count
            job.completed_at = now()
            job.active_attempt_id = None
            job.next_retry_at = None
            job.output_path = relative
            job.output_size = size
            job.output_checksum = checksum
            record_event(
                db,
                job_id,
                "SUCCESS",
                "PDF 게시 완료",
                attempt_id=attempt_id,
                pageCount=page_count,
                fileSize=size,
            )
    except Cancelled:
        with Session.begin() as db:
            job = lock_job(db, job_id)
            if (
                job
                and job.run_generation == generation
                and job.active_attempt_id == attempt_id
                and job.status == "CANCEL_REQUESTED"
            ):
                cancel_locked(db, job, db.get(Attempt, attempt_id))
    except StaleExecution:
        logger.info("job=%s attempt=%s ignored stale execution", job_id, attempt_id)
    except Exception as exc:
        logger.exception("job=%s attempt=%s stage=failed", job_id, attempt_id)
        failure = classify_error(exc)
        if current_file:
            failure = Failure(
                failure.code, f"{current_file}: {failure.message}", failure.retryable
            )
        fail_attempt(
            job_id, generation, attempt_id, failure, type(exc).__name__, current_file
        )
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
