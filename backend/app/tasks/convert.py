import hashlib
import logging
import os
from uuid import uuid4
from sqlalchemy import update, select
from app.core.db import Session
from app.models.job import Job, JobFile, Result, now
from app.storage.local import storage
from app.converters.image_pdf import ImagePDFConverter, validate_pdf
from app.tasks.celery_app import celery_app
from app.schemas.options import ConversionOptions
from app.services.validation import InvalidInput, validate_image
from app.services.events import record_event

logger = logging.getLogger(__name__)


@celery_app.task(name="convertflow.convert")
def convert_job(job_id: str):
    with Session.begin() as db:
        claimed = db.execute(
            update(Job)
            .where(Job.job_id == job_id, Job.status == "QUEUED")
            .values(
                status="PROCESSING",
                stage="INPUT_VALIDATION",
                progress=10,
                started_at=now(),
            )
        ).rowcount
        if not claimed:
            return
        record_event(db, job_id, "PROCESSING", "Worker가 변환을 시작했습니다.")
    temporary = None
    current_file = None
    try:
        temporary = storage.path(f"processing/{job_id}/{uuid4()}/output.pdf")
        with Session() as db:
            job = db.get(Job, job_id)
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

        def on_page(file_index: int, page_index: int, completed: int):
            with Session.begin() as db:
                updated = db.execute(
                    update(Job)
                    .where(Job.job_id == job_id, Job.status == "PROCESSING")
                    .values(
                        stage="PAGE_PROCESSING",
                        progress=10 + int(75 * completed / total_pages),
                        processed_pages=completed,
                        processed_files=file_index
                        + int(page_index == files[file_index].page_count),
                    )
                ).rowcount
                if not updated:
                    raise RuntimeError("Job no longer belongs to this execution")
                record_event(
                    db,
                    job_id,
                    "PAGE_PROCESSED",
                    "이미지 페이지 처리 완료",
                    fileIndex=file_index,
                    pageIndex=page_index,
                    processedPages=completed,
                    totalPages=total_pages,
                )

        logger.info(
            "job=%s stage=converting files=%s pages=%s", job_id, len(files), total_pages
        )
        page_count = ImagePDFConverter().convert(sources, temporary, options, on_page)
        validate_pdf(temporary, total_pages)
        if page_count != total_pages:
            raise InvalidInput(
                "CONVERSION_FAILED", "PDF 페이지 수 검증에 실패했습니다."
            )
        with Session.begin() as db:
            db.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.status == "PROCESSING")
                .values(progress=95, stage="RESULT_VALIDATION")
            )
            record_event(
                db,
                job_id,
                "PDF_VALIDATED",
                "전체 PDF 페이지 검증 완료",
                pageCount=page_count,
            )
        result_relative = f"results/{job_id}/result.pdf"
        result = storage.path(result_relative)
        checksum = hashlib.sha256(temporary.read_bytes()).hexdigest()
        size = temporary.stat().st_size
        with Session.begin() as db:
            job = db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
            if job.status != "PROCESSING":
                return
            os.replace(temporary, result)
            db.add(
                Result(
                    job_id=job_id,
                    output_path=result_relative,
                    file_size=size,
                    checksum=checksum,
                    page_count=page_count,
                )
            )
            job.status = "SUCCESS"
            job.stage = "SUCCESS"
            job.progress = 100
            job.processed_files = job.total_files
            job.processed_pages = page_count
            job.completed_at = now()
            # Transitional compatibility fields for Phase 1 consumers/migration.
            job.output_path = result_relative
            job.output_size = size
            job.output_checksum = checksum
            record_event(
                db,
                job_id,
                "SUCCESS",
                "PDF 게시 완료",
                pageCount=page_count,
                fileSize=size,
            )
        logger.info("job=%s stage=success", job_id)
    except Exception as exc:
        logger.exception("job=%s stage=failed", job_id)
        code = (
            exc.code
            if isinstance(exc, InvalidInput)
            else "STORAGE_ERROR"
            if isinstance(exc, OSError)
            else "CONVERSION_FAILED"
        )
        message = (
            str(exc)
            if isinstance(exc, InvalidInput)
            else "파일 저장소 오류가 발생했습니다."
            if isinstance(exc, OSError)
            else "PDF 변환에 실패했습니다."
        )
        if current_file:
            message = f"{current_file}: {message}"
        with Session.begin() as db:
            updated = db.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.status == "PROCESSING")
                .values(
                    status="FAILED",
                    stage="FAILED",
                    error_code=code,
                    error_message=message,
                    completed_at=now(),
                )
            ).rowcount
            if updated:
                record_event(
                    db,
                    job_id,
                    "FAILED",
                    message,
                    errorCode=code,
                    exceptionType=type(exc).__name__,
                    filename=current_file,
                )
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
