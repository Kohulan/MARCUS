"""rgroups steps move from q.llm to their own queue q.rgroup

Revision ID: 0013
Revises: 0012

The R-group model runs on its own llama-server, so its steps get their own queue (and worker):
an annotation run no longer holds back an R-group reading, nor the other way round. Data only:
every rgroups step's `queue` changes. A step already sent or started (`queued`, `running`) goes
back to `pending` with one more attempt, so the dispatcher sends it again on the new queue with
a new attempt token; the old q.llm message carries the old token and is dropped as stale
(marcus.workers.runtime.claim). Annotate steps stay on q.llm. The downgrade moves them back the
same way.
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
               attempts = CASE WHEN status IN ('queued', 'running') THEN attempts + 1
                               ELSE attempts END,
               queued_at = CASE WHEN status IN ('queued', 'running') THEN NULL
                                ELSE queued_at END,
               started_at = CASE WHEN status IN ('queued', 'running') THEN NULL
                                 ELSE started_at END,
               status = CASE WHEN status IN ('queued', 'running') THEN 'pending' ELSE status END
         WHERE kind = 'rgroups' AND queue = '{old}'
        """
    )


def upgrade() -> None:
    _move("q.llm", "q.rgroup")


def downgrade() -> None:
    _move("q.rgroup", "q.llm")
