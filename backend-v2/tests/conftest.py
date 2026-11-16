import os

import pytest

os.environ.setdefault(
    "MARCUS_DATABASE_URL", "postgresql+asyncpg://marcus:marcus@127.0.0.1:55432/marcus_test"
)
os.environ.setdefault("MARCUS_REDIS_URL", "redis://127.0.0.1:56379/0")


@pytest.fixture(autouse=True)
def _settings_env(tmp_path, monkeypatch):
    from marcus.core.settings import get_settings

    monkeypatch.setenv("MARCUS_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def clear_settings_cache():
    from marcus.core.settings import get_settings

    get_settings.cache_clear()
    yield get_settings.cache_clear
    get_settings.cache_clear()
