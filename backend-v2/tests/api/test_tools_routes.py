import time

import pytest

from marcus.api.routes import tools as tools_route
from tests.api.conftest import make_client

BASE = "/api/v2/tools"


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(name, kwargs, timeout):
        seen.append((name, kwargs, timeout))
        return {"ok": name}

    monkeypatch.setattr(tools_route, "run_tool", fake)
    return seen


async def test_depict_dispatches_to_task(app, calls):
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/depict", json={"smiles": "c1ccccc1"})
    assert r.status_code == 200
    name, kwargs, timeout = calls[0]
    assert name == "marcus.tools.depict"
    assert kwargs["fmt"] == "svg" and kwargs["width"] == 512 and kwargs["height"] == 512
    assert timeout == 10


async def test_long_smiles_422(app, calls):
    async with make_client(app) as c:
        for path, body in [
            ("depict", {"smiles": "C" * 2001}),
            ("smiles-to-molfile", {"smiles": "C" * 2001}),
            ("compare", {"smiles_a": "C" * 2001, "smiles_b": "C"}),
        ]:
            r = await c.post(f"{BASE}/{path}", json=body)
            assert r.status_code == 422, path
    assert calls == []


@pytest.mark.parametrize("size", [49, 2001])
async def test_size_clamp_422(app, calls, size):
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/depict", json={"smiles": "C", "width": size})
    assert r.status_code == 422


async def test_mcs_caps(app, calls):
    async with make_client(app) as c:
        too_many = await c.post(f"{BASE}/mcs", json={"molfiles": ["x"] * 21})
        too_big = await c.post(f"{BASE}/mcs", json={"molfiles": ["x" * 200_001, "y"]})
        one = await c.post(f"{BASE}/mcs", json={"molfiles": ["x"]})
        ok = await c.post(f"{BASE}/mcs", json={"molfiles": ["x", "y"]})
    assert too_many.status_code == too_big.status_code == one.status_code == 422
    assert ok.status_code == 200


async def test_tool_timeout_is_504(app, monkeypatch):
    from celery.exceptions import TimeoutError as CeleryTimeout

    def slow(*a, **k):
        raise CeleryTimeout()

    monkeypatch.setattr(tools_route, "_send_and_wait", slow)
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/compare", json={"smiles_a": "C", "smiles_b": "CC"})
    assert r.status_code == 504 and r.json() == {"detail": "tool timed out"}


async def test_task_input_error_is_422_other_is_500(app, monkeypatch):
    def bad(*a, **k):
        return {"ok": False, "error": "cannot parse SMILES"}

    def boom(*a, **k):
        raise RuntimeError("jvm exploded: secret")

    async with make_client(app) as c:
        monkeypatch.setattr(tools_route, "_send_and_wait", bad)
        r = await c.post(f"{BASE}/compare", json={"smiles_a": "C", "smiles_b": "CC"})
        assert r.status_code == 422 and "cannot parse" in r.json()["detail"]
        monkeypatch.setattr(tools_route, "_send_and_wait", boom)
        r = await c.post(f"{BASE}/compare", json={"smiles_a": "C", "smiles_b": "CC"})
        assert r.status_code == 500 and "secret" not in r.text


async def test_envelope_ok_result_is_unwrapped(app, monkeypatch):
    monkeypatch.setattr(
        tools_route, "_send_and_wait", lambda *a, **k: {"ok": True, "result": "<svg/>"}
    )
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/depict", json={"smiles": "C"})
    assert r.status_code == 200 and r.json() == {"format": "svg", "data": "<svg/>"}


def test_run_tool_times_out_with_stub_task(monkeypatch):
    """A task that sleeps 20 s must not hold the request past the wait timeout."""
    from celery.exceptions import TimeoutError as CeleryTimeout

    class Slow:
        def get(self, timeout=None, **kw):
            time.sleep(timeout)
            raise CeleryTimeout()

    monkeypatch.setattr(tools_route.celery_app, "send_task", lambda *a, **k: Slow())
    start = time.monotonic()
    with pytest.raises(CeleryTimeout):
        tools_route._send_and_wait("marcus.tools.compare", {}, 0.2)
    assert time.monotonic() - start < 2
