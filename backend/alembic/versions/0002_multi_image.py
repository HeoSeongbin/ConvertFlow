"""Multi-file options, results, workspace-scoped history and immutable events."""

from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("workspace_hash", sa.String(64)),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("processed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_pages", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("processed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(40), nullable=False, server_default="QUEUED"),
    ]:
        op.add_column("conversion_job", column)
    op.create_index(
        "ix_conversion_job_workspace_hash", "conversion_job", ["workspace_hash"]
    )
    op.create_index(
        "ix_job_workspace_created", "conversion_job", ["workspace_hash", "created_at"]
    )
    op.create_table(
        "conversion_job_file",
        sa.Column("file_id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("conversion_job.job_id"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.UniqueConstraint("job_id", "sort_order"),
        sa.CheckConstraint("page_count > 0"),
        sa.CheckConstraint("sort_order >= 0"),
    )
    op.create_index("ix_conversion_job_file_job_id", "conversion_job_file", ["job_id"])
    op.create_table(
        "conversion_result",
        sa.Column("result_id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("conversion_job.job_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "conversion_event",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("conversion_job.job_id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "sequence"),
    )
    op.create_index("ix_conversion_event_job_id", "conversion_event", ["job_id"])
    bind = op.get_bind()
    meta = sa.MetaData()
    jobs = sa.Table("conversion_job", meta, autoload_with=bind)
    files = sa.Table("conversion_job_file", meta, autoload_with=bind)
    results = sa.Table("conversion_result", meta, autoload_with=bind)
    events = sa.Table("conversion_event", meta, autoload_with=bind)
    for row in bind.execute(sa.select(jobs)).mappings().all():
        bind.execute(
            files.insert().values(
                file_id=str(uuid4()),
                job_id=row["job_id"],
                original_filename=row["original_filename"],
                storage_path=row["input_path"],
                file_size=row["file_size"],
                mime_type=row["mime_type"],
                page_count=1,
                sort_order=0,
                checksum=row["checksum"],
            )
        )
        terminal = row["status"] in ("SUCCESS", "FAILED")
        bind.execute(
            jobs.update()
            .where(jobs.c.job_id == row["job_id"])
            .values(
                stage=row["status"],
                processed_files=1 if row["status"] == "SUCCESS" else 0,
                processed_pages=1 if row["status"] == "SUCCESS" else 0,
            )
        )
        if row["status"] == "SUCCESS" and row["output_path"]:
            bind.execute(
                results.insert().values(
                    result_id=str(uuid4()),
                    job_id=row["job_id"],
                    output_path=row["output_path"],
                    file_size=row["output_size"],
                    checksum=row["output_checksum"],
                    page_count=1,
                    created_at=row["completed_at"] or row["created_at"],
                )
            )
        bind.execute(
            events.insert().values(
                event_id=str(uuid4()),
                job_id=row["job_id"],
                sequence=1,
                event_type="LEGACY_IMPORTED",
                message="Phase 1 작업 이관 (과거 단계별 기록 없음)",
                details={
                    "status": row["status"],
                    "errorCode": row["error_code"],
                    "terminal": terminal,
                },
                created_at=row["created_at"],
            )
        )


def downgrade():
    # Downgrade would discard multi-file metadata/history: require an explicit export instead.
    raise RuntimeError(
        "Phase 2 downgrade is intentionally blocked to preserve file and event history"
    )
