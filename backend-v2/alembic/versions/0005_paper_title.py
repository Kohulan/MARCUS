"""papers.title: the paper title found with the DOI

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("title", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("papers", "title")
