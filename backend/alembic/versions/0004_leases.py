"""Bound execution ownership with expiring leases; retain all history."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversion_job", sa.Column("heartbeat_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "conversion_job", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_conversion_job_lease_expires_at", "conversion_job", ["lease_expires_at"]
    )
    # Old workers must be drained before migration; NULL running leases are recoverable.


def downgrade():
    raise RuntimeError(
        "Lease ownership downgrade requires an explicit offline migration"
    )
