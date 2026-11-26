"""paper layout: predictions.layout and ocsr_cache.layout

Revision ID: 0024
Revises: 0023

Owner decision 2026-11-26 ("Layout + overlay"): MolScribe's atom positions, read off the image
and fitted to its ink, are kept as a molfile beside the prediction (marcus.core.paper_layout), so
every engine's answer can be drawn in the paper's layout and over the paper, also when
MolScribe's own answer is invalid.

predictions.layout: NULL without one (every other engine, rows from before: no backfill).
ocsr_cache.layout: NULL = never tried (a MolScribe row from before is read once more),
'' = tried, none.
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

TABLES = ("predictions", "ocsr_cache")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("layout", sa.Text, nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "layout")
