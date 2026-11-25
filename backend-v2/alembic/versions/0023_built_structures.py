"""built structures: Markush Phase 3 (built_segments, scaffold_builds, engine enumerated)

Revision ID: 0023
Revises: 0022

Owner decision 2026-11-25: a scaffold's R-group rows can be built into full structures, each its
own card (marcus.core.built). A built structure is a segment (the scaffold's crop and position)
with a prediction of engine `enumerated`, linked to its scaffold in built_segments; the rows that
could not be built are kept in scaffold_builds. `enumerated` is allowed on predictions and steps
only (never a paper's or an image job's engine).

Downgrade: only while no prediction or step names `enumerated`.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

OLD = ("decimer", "decimer-hand", "molnextr", "molparser", "molscribe", "fake")
NEW = (*OLD, "enumerated")
CHECKS = (("steps", "ck_steps_engine", True), ("predictions", "ck_predictions_engine", False))
TZ = sa.TIMESTAMP(timezone=True)


def _checks(values) -> None:
    for table, name, nullable in CHECKS:
        op.drop_constraint(name, table, type_="check")
        cond = "engine IN (" + ", ".join(f"'{v}'" for v in values) + ")"
        op.create_check_constraint(name, table, ("engine IS NULL OR " if nullable else "") + cond)


def _fk(name: str, **kw) -> sa.Column:
    return sa.Column(
        name, pg.UUID(as_uuid=True), sa.ForeignKey("segments.id", ondelete="CASCADE"), **kw
    )


def upgrade() -> None:
    _checks(NEW)
    op.create_table(
        "built_segments",
        _fk("segment_id", primary_key=True),
        _fk("scaffold_segment_id", nullable=False),
        sa.Column("row_key", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("input_hash", pg.CHAR(64), nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "scaffold_segment_id", "row_key", name="uq_built_segments_scaffold_row"
        ),
    )
    op.create_index(
        "ix_built_segments_scaffold_segment_id", "built_segments", ["scaffold_segment_id"]
    )
    op.create_table(
        "scaffold_builds",
        _fk("scaffold_segment_id", primary_key=True),
        sa.Column("failures", pg.JSONB, nullable=False),
        sa.Column("built_at", TZ, nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM predictions WHERE engine = 'enumerated')
               OR EXISTS (SELECT 1 FROM steps WHERE engine = 'enumerated') THEN
                RAISE EXCEPTION 'rows with engine enumerated exist: restore the database dump';
            END IF;
        END
        $$
        """
    )
    op.drop_table("scaffold_builds")
    op.drop_index("ix_built_segments_scaffold_segment_id", table_name="built_segments")
    op.drop_table("built_segments")
    _checks(OLD)
