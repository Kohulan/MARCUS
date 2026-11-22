"""rgroups steps move from q.llm to their own queue q.rgroup

Revision ID: 0013
Revises: 0012

The R-group model runs on its own llama-server, so its steps get their own queue (and worker):
an annotation run no longer holds back an R-group reading, nor the other way round. Data only:
every rgroups step's `queue` changes. A step already sent (`queued`) goes back to `pending`, so
the dispatcher sends it again on the new queue; the old q.llm message is dropped as stale, as it
comes from another queue than the step's (marcus.workers.runtime.claim), even after the step is
queued again with the same attempt token. Annotate steps stay on q.llm. The downgrade
moves them back the same way.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _move(old: str, new: str) -> None:
    op.execute(
        f"""
        UPDATE steps
           SET queue = '{new}',
               status = CASE WHEN status = 'queued' THEN 'pending' ELSE status END,
               queued_at = CASE WHEN status = 'queued' THEN NULL ELSE queued_at END
         WHERE kind = 'rgroups' AND queue = '{old}'
        """
    )


def upgrade() -> None:
    _move("q.llm", "q.rgroup")


def downgrade() -> None:
    _move("q.rgroup", "q.llm")
