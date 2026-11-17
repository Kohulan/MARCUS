from sqlalchemy import inspect

from alembic import command
from tests.conftest import _assert_test_database, alembic_config

EXPECTED = {
    "owners", "papers", "steps", "segments", "predictions", "curation",
    "image_jobs", "seg_cache", "ocsr_cache",
}  # fmt: skip

# 0002: column + index
INDEXES_0002 = {("segments", "ix_segments_image_sha256")}
# 0003: purge and foreign-key indexes, (table, name) -> columns
INDEXES_0003 = {
    ("steps", "ix_steps_segment_id"): ["segment_id"],
    ("steps", "ix_steps_image_job_id"): ["image_job_id"],
    ("predictions", "ix_predictions_segment_id"): ["segment_id"],
    ("predictions", "ix_predictions_image_job_id"): ["image_job_id"],
    ("image_jobs", "ix_image_jobs_owner_id"): ["owner_id"],
    ("papers", "ix_papers_expires_at"): ["expires_at"],
    ("image_jobs", "ix_image_jobs_expires_at"): ["expires_at"],
    ("owners", "ix_owners_created_ip_created_at"): ["created_ip", "created_at"],
    ("steps", "ix_steps_queue_finished_at"): ["queue", "finished_at"],
    ("seg_cache", "ix_seg_cache_created_at"): ["created_at"],
    ("ocsr_cache", "ix_ocsr_cache_created_at"): ["created_at"],
}


def _indexes(engine) -> dict[tuple[str, str], list[str]]:
    insp = inspect(engine)
    return {
        (table, ix["name"]): ix["column_names"]
        for table in insp.get_table_names()
        for ix in insp.get_indexes(table)
    }


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_upgrade_then_downgrade_clean(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert EXPECTED <= set(inspect(engine).get_table_names())
        command.downgrade(cfg, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        command.upgrade(cfg, "head")


def test_0002_and_0003_objects_up_and_down(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        indexes = _indexes(engine)
        assert "model_version" in _columns(engine, "steps")
        assert INDEXES_0002 <= set(indexes)
        for key, columns in INDEXES_0003.items():
            assert indexes.get(key) == columns, key

        command.downgrade(cfg, "0002")
        indexes = _indexes(engine)
        assert not set(INDEXES_0003) & set(indexes)
        assert INDEXES_0002 <= set(indexes)
        assert "model_version" in _columns(engine, "steps")

        command.downgrade(cfg, "0001")
        assert not INDEXES_0002 & set(_indexes(engine))
        assert "model_version" not in _columns(engine, "steps")
    finally:
        command.upgrade(cfg, "head")


def test_models_declare_the_0003_indexes():
    """The ORM metadata matches the migrations (the model is what readers look at)."""
    from marcus.core.db import Base

    declared = {
        (table.name, ix.name): [c.name for c in ix.columns]
        for table in Base.metadata.sorted_tables
        for ix in table.indexes
    }
    for key, columns in INDEXES_0003.items():
        assert declared.get(key) == columns, key


def test_0004_adds_predictions_cached(migrated_db):
    from marcus.core.db import get_sync_engine

    _assert_test_database()
    cfg = alembic_config()
    engine = get_sync_engine()
    try:
        command.upgrade(cfg, "head")
        assert "cached" in _columns(engine, "predictions")
        command.downgrade(cfg, "0003")
        assert "cached" not in _columns(engine, "predictions")
    finally:
        command.upgrade(cfg, "head")
