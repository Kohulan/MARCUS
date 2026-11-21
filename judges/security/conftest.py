"""Shared fixtures for the MARCUS security judge.

Run with:

    cd /home/kohulan/MARCUS/judges
    MARCUS_FS_PROBE=docker:marcus-judge-backend uv run pytest security -v

`common/target.py` picks the backend/frontend URLs and refuses production
hosts; nothing here overrides that. The filesystem probe (`fs_probe.py`) is
the only other thing a rebuild needs to re-point (via MARCUS_FS_PROBE) to
run this same suite against v2.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # judges/ root
sys.path.insert(0, str(Path(__file__).resolve().parent))  # security/ itself
from common import target  # noqa: E402
from fs_probe import ProbeError, get_probe  # noqa: E402

# The local CPU copy loads several large CPU-bound ML models on first use
# (docling layout parsing, DECIMER/MolNeXtR/MolScribe, PDF->image
# rendering) and the container has been observed to restart during that
# warm-up. Tests give it generous timeouts rather than assume a GPU-speed
# production box.
BACKEND_HEALTH_TIMEOUT_S = 600
HTTP_TIMEOUT_S = 300


@pytest.fixture(scope="session")
def backend() -> str:
    return target.backend_url()


@pytest.fixture(scope="session")
def frontend() -> str:
    return target.frontend_url()


@pytest.fixture(scope="session", autouse=True)
def ensure_backend_up(backend):
    """Block until /health is reachable, so a mid-warm-up/restarting
    container doesn't masquerade as a fixed, safe build.

    This does not skip on failure: if the backend never comes up the whole
    session errors, which is correct -- a judge that silently passes
    because the target was down proves nothing.
    """
    deadline = time.monotonic() + BACKEND_HEALTH_TIMEOUT_S
    last_error = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{backend}/health", timeout=5)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(
        f"Backend at {backend} never became healthy within "
        f"{BACKEND_HEALTH_TIMEOUT_S}s (last error: {last_error})"
    )


@pytest.fixture
def client(backend):
    with httpx.Client(base_url=backend, timeout=HTTP_TIMEOUT_S) as c:
        yield c


@pytest.fixture
def fs_probe():
    """The pluggable filesystem probe. Errors (does not skip) if unset or
    unreachable -- see fs_probe.get_probe."""
    try:
        probe = get_probe()
    except ProbeError as exc:
        pytest.fail(str(exc), pytrace=False)
    return probe
