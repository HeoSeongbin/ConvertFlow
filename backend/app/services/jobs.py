import hashlib
import secrets
from datetime import timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models.job import Job, JobFile, Result
from app.schemas.options import ConversionOptions

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


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def serialize(job, db=None):
    elapsed = (
        (job.completed_at - job.started_at).total_seconds()
        if job.completed_at and job.started_at
        else None
    )
    result = {
        "jobId": job.job_id,
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
            for f in db.scalars(
                select(JobFile)
                .where(JobFile.job_id == job.job_id)
                .order_by(JobFile.sort_order)
            )
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
