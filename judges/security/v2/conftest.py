"""Fixtures for the security judge on the v2 API (`/api/v2`).

Run (local fake-engine stack; nginx is the only published port):

    cd /home/kohulan/MARCUS/judges
    MARCUS_BACKEND_URL=http://localhost:18090 MARCUS_FRONTEND_URL=http://localhost:18090 \
        MARCUS_FS_PROBE=docker:marcus-v2-api-1 uv run pytest security/v2 -v

`common/target.py` picks the URL and refuses production hosts, as in v1 (the `backend` fixture
here calls it). The v1 conftest one directory up still loads: its `fs_probe` fixture is reused,
its autouse `ensure_backend_up` is overridden below (v1's `/health` does not exist on v2).

Every test calls its v2 route with a valid request first and asserts a 2xx (`expect_ok`), INSIDE
the test body, so a missing route FAILS the test; it never errors in a fixture and never passes.
The session-wide processed paper is therefore built lazily, by the first test that asks for it.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import pytest

_SECURITY = Path(__file__).resolve().parents[1]
for _p in (str(_SECURITY.parent), str(_SECURITY)):  # judges/ (common), security/ (payloads)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import target  # noqa: E402
from v2.helpers import API, SharedPaper, V2Owner, upload_paper, wait_paper  # noqa: E402

UP_TIMEOUT_S = 300


@pytest.fixture(scope="session")
def backend() -> str:
    return target.backend_url()


@pytest.fixture(scope="session", autouse=True)
def ensure_backend_up(backend):
    """Wait until the edge answers at all. Deliberately not a v2 check: a missing v2 route must
    fail each test's own existence check. Only an nginx upstream error (502/503/504) or a
    refused connection means "not up yet"."""
    deadline = time.monotonic() + UP_TIMEOUT_S
    last = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{backend}{API}/health", timeout=5)
            if r.status_code not in (502, 503, 504):
                return
            last = f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            last = repr(exc)
        time.sleep(2)
    raise RuntimeError(f"{backend} never answered within {UP_TIMEOUT_S}s (last: {last})")


@pytest.fixture
def new_owner(backend):
    """Factory: `new_owner()` -> a fresh caller (V2Owner), closed at teardown."""
    made: list[V2Owner] = []

    def make(**kw) -> V2Owner:
        o = V2Owner(backend, **kw)
        made.append(o)
        return o

    yield make
    for o in made:
        o.close()


@pytest.fixture(scope="session")
def shared_paper(backend):
    """`shared_paper()` -> one paper processed by the fake engines (page images, segments,
    predictions, text), owned by its own owner. Built on the first call, inside a test body.

    Tests only read it as its owner (other tests reuse it); attacks come from other callers.
    """
    owner = V2Owner(backend)
    cache: dict[str, SharedPaper] = {}

    def get() -> SharedPaper:
        if "paper" not in cache:
            pid = upload_paper(owner, filename="judge-shared.pdf")
            detail = wait_paper(owner, pid)
            assert detail["status"] == "done", f"shared paper did not finish: {detail}"
            seg_ids = [s["id"] for s in detail["segments"]]
            assert seg_ids, f"shared paper has no segments (fake engines on?): {detail}"
            cache["paper"] = SharedPaper(owner, pid, detail, seg_ids)
        return cache["paper"]

    yield get
    owner.close()
