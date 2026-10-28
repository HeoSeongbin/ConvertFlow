"""Monitoring observations and query indexes; no changes to existing history."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitor_snapshot",
        sa.Column("key", sa.String(24), primary_key=True),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_table(
        "worker_observation",
        sa.Column("worker_name", sa.String(255), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responding", sa.Boolean(), nullable=False),
        sa.Column("concurrency", sa.Integer()),
        sa.Column("active_job_ids", sa.JSON()),
        sa.Column("active_count", sa.Integer()),
    )
    op.create_index(
        "ix_job_status_lease", "conversion_job", ["status", "lease_expires_at"]
    )
    op.create_index(
        "ix_job_workspace_completed",
        "conversion_job",
        ["workspace_hash", "completed_at"],
    )
    op.create_index(
        "ix_attempt_job_finished", "conversion_attempt", ["job_id", "finished_at"]
    )


def downgrade():
    raise RuntimeError(
        "Monitoring observation history requires an explicit offline downgrade"
    )
