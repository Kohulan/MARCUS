import os
from pathlib import Path

import pytest

# Always point tests at the test services; never inherit a developer's real URLs.
TEST_DATABASE_URL = os.environ.get(
    "MARCUS_TEST_DATABASE_URL",
    "postgresql+asyncpg://marcus:marcus@127.0.0.1:55432/marcus_test",
)
TEST_REDIS_URL = os.environ.get("MARCUS_TEST_REDIS_URL", "redis://127.0.0.1:56379/0")
os.environ["MARCUS_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["MARCUS_REDIS_URL"] = TEST_REDIS_URL

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _assert_test_database() -> None:
    from sqlalchemy.engine import make_url

    name = make_url(TEST_DATABASE_URL).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run DB tests: database name {name!r} does not end in '_test'"
        )


@pytest.fixture(autouse=True)
def _settings_env(tmp_path, monkeypatch):
    from marcus.core.settings import get_settings

    monkeypatch.setenv("MARCUS_DATA_ROOT", str(tmp_path))
    # Tests that use the segmentation cache set it themselves (all test PDFs share bytes).
    monkeypatch.delenv("MARCUS_SEG_VERSION", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_background_watch(monkeypatch):
    """The dispatcher watchdog's memory of unserved queues is per process: each test starts
    with none."""
    from marcus.dispatcher import pick

    monkeypatch.setattr(pick, "BACKGROUND_WATCH", pick.BackgroundWatch())


@pytest.fixture
def clear_settings_cache():
    from marcus.core.settings import get_settings

    get_settings.cache_clear()
    yield get_settings.cache_clear
    get_settings.cache_clear()


def alembic_config():
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def migrated_db():
    """Run `alembic upgrade head` once on the (guarded) test database."""
    _assert_test_database()
    from alembic import command

    command.upgrade(alembic_config(), "head")
    yield


def _truncate_all(conn) -> None:
    """Empty every table after a test. DELETE (children first), not TRUNCATE: a test leaves a
    handful of rows, and TRUNCATE replaces every table's and index's files (IO per relation,
    ~40 relations), which made teardown the slowest part of most DB tests."""
    from sqlalchemy import text

    from marcus.core.db import Base

    for table in reversed(Base.metadata.sorted_tables):
        conn.execute(text(f'DELETE FROM "{table.name}"'))


@pytest.fixture
def db_session(migrated_db):
    from marcus.core.db import get_sync_sessionmaker

    _assert_test_database()
    with get_sync_sessionmaker()() as session:
        yield session
        session.rollback()
        _truncate_all(session)
        session.commit()


@pytest.fixture
async def async_db_session(migrated_db):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from marcus.core.db import async_db_url
    from marcus.core.settings import get_settings

    _assert_test_database()
    # Own NullPool engine: each test has its own event loop, so pooled connections can't be reused.
    engine = create_async_engine(async_db_url(get_settings().database_url), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
            await session.rollback()
            await session.run_sync(lambda s: _truncate_all(s.connection()))
            await session.commit()
    finally:
        await engine.dispose()
