from sqlalchemy import inspect

from alembic import command
from tests.conftest import _assert_test_database, alembic_config

EXPECTED = {
    "owners", "papers", "steps", "segments", "predictions", "curation",
    "image_jobs", "seg_cache", "ocsr_cache",
}  # fmt: skip


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
