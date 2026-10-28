import hashlib
import secrets
from datetime import timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models.job import Job, JobFile, Result
from app.schemas.options import ConversionOptions
from app.services.errors import MANUAL_RETRY_CODES
from app.storage.local import storage

WORKSPACE_COOKIE = "cf_workspace"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authorized(db, job_id, token=None, workspace=None):
    job = db.get(Job, str(job_id))
    if job and (
        (token and secrets.compare_digest(job.access_hash, token_hash(token)))
        or (
            workspace
            and job.workspace_hash
            and secrets.compare_digest(job.workspace_hash, token_hash(workspace))
        )
    ):
        return job
    raise HTTPException(
        404, detail={"code": "NOT_FOUND", "message": "작업을 찾을 수 없습니다."}
    )


def utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def iso(value):
    return utc(value).isoformat() if value else None


def serialize(job, db=None):
    elapsed = (
        (utc(job.completed_at) - utc(job.started_at)).total_seconds()
        if job.completed_at and job.started_at
        else None
    )
    result = {
        "jobId": job.job_id,
        "runGeneration": job.run_generation,
        "attemptCount": job.attempt_count,
        "heartbeatAt": iso(job.heartbeat_at),
        "leaseExpiresAt": iso(job.lease_expires_at),
        "autoRetryCount": job.auto_retry_count,
        "nextRetryAt": iso(job.next_retry_at),
        "canRetry": job.status == "FAILED" and job.error_code in MANUAL_RETRY_CODES,
        "canCancel": job.status in {"QUEUED", "PROCESSING", "RETRY_WAIT"},
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "filename": job.original_filename,
        "createdAt": iso(job.created_at),
        "startedAt": iso(job.started_at),
        "completedAt": iso(job.completed_at),
        "durationSeconds": elapsed,
        "totalFiles": job.total_files,
        "processedFiles": job.processed_files,
        "totalPages": job.total_pages,
        "processedPages": job.processed_pages,
        "errorCode": job.error_code,
        "errorMessage": job.error_message,
        "downloadAvailable": job.status == "SUCCESS" and bool(job.output_path),
    }
    if db is not None:
        result["options"] = ConversionOptions.model_validate(job.options).model_dump(
            by_alias=True
        )
        files = list(
            db.scalars(
                select(JobFile)
                .where(JobFile.job_id == job.job_id)
                .order_by(JobFile.sort_order)
            )
        )
        available = bool(files) and all(
            storage.path(file.storage_path).is_file() for file in files
        )
        result["sourceAvailable"] = available
        result["canRetry"] = result["canRetry"] and available
        result["retryBlockedReason"] = (
            "원본 파일이 없습니다."
            if not available
            else "입력 또는 옵션을 변경해야 하는 오류입니다."
            if job.status == "FAILED" and not result["canRetry"]
            else None
        )
        result["files"] = [
            {
                "fileId": f.file_id,
                "filename": f.original_filename,
                "fileSize": f.file_size,
                "mimeType": f.mime_type,
                "pageCount": f.page_count,
                "sortOrder": f.sort_order,
                "checksum": f.checksum,
            }
            for f in files
        ]
        output = db.scalar(select(Result).where(Result.job_id == job.job_id))
        result["result"] = (
            {
                "fileSize": output.file_size,
                "pageCount": output.page_count,
                "checksum": output.checksum,
            }
            if output
            else None
        )
    return result
