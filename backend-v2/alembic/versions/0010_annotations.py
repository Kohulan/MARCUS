"""annotations: the MARCUS model's annotation of a paper, and the curator's corrections

Revision ID: 0010
Revises: 0009

One row per paper (owner decision 2026-11-20: annotation on demand). `output` and `positions`
come from the model run (marcus.workers.annotate); `curated` and `curated_positions` from the
curator (NULL: not corrected; "reset to model" sets them back to NULL). Deleting the paper row
deletes it (retention purge); deleting a paper (status `deleted`) deletes it at once
(pipeline.cancel_paper).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column(
            "paper_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("output", postgresql.JSONB, nullable=False),
        sa.Column("positions", postgresql.JSONB, nullable=False),
        sa.Column("curated", postgresql.JSONB, nullable=True),
        sa.Column("curated_positions", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("curated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("annotations")
