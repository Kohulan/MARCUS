"""R-group labels again, with only the labels that have the form of one

Revision ID: 0014
Revises: 0013

marcus.core.rgroups now counts a dummy atom's alias as a label only when it looks like one (R,
R1, R′, Ra, X, Y, Z, Ar, n...; marcus.core.rgroup_labels): MolScribe's unexpanded groups (OAc,
MeO, CO2H...) and misread numbers stop being labels, and R2O / OR3 count as R2 / R3. The upgrade
computes the labels of every row that has some again with the same function (a structure that
had labels before is the only one whose labels can change). The downgrade keeps them: the older
code reads them unchanged.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

BATCH = 500


def _recompute(conn, table: str, key: str) -> None:
    """Labels of the rows of `table` that have some, computed again (fixed SQL, no user input)."""
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    from marcus.core.rgroups import rgroup_labels

    changed: list[dict] = []
    select = sa.text(
        f"SELECT {key} AS id, smiles, molfile, rgroups FROM {table} "
        "WHERE rgroups IS NOT NULL AND cardinality(rgroups) > 0"
    )
    for row in conn.execute(select.execution_options(stream_results=True, yield_per=BATCH)):
        labels = rgroup_labels(row.smiles, row.molfile)
        if labels != list(row.rgroups):
            changed.append({"id": row.id, "labels": labels})
    if changed:
        update = sa.text(f"UPDATE {table} SET rgroups = :labels WHERE {key} = :id")
        conn.execute(
            update.bindparams(sa.bindparam("labels", type_=postgresql.ARRAY(sa.Text))), changed
        )


def upgrade() -> None:
    conn = op.get_bind()
    _recompute(conn, "predictions", "id")
    _recompute(conn, "curation", "segment_id")


def downgrade() -> None:
    pass
