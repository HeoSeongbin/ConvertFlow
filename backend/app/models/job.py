from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    String,
    DateTime,
    Integer,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Job(Base):
    __tablename__ = "conversion_job"
    __table_args__ = (
        Index("ix_job_workspace_created", "workspace_hash", "created_at"),
    )
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    access_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    workspace_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    total_files: Mapped[int] = mapped_column(Integer, default=1)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=1)
    processed_pages: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(40), default="QUEUED")
    original_filename: Mapped[str] = mapped_column(String(255))
    input_path: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(50))
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    output_path: Mapped[str | None] = mapped_column(Text)
    output_checksum: Mapped[str | None] = mapped_column(String(64))
    output_size: Mapped[int | None] = mapped_column(Integer)


class Outbox(Base):
    __tablename__ = "job_dispatch_outbox"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("conversion_job.job_id"), unique=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobFile(Base):
    __tablename__ = "conversion_job_file"
    __table_args__ = (
        UniqueConstraint("job_id", "sort_order"),
        CheckConstraint("page_count > 0"),
        CheckConstraint("sort_order >= 0"),
    )
    file_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("conversion_job.job_id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(50))
    page_count: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))


class Result(Base):
    __tablename__ = "conversion_result"
    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("conversion_job.job_id"), unique=True
    )
    output_path: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    __tablename__ = "conversion_event"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("conversion_job.job_id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("job_id", "sequence"),)
