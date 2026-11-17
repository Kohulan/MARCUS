"""indexes for the retention purge, foreign-key cascades and per-IP limits

Revision ID: 0003
Revises: 0002

- steps(segment_id), steps(image_job_id), predictions(segment_id), predictions(image_job_id),
  image_jobs(owner_id): the ON DELETE CASCADE of a segment, image job or owner looks up the
  child rows by these columns (a sequential scan per deleted parent row without them).
- papers(expires_at), image_jobs(expires_at), seg_cache(created_at), ocsr_cache(created_at):
  the daily retention purge (marcus.workers.retention).
- owners(created_ip, created_at): the per-IP new-owner limit.
- steps(queue, finished_at): recent finished steps per queue (queue view, metrics).
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_steps_segment_id", "steps", ["segment_id"]),
    ("ix_steps_image_job_id", "steps", ["image_job_id"]),
    ("ix_predictions_segment_id", "predictions", ["segment_id"]),
    ("ix_predictions_image_job_id", "predictions", ["image_job_id"]),
    ("ix_image_jobs_owner_id", "image_jobs", ["owner_id"]),
    ("ix_papers_expires_at", "papers", ["expires_at"]),
    ("ix_image_jobs_expires_at", "image_jobs", ["expires_at"]),
    ("ix_owners_created_ip_created_at", "owners", ["created_ip", "created_at"]),
    ("ix_steps_queue_finished_at", "steps", ["queue", "finished_at"]),
    ("ix_seg_cache_created_at", "seg_cache", ["created_at"]),
    ("ix_ocsr_cache_created_at", "ocsr_cache", ["created_at"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
