"""background_steps and predictions.inchikey: every structure read by three engines

Revision ID: 0019
Revises: 0018

Phase B item 3: a new paper's segments are read by DECIMER, MolNexTR and MolScribe. The
paper's own engine is its read; the other two run in the background (one background_steps row
per such OCSR step): they never keep the paper busy, count in its progress or fail it. A table
of its own, not a steps column: the migration tests of older revisions write steps through the
ORM. predictions.inchikey (a valid structure's InChIKey, written as the prediction lands) is
what the engines agree on (marcus.core.agreement); NULL for predictions made before this
revision (no backfill: older cards keep the structure they show).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_steps",
        sa.Column(
            "step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("steps.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.add_column("predictions", sa.Column("inchikey", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("predictions", "inchikey")
    op.drop_table("background_steps")
