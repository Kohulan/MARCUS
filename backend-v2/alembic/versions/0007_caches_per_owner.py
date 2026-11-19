"""seg_cache and ocsr_cache per owner (security F3/F6)

Revision ID: 0007
Revises: 0006

Both caches gain `owner_id` (first primary-key column, ON DELETE CASCADE): a row one owner's
work made is never another owner's hit. seg_cache also records the paper whose segmentation it
holds (`paper_id`, ON DELETE CASCADE; deleting the paper drops the row). The tables are only
caches and the deploy starts from empty volumes, so both are dropped and created again (rows
cannot be given an owner); the downgrade does the same with the 0001/0003 shape.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TZ = sa.TIMESTAMP(timezone=True)
NOW = sa.text("now()")


def _fk(name: str, target: str) -> sa.Column:
    return sa.Column(
        name, pg.UUID(as_uuid=True), sa.ForeignKey(target, ondelete="CASCADE"), nullable=False
    )


def _drop() -> None:
    for table in ("seg_cache", "ocsr_cache"):
        op.drop_index(f"ix_{table}_created_at", table_name=table)
    op.drop_table("seg_cache")
    op.drop_table("ocsr_cache")


def upgrade() -> None:
    _drop()
    op.create_table(
        "seg_cache",
        sa.Column(
            "owner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pdf_sha256", pg.CHAR(64), primary_key=True),
        sa.Column("seg_version", sa.Text, primary_key=True),
        _fk("paper_id", "papers.id"),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_index("ix_seg_cache_created_at", "seg_cache", ["created_at"])
    op.create_index("ix_seg_cache_paper_id", "seg_cache", ["paper_id"])
    op.create_table(
        "ocsr_cache",
        sa.Column(
            "owner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("image_sha256", pg.CHAR(64), primary_key=True),
        sa.Column("engine", sa.Text, primary_key=True),
        sa.Column("engine_version", sa.Text, primary_key=True),
        sa.Column("smiles", sa.Text, nullable=False),
        sa.Column("molfile", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_index("ix_ocsr_cache_created_at", "ocsr_cache", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_seg_cache_paper_id", table_name="seg_cache")
    _drop()
    op.create_table(
        "seg_cache",
        sa.Column("pdf_sha256", pg.CHAR(64), primary_key=True),
        sa.Column("seg_version", sa.Text, primary_key=True),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_index("ix_seg_cache_created_at", "seg_cache", ["created_at"])
    op.create_table(
        "ocsr_cache",
        sa.Column("image_sha256", pg.CHAR(64), primary_key=True),
        sa.Column("engine", sa.Text, primary_key=True),
        sa.Column("engine_version", sa.Text, primary_key=True),
        sa.Column("smiles", sa.Text, nullable=False),
        sa.Column("molfile", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_index("ix_ocsr_cache_created_at", "ocsr_cache", ["created_at"])
