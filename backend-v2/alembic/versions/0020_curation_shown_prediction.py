"""curation.shown_prediction_id: the structure a decision was made on

Revision ID: 0020
Revises: 0019

A status decision (accepted, rejected) without a structure of its own keeps the prediction the
card showed at that moment (marcus.api.decisions). Card, depiction, exports, COCONUT and the
main-figure links show it afterwards, whatever other engines read later
(marcus.core.agreement.pick_prediction). NULL: no decision on a prediction (unchecked, a
curated structure, or a decision from before this revision: the shown structure follows the
default pick, as before). Deleting the prediction clears it.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curation",
        sa.Column(
            "shown_prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("curation", "shown_prediction_id")
