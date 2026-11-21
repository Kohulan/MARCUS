"""papers.started_ip, image_jobs.started_ip: the per-address active cap counts the work's own
address (review I-1)

Revision ID: 0008
Revises: 0007

The per-address active-work cap counted active work by its owner's `created_ip`, which the
retention purge now deletes after `owner_ip_retention_days`: an aged owner's work fell out of its
address's count (and into the unknown bucket). The address bucket that started the work is now
kept on the work itself while it is active, and cleared when it finishes, fails or is deleted.
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TABLES = ("papers", "image_jobs")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("started_ip", sa.Text, nullable=True))
        op.create_index(f"ix_{table}_started_ip", table, ["started_ip"])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_started_ip", table_name=table)
        op.drop_column(table, "started_ip")
