"""inherited_statuses: curation statuses a structure got from its main-figure group

Revision ID: 0017
Revises: 0016

A decision on a main-figure structure goes to its repeats too (marcus.api.decisions). Such a
repeat's status is inherited: this row names the main structure it came from. While the
structure is no longer a repeat of that main one (the page unmarked or moved, a structure
edited, a page read again), its status reads as "unchecked" everywhere (marcus.core.main_figure
stale_members): an inherited decision is never exported unreviewed. A decision on the
structure's own card deletes the row. main_id has no foreign key on purpose: the row must
outlive its main segment (a page retry replaces it). Deleting the structure deletes the row.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inherited_statuses",
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("segments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("main_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("inherited_statuses")
