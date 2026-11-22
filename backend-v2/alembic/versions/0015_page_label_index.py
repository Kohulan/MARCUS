"""papers.rgroup_text_labels: per page, the R-group labels its text names

Revision ID: 0015
Revises: 0014

The docling step stores, per page (0-based, key a string), the R-group labels the R-group
model's context for that page names (marcus.core.rgroup_labels.page_label_index). The scaffold
tag, the exports and the UI list show only the labels a structure's page names (all of them
when it names none). NULL: no index (a paper read before this revision, or no readable text):
every label is shown, as before.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("rgroup_text_labels", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("papers", "rgroup_text_labels")
