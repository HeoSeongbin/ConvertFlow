"""Initial single-image jobs and transactional dispatch outbox."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversion_job",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column("access_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.Text()),
        sa.Column("output_path", sa.Text()),
        sa.Column("output_checksum", sa.String(64)),
        sa.Column("output_size", sa.Integer()),
    )
    op.create_index("ix_conversion_job_status", "conversion_job", ["status"])
    op.create_table(
        "job_dispatch_outbox",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("conversion_job.job_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("job_dispatch_outbox")
    op.drop_index("ix_conversion_job_status", table_name="conversion_job")
    op.drop_table("conversion_job")
