"""papers.first_author, papers.year: found with the DOI, with the title

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("first_author", sa.Text, nullable=True))
    op.add_column("papers", sa.Column("year", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("papers", "year")
    op.drop_column("papers", "first_author")
