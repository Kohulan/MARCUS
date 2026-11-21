"""predictions.rgroups and curation.rgroups: the R-group labels of a structure

Revision ID: 0011
Revises: 0010

The labels (R1, X, Ar...) of the R-group placeholders in a prediction's or a curated structure
(marcus.core.rgroups); [] for none. Written once with the row (the OCSR result in the worker,
the curation route), so reading a paper costs nothing. NULL: not computed (a curation without
its own structure). The upgrade fills the rows already there with the same function: most rows
pass its string check without RDKit, and data lives at most 30 days, so the table is small.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

BATCH = 500


def _backfill(conn, table: str, key: str, where: str) -> None:
    """Set `rgroups` on the rows of `table` matching `where` (fixed SQL, no user input)."""
    from marcus.core.rgroups import rgroup_labels

    found: list[dict] = []
    select = sa.text(f"SELECT {key} AS id, smiles, molfile FROM {table} WHERE {where}")
    rows = conn.execute(select.execution_options(stream_results=True, yield_per=BATCH))
    for row in rows:
        labels = rgroup_labels(row.smiles, row.molfile)
        if labels:
            found.append({"id": row.id, "labels": labels})
    conn.execute(sa.text(f"UPDATE {table} SET rgroups = '{{}}' WHERE {where}"))
    if found:
        update = sa.text(f"UPDATE {table} SET rgroups = :labels WHERE {key} = :id")
        conn.execute(
            update.bindparams(sa.bindparam("labels", type_=postgresql.ARRAY(sa.Text))), found
        )


def upgrade() -> None:
    op.add_column("predictions", sa.Column("rgroups", postgresql.ARRAY(sa.Text), nullable=True))
    op.add_column("curation", sa.Column("rgroups", postgresql.ARRAY(sa.Text), nullable=True))
    conn = op.get_bind()
    _backfill(conn, "predictions", "id", "TRUE")
    _backfill(conn, "curation", "segment_id", "smiles IS NOT NULL OR molfile IS NOT NULL")


def downgrade() -> None:
    op.drop_column("curation", "rgroups")
    op.drop_column("predictions", "rgroups")
