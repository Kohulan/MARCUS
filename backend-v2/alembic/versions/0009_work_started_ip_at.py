"""papers.started_ip_at, image_jobs.started_ip_at: when the work's address was last set
(re-review of the security follow-up, Minor 3)

Revision ID: 0009
Revises: 0008

The retention backstop cleared an active work's address by the work's `created_at`, so a paper
reopened after `owner_ip_retention_days` lost the address it had just been given and left the
per-address cap. The address is now aged by when it was set (creation or reopen). Rows from
before this revision keep NULL and fall back to `created_at`.
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TABLES = ("papers", "image_jobs")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("started_ip_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "started_ip_at")
