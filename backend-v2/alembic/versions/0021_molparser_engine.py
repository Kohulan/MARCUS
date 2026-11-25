"""engine molparser: MolParser replaces MolNexTR

Revision ID: 0021
Revises: 0020

Owner decision 2026-11-25: the OCSR engine `molparser` (MolParser-Mobile-V2, queue q.molparser)
replaces `molnextr`, which is no longer run (no worker, no queue). The four engine CHECK
constraints (papers, image_jobs, steps, predictions) accept `molparser`; `molnextr` stays allowed
for the old rows (predictions, papers whose engine it was), kept until retention removes them.

Data: an ocsr step of `molnextr` that has not finished (pending, queued, running) would wait for
a worker that no longer exists. It moves to `molparser` on q.molparser; one already sent or
started goes back to `pending` with one more attempt, so the dispatcher sends it again with a new
attempt token and the old q.molnextr message is dropped as stale (as 0013). Finished steps keep
their engine.

Downgrade: only while no row names `molparser` (the old constraints cannot hold one); the moved
steps stay with MolParser.
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

OLD = ("decimer", "decimer-hand", "molnextr", "molscribe", "fake")
NEW = ("decimer", "decimer-hand", "molnextr", "molparser", "molscribe", "fake")
# (table, constraint, NULL allowed)
CHECKS = (
    ("papers", "ck_papers_engine", False),
    ("image_jobs", "ck_image_jobs_engine", False),
    ("steps", "ck_steps_engine", True),
    ("predictions", "ck_predictions_engine", False),
)


def _in(values) -> str:
    return "engine IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _checks(values) -> None:
    for table, name, nullable in CHECKS:
        op.drop_constraint(name, table, type_="check")
        cond = ("engine IS NULL OR " if nullable else "") + _in(values)
        op.create_check_constraint(name, table, cond)


def upgrade() -> None:
    _checks(NEW)
    op.execute(
        """
        UPDATE steps
           SET engine = 'molparser',
               queue = 'q.molparser',
               attempts = CASE WHEN status IN ('queued', 'running') THEN attempts + 1
                               ELSE attempts END,
               queued_at = CASE WHEN status IN ('queued', 'running') THEN NULL
                                ELSE queued_at END,
               started_at = CASE WHEN status IN ('queued', 'running') THEN NULL
                                 ELSE started_at END,
               status = CASE WHEN status IN ('queued', 'running') THEN 'pending' ELSE status END
         WHERE kind = 'ocsr' AND engine = 'molnextr'
           AND status IN ('pending', 'queued', 'running')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM papers WHERE engine = 'molparser')
               OR EXISTS (SELECT 1 FROM image_jobs WHERE engine = 'molparser')
               OR EXISTS (SELECT 1 FROM steps WHERE engine = 'molparser')
               OR EXISTS (SELECT 1 FROM predictions WHERE engine = 'molparser') THEN
                RAISE EXCEPTION 'rows with engine molparser exist: restore the database dump';
            END IF;
        END
        $$
        """
    )
    _checks(OLD)
