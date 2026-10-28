import hashlib
import secrets
from uuid import UUID, uuid4
from typing import Literal
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Header,
    Request,
    Response,
    Query,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError, BaseModel, Field, ConfigDict
from sqlalchemy import select, func, or_
from app.core.db import Session
from app.core.config import settings
from app.models.job import Job, JobFile, Outbox, Result, Event, Attempt
from app.storage.local import storage
from app.storage.checksums import checksum as file_checksum
from app.services.validation import validate_image, InvalidInput
from app.services.jobs import authorized, serialize, token_hash, WORKSPACE_COOKIE, iso
from app.services.events import record_event
from app.schemas.options import ConversionOptions

router = APIRouter(prefix="/api/v1/jobs")


@router.post("", status_code=202)
def create_job(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(..., alias="file", min_length=1, max_length=20),
    options: str = Form("{}"),
):
    paths = []
    try:
        try:
            parsed = ConversionOptions.model_validate_json(options)
        except ValidationError as exc:
            raise InvalidInput(
                "INVALID_OPTIONS", "PDF 출력 옵션을 확인하세요."
            ) from exc
        if len(files) > settings.max_files:
            raise InvalidInput("FILE_LIMIT_EXCEEDED", "파일 개수 제한을 초과했습니다.")
        job_id, token = str(uuid4()), secrets.token_urlsafe(32)
        workspace = request.cookies.get(WORKSPACE_COOKIE)
        if not workspace or not 32 <= len(workspace) <= 128:
            workspace = secrets.token_urlsafe(32)
        metadata = []
        total_size = total_pages = total_pixels = 0
        for index, file in enumerate(files):
            relative = f"uploads/{job_id}/{uuid4()}"
            path = storage.path(relative)
            paths.append(path)
            size = 0
            digest = hashlib.sha256()
            filename = (
                (file.filename or "image").replace("\\", "/").split("/")[-1][:255]
            )
            try:
                with path.open("wb") as target:
                    while chunk := file.file.read(1024 * 1024):
                        size += len(chunk)
                        total_size += len(chunk)
                        if (
                            size > settings.max_upload_bytes
                            or total_size > settings.max_total_upload_bytes
                        ):
                            raise InvalidInput(
                                "FILE_TOO_LARGE",
                                "개별 20 MiB 또는 전체 100 MiB 제한을 초과했습니다.",
                            )
                        target.write(chunk)
                        digest.update(chunk)
                info = validate_image(path, filename, file.content_type)
                total_pages += info.page_count
                total_pixels += info.pixels
                if total_pages > settings.max_pages:
                    raise InvalidInput(
                        "PAGE_LIMIT_EXCEEDED", "작업은 최대 100페이지까지 지원합니다."
                    )
                if total_pixels > settings.max_total_pixels:
                    raise InvalidInput(
                        "PIXEL_LIMIT_EXCEEDED", "작업 전체 픽셀 제한을 초과했습니다."
                    )
            except InvalidInput as exc:
                raise InvalidInput(exc.code, f"{filename}: {exc}") from exc
            metadata.append(
                dict(
                    original_filename=filename,
                    storage_path=relative,
                    file_size=size,
                    mime_type=info.mime_type,
                    page_count=info.page_count,
                    sort_order=index,
                    checksum=digest.hexdigest(),
                )
            )
        with Session.begin() as db:
            first = metadata[0]
            job = Job(
                job_id=job_id,
                access_hash=token_hash(token),
                workspace_hash=token_hash(workspace),
                original_filename=first["original_filename"],
                input_path=first["storage_path"],
                file_size=total_size,
                mime_type=first["mime_type"],
                checksum=first["checksum"],
                options=parsed.model_dump(by_alias=True),
                total_files=len(files),
                total_pages=total_pages,
            )
            db.add(job)
            db.flush()
            db.add_all(JobFile(job_id=job_id, **item) for item in metadata)
            db.add(Outbox(job_id=job_id))
            record_event(
                db,
                job_id,
                "QUEUED",
                "파일 검증 완료, 변환 대기 중",
                totalFiles=len(files),
                totalPages=total_pages,
            )
            result = serialize(job)
        response.set_cookie(
            WORKSPACE_COOKIE,
            workspace,
            httponly=True,
            samesite="lax",
            max_age=30 * 86400,
            path="/api/v1",
        )
        return {**result, "accessToken": token}
    except InvalidInput as exc:
        for path in paths:
            path.unlink(missing_ok=True)
        raise HTTPException(
            422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        for file in files:
            file.file.close()


@router.get("")
def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    status: Literal[
        "QUEUED",
        "PROCESSING",
        "SUCCESS",
        "FAILED",
        "RETRY_WAIT",
        "CANCEL_REQUESTED",
        "CANCELLED",
    ]
    | None = None,
    search: str = Query("", max_length=120),
    retry_center: bool = Query(False, alias="retryCenter"),
):
    workspace = request.cookies.get(WORKSPACE_COOKIE)
    if not workspace:
        return {"items": [], "total": 0, "page": page, "pageSize": page_size}
    filters = [Job.workspace_hash == token_hash(workspace)]
    if retry_center:
        filters.append(Job.status.in_(["FAILED", "RETRY_WAIT"]))
    if status:
        filters.append(Job.status == status)
    if search.strip():
        text = search.strip()
        matching = select(JobFile.job_id).where(
            JobFile.original_filename.contains(text, autoescape=True)
        )
        filters.append(
            or_(Job.job_id.contains(text, autoescape=True), Job.job_id.in_(matching))
        )
    with Session() as db:
        total = db.scalar(select(func.count()).select_from(Job).where(*filters))
        jobs = db.scalars(
            select(Job)
            .where(*filters)
            .order_by(Job.created_at.desc(), Job.job_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        jobs = list(jobs)
        from app.services.errors import MANUAL_RETRY_CODES

        eligible = [
            job.job_id
            for job in jobs
            if job.status == "FAILED" and job.error_code in MANUAL_RETRY_CODES
        ]
        source_files = {}
        if eligible:
            for file in db.scalars(select(JobFile).where(JobFile.job_id.in_(eligible))):
                source_files.setdefault(file.job_id, []).append(file)
        items = []
        for job in jobs:
            item = serialize(job)
            if item["canRetry"]:
                files = source_files.get(job.job_id, [])
                available = bool(files) and all(
                    storage.path(file.storage_path).is_file() for file in files
                )
                item["canRetry"] = available
                item["sourceAvailable"] = available
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }


@router.get("/{job_id}")
def get_job(
    job_id: UUID, request: Request, x_job_token: str | None = Header(default=None)
):
    with Session() as db:
        return serialize(
            authorized(db, job_id, x_job_token, request.cookies.get(WORKSPACE_COOKIE)),
            db,
        )


@router.get("/{job_id}/events")
def get_events(
    job_id: UUID,
    request: Request,
    x_job_token: str | None = Header(default=None),
    after: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    order: Literal["asc", "desc"] = "asc",
    before: int | None = Query(None, ge=1),
):
    with Session() as db:
        authorized(db, job_id, x_job_token, request.cookies.get(WORKSPACE_COOKIE))
        query = select(Event).where(Event.job_id == str(job_id), Event.sequence > after)
        if before is not None:
            query = query.where(Event.sequence < before)
        events = db.scalars(
            query.order_by(
                Event.sequence.desc() if order == "desc" else Event.sequence
            ).limit(limit + 1)
        ).all()
        visible = events[:limit]
        return {
            "items": [
                {
                    "eventId": e.event_id,
                    "attemptId": e.attempt_id,
                    "sequence": e.sequence,
                    "type": e.event_type,
                    "message": e.message,
                    "details": e.details,
                    "createdAt": iso(e.created_at),
                }
                for e in visible
            ],
            "nextAfter": visible[-1].sequence if visible and order == "asc" else after,
            "nextBefore": visible[-1].sequence
            if visible and order == "desc"
            else before,
            "hasMore": len(events) > limit,
        }


@router.get("/{job_id}/download")
def download(
    job_id: UUID, request: Request, x_job_token: str | None = Header(default=None)
):
    with Session() as db:
        job = authorized(db, job_id, x_job_token, request.cookies.get(WORKSPACE_COOKIE))
        if job.status != "SUCCESS" or not job.output_path:
            raise HTTPException(
                409,
                detail={"code": "NOT_READY", "message": "결과가 준비되지 않았습니다."},
            )
        result = db.scalar(select(Result).where(Result.job_id == job.job_id))
        path = storage.path(result.output_path if result else job.output_path)
        expected_size = result.file_size if result else job.output_size
        expected_hash = result.checksum if result else job.output_checksum
        if (
            not path.is_file()
            or path.stat().st_size != expected_size
            or file_checksum(path) != expected_hash
        ):
            raise HTTPException(
                410,
                detail={
                    "code": "RESULT_UNAVAILABLE",
                    "message": "결과 파일을 확인할 수 없습니다.",
                },
            )
        return FileResponse(
            path, media_type="application/pdf", filename=f"convertflow-{job_id}.pdf"
        )


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_generation: int = Field(alias="expectedGeneration", ge=1, strict=True)


@router.post("/{job_id}/retry", status_code=202)
def retry(
    job_id: UUID,
    body: ExecutionRequest,
    request: Request,
    x_job_token: str | None = Header(default=None),
):
    from app.services.lifecycle import request_retry

    with Session.begin() as db:
        authorized(db, job_id, x_job_token, request.cookies.get(WORKSPACE_COOKIE))
        return serialize(request_retry(db, job_id, body.expected_generation))


@router.post("/{job_id}/cancel", status_code=202)
def cancel(
    job_id: UUID,
    body: ExecutionRequest,
    request: Request,
    x_job_token: str | None = Header(default=None),
):
    from app.services.lifecycle import request_cancel

    with Session.begin() as db:
        authorized(db, job_id, x_job_token, request.cookies.get(WORKSPACE_COOKIE))
        return serialize(request_cancel(db, job_id, body.expected_generation))


@router.get("/{job_id}/attempts")
def attempts(
    job_id: UUID,
    request: Request,
    x_job_token: str | None = Header(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
):
    with Session() as db:
        authorized(db, job_id, x_job_token, request.cookies.get(WORKSPACE_COOKIE))
        count = db.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.job_id == str(job_id))
        )
        rows = db.scalars(
            select(Attempt)
            .where(Attempt.job_id == str(job_id))
            .order_by(Attempt.attempt_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [
                {
                    "attemptId": a.attempt_id,
                    "attemptNumber": a.attempt_number,
                    "generation": a.generation,
                    "origin": a.origin,
                    "workerName": a.worker_name,
                    "status": a.status,
                    "startedAt": iso(a.started_at),
                    "finishedAt": iso(a.finished_at),
                    "errorCode": a.error_code,
                    "errorMessage": a.error_message,
                    "retryable": a.retryable,
                }
                for a in rows
            ],
            "total": count,
            "page": page,
            "pageSize": page_size,
        }
