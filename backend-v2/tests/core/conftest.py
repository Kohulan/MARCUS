"""Fixtures shared by the core tests."""

import pytest

from marcus.core.settings import get_settings


@pytest.fixture
def seg_version(monkeypatch):
    """The segmenter version of the cache tests (test_caches.SEG_V), for a module that drives
    papers with them: `pytestmark = pytest.mark.usefixtures("seg_version")`."""
    from tests.core.test_caches import SEG_V

    monkeypatch.setenv("MARCUS_SEG_VERSION", SEG_V)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
