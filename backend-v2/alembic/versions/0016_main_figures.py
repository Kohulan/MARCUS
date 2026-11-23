"""main_figures: the page the user marked as a paper's compound list

Revision ID: 0016
Revises: 0015

The user marks one page of a paper as its main figure (the figure that lists every compound).
Its structures come first in the workspace; a structure on another page with the same
InChIKey as one of them is a repeat, linked to it and not counted twice
(marcus.core.main_figure). One row per paper at most (paper_id is the key); no row: no main
figure. Deleting the paper deletes the row.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "main_figures",
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("page >= 0", name="ck_main_figures_page"),
    )


def downgrade() -> None:
    op.drop_table("main_figures")
