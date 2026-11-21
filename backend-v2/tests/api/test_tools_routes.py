import time

import pytest

from marcus.api import tooling as tools_route  # the tool-call code the routes use
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


async def test_mcs_total_size_cap(app, calls):
    mf = ["x" * 200_000] * 6  # each within the per-file cap, 1.2 MB together
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/mcs", json={"molfiles": mf})
    assert r.status_code == 422 and calls == []


def test_result_is_released_even_on_timeout(monkeypatch):
    from celery.exceptions import TimeoutError as CeleryTimeout

    events = []

    class Res:
        id = "abc"

        def get(self, timeout=None, **kw):
            raise CeleryTimeout()

        def forget(self):
            events.append("forget")

    class Consumer:
        def cancel_for(self, task_id):
            events.append(("cancel", task_id))

    monkeypatch.setattr(tools_route.celery_app, "send_task", lambda *a, **k: Res())
    monkeypatch.setattr(
        tools_route.celery_app.backend, "result_consumer", Consumer(), raising=False
    )
    with pytest.raises(CeleryTimeout):
        tools_route._send_and_wait("marcus.tools.compare", {}, 0.1)
    assert events == ["forget", ("cancel", "abc")]


def test_tool_task_expires_with_the_wait(monkeypatch):
    """Review I5: a call the API gave up on must not still run later in q.tools."""
    seen = {}

    class Done:
        id = "x"

        def get(self, timeout=None, **kw):
            return {"ok": True, "result": 1}

        def forget(self):
            pass

    def send_task(name, **kw):
        seen.update(kw)
        return Done()

    monkeypatch.setattr(tools_route.celery_app, "send_task", send_task)
    tools_route._send_and_wait("marcus.tools.compare", {}, 7)
    assert seen["expires"] == 7 and seen["queue"] == tools_route.TOOLS_QUEUE


async def test_tool_waits_have_their_own_bounded_thread_budget(monkeypatch):
    """Review I5: waiting tool calls hold at most MAX_TOOL_WAITS threads of their own; above
    that the call gets 503 at once, and file responses keep the default thread pool."""
    import asyncio
    import threading

    import anyio
    from fastapi import HTTPException

    monkeypatch.setattr(tools_route, "MAX_TOOL_WAITS", 2)
    monkeypatch.setattr(tools_route, "_tool_waits", None)
    release = threading.Event()
    started = []

    def blocking(name, kwargs, timeout):
        started.append(name)
        release.wait(5)
        return "<svg/>"

    monkeypatch.setattr(tools_route, "run_tool", blocking)
    default = anyio.to_thread.current_default_thread_limiter()
    held = [
        asyncio.ensure_future(tools_route.call_tool("marcus.tools.depict", {})) for _ in range(2)
    ]
    for _ in range(100):
        if len(started) == 2:
            break
        await asyncio.sleep(0.02)
    assert len(started) == 2
    assert default.borrowed_tokens == 0  # the default pool is untouched
    with pytest.raises(HTTPException) as info:
        await tools_route.call_tool("marcus.tools.depict", {})
    assert info.value.status_code == 503 and info.value.detail == "tools busy, try again"
    release.set()
    assert await asyncio.gather(*held) == ["<svg/>", "<svg/>"]
    assert await tools_route.call_tool("marcus.tools.depict", {}) == "<svg/>"


@pytest.mark.parametrize(
    "highlight",
    ["~".join(["*"] * 129), "~".join(["[#6]"] * 129), "[$(*~*)]", "C[$(CO)]"],
    ids=["any-atoms", "bracket-atoms", "recursive", "recursive-mixed"],
)
async def test_depict_highlight_over_cap_422(app, calls, highlight):
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/depict", json={"smiles": "C", "highlight": highlight})
    assert r.status_code == 422
    assert calls == []


# --- signed highlight (F5): /tools/depict never searches with a pattern the server did not make


def molfile(smiles: str) -> str:
    from rdkit import Chem

    return Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))


MCS_SMARTS = "[#6]-[#6]"


@pytest.fixture
def tools(monkeypatch):
    """Fake tools worker: an MCS reply with MCS_SMARTS, an SVG for a depiction."""
    seen = []

    def fake(name, kwargs, timeout):
        seen.append((name, kwargs))
        if name == "marcus.tools.mcs":
            n = len(kwargs["molfiles"])
            return {
                "mcs_smarts": MCS_SMARTS,
                "atom_count": 2,
                "bond_count": 1,
                "original_molecules": [{"atom_count": 3, "bond_count": 2}] * n,
            }
        return "<svg/>"

    monkeypatch.setattr(tools_route, "run_tool", fake)
    return seen


async def _token(c, smiles=("CCO", "CCN")) -> str:
    r = await c.post(f"{BASE}/mcs", json={"molfiles": [molfile(s) for s in smiles]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mcs_smarts"] == MCS_SMARTS and body["atom_count"] == 2
    assert set(body) == {
        "mcs_smarts", "atom_count", "bond_count", "original_molecules", "highlight_token",
    }  # fmt: skip
    return body["highlight_token"]


def _depicts(seen):
    return [k for name, k in seen if name == "marcus.tools.depict"]


async def test_mcs_reply_carries_a_highlight_token_and_it_draws_a_bound_molecule(app, tools):
    async with make_client(app) as c:
        token = await _token(c)
        for smiles in ("CCO", "OCC", "NCC"):  # any spelling of a bound molecule
            r = await c.post(
                f"{BASE}/depict",
                json={"smiles": smiles, "highlight": MCS_SMARTS, "highlight_token": token},
            )
            assert r.status_code == 200, r.text
    assert [k["highlight"] for k in _depicts(tools)] == [MCS_SMARTS] * 3


async def test_mcs_without_a_common_part_has_no_token(app, monkeypatch):
    def fake(name, kwargs, timeout):
        return {"mcs_smarts": "", "atom_count": 0, "bond_count": 0, "original_molecules": []}

    monkeypatch.setattr(tools_route, "run_tool", fake)
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/mcs", json={"molfiles": [molfile("C"), molfile("O")]})
    assert r.status_code == 200 and r.json()["highlight_token"] is None


NEVER_MATCHES = "~".join(["*"] * 19) + "~[#7]"  # 52 s of VF2 on C60 before this fix


@pytest.mark.parametrize("token", [None, "", "x", "e30.AAAA", "a" * 100, "a.é", "é.a", "e30.ÿÿ"])
async def test_highlight_without_a_valid_token_is_refused_before_any_search(app, tools, token):
    body = {"smiles": "C1=CC=CC=C1", "highlight": NEVER_MATCHES}
    if token is not None:
        body["highlight_token"] = token
    async with make_client(app) as c:
        r = await c.post(f"{BASE}/depict", json=body)
    assert r.status_code == 422
    assert r.json() == {"detail": "highlight not valid for this structure"}
    assert tools == []  # no tool call: no CDK search ran


async def test_token_for_another_pattern_is_refused(app, tools):
    async with make_client(app) as c:
        token = await _token(c)
        r = await c.post(
            f"{BASE}/depict",
            json={"smiles": "CCO", "highlight": NEVER_MATCHES, "highlight_token": token},
        )
    assert r.status_code == 422 and _depicts(tools) == []


async def test_token_for_other_molecules_is_refused(app, tools):
    """Rebound: a valid token for CCO and CCN does not license drawing benzene with it."""
    async with make_client(app) as c:
        token = await _token(c)
        r = await c.post(
            f"{BASE}/depict",
            json={"smiles": "c1ccccc1", "highlight": MCS_SMARTS, "highlight_token": token},
        )
    assert r.status_code == 422 and _depicts(tools) == []


async def test_forged_and_tampered_tokens_are_refused(app, tools):
    import base64
    import json

    from marcus.api import highlight

    async with make_client(app) as c:
        token = await _token(c)
        payload, sig = token.split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        claims["m"].append(highlight.digest(highlight.binding_key_of_smiles("c1ccccc1")))
        forged_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        other_key = highlight.sign(b"k" * 32, MCS_SMARTS, ["c1ccccc1"], now=0)
        for bad in (
            f"{forged_payload}.{sig}",  # claims changed, old signature
            f"{payload}.{sig[:-2]}AA",  # signature changed
            other_key,  # signed with another key
        ):
            r = await c.post(
                f"{BASE}/depict",
                json={"smiles": "c1ccccc1", "highlight": MCS_SMARTS, "highlight_token": bad},
            )
            assert r.status_code == 422, bad
    assert _depicts(tools) == []


async def test_expired_token_is_refused(app, tools, monkeypatch):
    from marcus.api import highlight

    async with make_client(app) as c:
        token = await _token(c)
        real = highlight._now()
        monkeypatch.setattr(highlight, "_now", lambda: real + highlight.TOKEN_TTL_S + 1)
        r = await c.post(
            f"{BASE}/depict",
            json={"smiles": "CCO", "highlight": MCS_SMARTS, "highlight_token": token},
        )
    assert r.status_code == 422 and _depicts(tools) == []
    assert highlight.TOKEN_TTL_S == 30 * 60


async def test_highlight_key_is_shared_through_redis_and_a_setting_wins(app, monkeypatch):
    from marcus.api import highlight
    from marcus.core.settings import get_settings

    redis = app.state.rate_limiter.redis
    await redis.delete(highlight.REDIS_KEY)
    first = await highlight.signing_key(redis)
    assert len(first) >= 32 and await highlight.signing_key(redis) == first  # every process
    assert await redis.get(highlight.REDIS_KEY) == first
    monkeypatch.setenv("MARCUS_HIGHLIGHT_KEY", "s" * 40)
    get_settings.cache_clear()
    assert await highlight.signing_key(redis) == b"s" * 40
    assert "s" * 40 not in repr(get_settings())


def test_highlight_atom_cap_matches_the_worker():
    from marcus.api.routes import tools as route
    from marcus.workers import tools as worker

    assert route.MAX_HIGHLIGHT_ATOMS == worker.MAX_HIGHLIGHT_ATOMS
