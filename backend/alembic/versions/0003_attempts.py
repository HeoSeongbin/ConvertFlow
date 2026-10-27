"""Persist attempts, dispatch generations, scheduled retry and cancellation."""

from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("run_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_attempt_id", sa.String(36)),
        sa.Column("auto_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column(
            "retry_origin", sa.String(16), nullable=False, server_default="INITIAL"
        ),
    ]:
        op.add_column("conversion_job", column)
    op.create_table(
        "conversion_attempt",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("conversion_job.job_id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("worker_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.Text()),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("job_id", "attempt_number"),
        sa.UniqueConstraint("job_id", "generation"),
        sa.CheckConstraint("attempt_number >= 1"),
    )
    op.create_index("ix_conversion_attempt_job_id", "conversion_attempt", ["job_id"])
    inspector = sa.inspect(op.get_bind())
    old_unique = next(
        c
        for c in inspector.get_unique_constraints("job_dispatch_outbox")
        if c["column_names"] == ["job_id"]
    )
    with op.batch_alter_table(
        "job_dispatch_outbox",
        naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
    ) as batch:
        batch.drop_constraint(
            old_unique["name"] or "uq_job_dispatch_outbox_job_id", type_="unique"
        )
        batch.add_column(
            sa.Column("generation", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.create_unique_constraint(
            "uq_outbox_job_generation", ["job_id", "generation"]
        )
    op.create_index(
        "ix_outbox_due", "job_dispatch_outbox", ["published_at", "available_at"]
    )
    for table in ("conversion_result", "conversion_event"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("attempt_id", sa.String(36)))
            batch.create_foreign_key(
                f"fk_{table}_attempt",
                "conversion_attempt",
                ["attempt_id"],
                ["attempt_id"],
            )
    bind = op.get_bind()
    meta = sa.MetaData()
    jobs = sa.Table("conversion_job", meta, autoload_with=bind)
    attempts = sa.Table("conversion_attempt", meta, autoload_with=bind)
    results = sa.Table("conversion_result", meta, autoload_with=bind)
    for row in bind.execute(sa.select(jobs)).mappings().all():
        if row["status"] not in ("SUCCESS", "FAILED", "PROCESSING"):
            continue
        identifier = str(uuid4())
        bind.execute(
            attempts.insert().values(
                attempt_id=identifier,
                job_id=row["job_id"],
                attempt_number=1,
                generation=1,
                origin="LEGACY",
                worker_name="UNKNOWN",
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["completed_at"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                retryable=False,
            )
        )
        bind.execute(
            jobs.update()
            .where(jobs.c.job_id == row["job_id"])
            .values(
                attempt_count=1,
                active_attempt_id=identifier if row["status"] == "PROCESSING" else None,
            )
        )
        bind.execute(
            results.update()
            .where(results.c.job_id == row["job_id"])
            .values(attempt_id=identifier)
        )


def downgrade():
    raise RuntimeError(
        "Downgrade would discard attempts and retry history; export/restore explicitly"
    )
