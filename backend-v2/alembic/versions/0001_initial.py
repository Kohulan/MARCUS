"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.TIMESTAMP(timezone=True)
NOW = sa.text("now()")
ENGINES = ("decimer", "decimer-hand", "molnextr", "molscribe", "fake")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _pk() -> sa.Column:
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _fk(name: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, pg.UUID(as_uuid=True), sa.ForeignKey(target, ondelete="CASCADE"), nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "owners",
        _pk(),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("priority_class", sa.Integer, nullable=False),
        sa.Column("created_ip", pg.INET),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", TZ, nullable=False, server_default=NOW),
        sa.Column("revoked_at", TZ),
        sa.Column("daily_page_quota", sa.Integer),
        sa.Column("label", sa.Text),
        sa.CheckConstraint(_in("kind", ("browser", "api_key")), name="ck_owners_kind"),
    )
    op.create_table(
        "papers",
        _pk(),
        _fk("owner_id", "owners.id"),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("pdf_sha256", pg.CHAR(64), nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("pages", sa.Integer),
        sa.Column("doi", sa.Text),
        sa.Column("engine", sa.Text, nullable=False),
        sa.Column("ocsr_mode", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("expires_at", TZ, nullable=False),
        sa.CheckConstraint("ocsr_mode IN ('auto', 'off')", name="ck_papers_ocsr_mode"),
        sa.CheckConstraint(
            _in("status", ("checking", "processing", "done", "failed", "deleted")),
            name="ck_papers_status",
        ),
        sa.CheckConstraint(_in("engine", ENGINES), name="ck_papers_engine"),
    )
    op.create_index("ix_papers_owner_id_status", "papers", ["owner_id", "status"])
    op.create_table(
        "image_jobs",
        _pk(),
        _fk("owner_id", "owners.id"),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("image_sha256", pg.CHAR(64), nullable=False),
        sa.Column("engine", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("expires_at", TZ, nullable=False),
        sa.CheckConstraint(
            _in("status", ("queued", "processing", "done", "failed", "deleted")),
            name="ck_image_jobs_status",
        ),
        sa.CheckConstraint(_in("engine", ENGINES), name="ck_image_jobs_engine"),
    )
    op.create_table(
        "segments",
        _pk(),
        _fk("paper_id", "papers.id"),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("bbox", pg.ARRAY(sa.Integer), nullable=False),
        sa.Column("image_sha256", pg.CHAR(64), nullable=False),
        sa.UniqueConstraint("paper_id", "page", "idx", name="uq_segments_paper_page_idx"),
        sa.CheckConstraint("cardinality(bbox) = 4", name="ck_segments_bbox_len"),
    )
    op.create_table(
        "steps",
        _pk(),
        _fk("paper_id", "papers.id", nullable=True),
        _fk("image_job_id", "image_jobs.id", nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("queue", sa.Text, nullable=False),
        sa.Column("engine", sa.Text),
        sa.Column("page", sa.Integer),
        _fk("segment_id", "segments.id", nullable=True),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error_class", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("queued_at", TZ),
        sa.Column("started_at", TZ),
        sa.Column("finished_at", TZ),
        sa.Column("worker_name", sa.Text),
        sa.CheckConstraint(
            "(paper_id IS NOT NULL)::int + (image_job_id IS NOT NULL)::int = 1",
            name="ck_steps_one_parent",
        ),
        sa.CheckConstraint(
            _in(
                "kind",
                ("check_pdf", "render_page", "segment_page", "ocsr", "docling", "doi", "annotate"),
            ),
            name="ck_steps_kind",
        ),
        sa.CheckConstraint(
            _in("status", ("pending", "queued", "running", "done", "failed", "cancelled")),
            name="ck_steps_status",
        ),
        sa.CheckConstraint("engine IS NULL OR " + _in("engine", ENGINES), name="ck_steps_engine"),
        sa.CheckConstraint(
            "error_class IS NULL OR "
            + _in("error_class", ("timeout", "worker_lost", "bad_input", "engine_error")),
            name="ck_steps_error_class",
        ),
    )
    op.create_index("ix_steps_queue_status", "steps", ["queue", "status"])
    op.create_index("ix_steps_paper_id_status", "steps", ["paper_id", "status"])
    op.create_table(
        "predictions",
        _pk(),
        _fk("segment_id", "segments.id", nullable=True),
        _fk("image_job_id", "image_jobs.id", nullable=True),
        sa.Column("engine", sa.Text, nullable=False),
        sa.Column("engine_version", sa.Text, nullable=False),
        sa.Column("smiles", sa.Text, nullable=False),
        sa.Column("molfile", sa.Text),
        sa.Column("valid", sa.Boolean, nullable=False),
        sa.Column("ms", sa.Integer, nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.CheckConstraint(_in("engine", ENGINES), name="ck_predictions_engine"),
    )
    op.create_table(
        "curation",
        sa.Column(
            "segment_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("segments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("smiles", sa.Text),
        sa.Column("molfile", sa.Text),
        sa.Column("note", sa.Text),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('unchecked', 'accepted', 'rejected')", name="ck_curation_status"
        ),
    )
    op.create_table(
        "seg_cache",
        sa.Column("pdf_sha256", pg.CHAR(64), primary_key=True),
        sa.Column("seg_version", sa.Text, primary_key=True),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_table(
        "ocsr_cache",
        sa.Column("image_sha256", pg.CHAR(64), primary_key=True),
        sa.Column("engine", sa.Text, primary_key=True),
        sa.Column("engine_version", sa.Text, primary_key=True),
        sa.Column("smiles", sa.Text, nullable=False),
        sa.Column("molfile", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.execute(
        """
        CREATE FUNCTION marcus_notify_step() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('marcus_steps', NEW.queue);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER steps_notify_insert AFTER INSERT ON steps "
        "FOR EACH ROW EXECUTE FUNCTION marcus_notify_step()"
    )
    op.execute(
        "CREATE TRIGGER steps_notify_status AFTER UPDATE OF status ON steps "
        "FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status) "
        "EXECUTE FUNCTION marcus_notify_step()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS steps_notify_status ON steps")
    op.execute("DROP TRIGGER IF EXISTS steps_notify_insert ON steps")
    op.execute("DROP FUNCTION IF EXISTS marcus_notify_step()")
    for table in (
        "ocsr_cache", "seg_cache", "curation", "predictions", "steps",
        "segments", "image_jobs", "papers", "owners",
    ):  # fmt: skip
        op.drop_table(table)
