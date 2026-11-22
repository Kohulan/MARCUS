"""rgroup_extractions: the R-group model's rows for a scaffold, and the `rgroups` step kind

Revision ID: 0012
Revises: 0011

One row per prediction (Markush Phase 2: on demand, for a prediction with R-group labels). The
request writes it (labels, status `queued`, the step); the step's end sets `done` with the rows,
model and version, or `failed` with the error class. A re-run replaces the rows when it ends
well. Deleting the prediction deletes the row; deleting a paper (status `deleted`) deletes its
rows at once (pipeline.cancel_paper). The new step kind `rgroups` joins ck_steps_kind.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

KINDS = ("check_pdf", "render_page", "segment_page", "ocsr", "docling", "doi", "annotate")


def _kinds(kinds) -> str:
    return "kind IN (" + ", ".join(f"'{k}'" for k in kinds) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_steps_kind", "steps", type_="check")
    op.create_check_constraint("ck_steps_kind", "steps", _kinds((*KINDS, "rgroups")))
    op.create_table(
        "rgroup_extractions",
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "step_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("labels", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("rows", postgresql.JSONB, nullable=True),
        sa.Column("truncated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("model", sa.Text, nullable=True),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'done', 'failed')", name="ck_rgroup_extractions_status"
        ),
    )
    op.create_index("ix_rgroup_extractions_step_id", "rgroup_extractions", ["step_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_rgroup_extractions_step_id", table_name="rgroup_extractions")
    op.drop_table("rgroup_extractions")
    op.execute("DELETE FROM steps WHERE kind = 'rgroups'")
    op.drop_constraint("ck_steps_kind", "steps", type_="check")
    op.create_check_constraint("ck_steps_kind", "steps", _kinds(KINDS))
