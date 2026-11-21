"""segmentation cache support: steps.model_version, index on segments.image_sha256

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The model version a step's result came from (segment_page: the segmenter version). The
    # planner writes a paper's seg_cache row only when every page reports the same one.
    op.add_column("steps", sa.Column("model_version", sa.Text, nullable=True))
    # A cache hit copies each crop from any live paper that has the same bytes (by sha256).
    op.create_index("ix_segments_image_sha256", "segments", ["image_sha256"])


def downgrade() -> None:
    op.drop_index("ix_segments_image_sha256", table_name="segments")
    op.drop_column("steps", "model_version")
