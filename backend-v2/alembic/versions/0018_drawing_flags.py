"""drawing_flags: crops that are not a clean drawing ("check this drawing")

Revision ID: 0018
Revises: 0017

One row per flagged segment, written when the segment_page step makes the crop
(marcus.workers.drawing_check): a drawing covered with NMR marks, or an X-ray / 3D picture. No
row: a clean drawing, or a segment from before this revision (no backfill). A table of its own,
not a segments column: the migration tests of older revisions insert segments through the ORM.
Deleting the segment deletes the row.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drawing_flags",
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("segments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("drawing_flags")
