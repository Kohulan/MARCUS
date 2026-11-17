"""Offline tests for load/v2_adapter.py (the v1 -> v2 call mapping of the load scenarios) and the --client switch
of load/scenarios.py. Fake v2 API through httpx.MockTransport; no network, no docker."""
import re
import sys
import threading
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import guard_jarvis  # noqa: E402
import scenarios  # noqa: E402
import v2_adapter  # noqa: E402
from common import client_v2  # noqa: E402

JOB = "22222222-2222-2222-2222-222222222222"
_REAL_CLIENT = httpx.Client


def v1_calls_in_scenarios() -> set[str]:
    """Every v1 HTTP path and client function that scenarios.py uses (grep of its source)."""
    src = (HERE / "scenarios.py").read_text()
    paths = set()
    for m in re.finditer(r"""["'](?:\{base_url\})?(/(?:health|session|latest|v1)[^"'{]*)""", src):
        paths.add(m.group(1).rstrip("/"))
    funcs = set(re.findall(r"\b(run_paper|parse_server_log)\(", src))
    return paths | funcs


class FakeApi:
    """A tiny v2: owner cookie on the first call without one, image jobs that finish after `polls` GETs."""

    def __init__(self, polls=2, upload_status=202, job_end="done", tokens=None):
        self.polls, self.upload_status, self.job_end = polls, upload_status, job_end
        self.calls: list[tuple[str, str, str | None]] = []
        self.bodies: list[str] = []
        self._tokens = iter(tokens or (f"tok{i}" for i in range(1000)))
        self._left = {}

    def _cookie(self, req):
        if req.headers.get("cookie"):
            return {}
        return {"set-cookie": f"marcus_owner={next(self._tokens)}; Path=/api/v2; HttpOnly; SameSite=strict; Secure"}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, cookie = req.url.path, req.headers.get("cookie")
        self.calls.append((req.method, path, cookie))
        if path == "/api/v2/health":
            return httpx.Response(200, json={"status": "ok"})
        if req.method == "GET" and path == "/api/v2/papers":
            return httpx.Response(200, json={"papers": []}, headers=self._cookie(req))
        if req.method == "POST" and path == "/api/v2/images":
            self.bodies.append(req.content.decode("latin1"))
            if self.upload_status != 202:
                return httpx.Response(self.upload_status, json={"detail": "service unavailable"}, headers=self._cookie(req))
            self._left[JOB] = self.polls
            return httpx.Response(202, json={"image_job_id": JOB, "status": "queued"}, headers=self._cookie(req))
        if req.method == "GET" and path == f"/api/v2/images/{JOB}":
            self._left[JOB] -= 1
            st = "queued" if self._left[JOB] > 0 else self.job_end
            return httpx.Response(200, json={"id": JOB, "status": st, "prediction": None, "error": None})
        if req.method == "POST" and path == "/api/v2/tools/depict":
            self.bodies.append(req.content.decode())
            return httpx.Response(200, json={"format": "svg", "data": "<svg/>"}, headers=self._cookie(req))
        return httpx.Response(404, json={"detail": "Not found"})


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    patch(monkeypatch, fake)
    return fake


def patch(monkeypatch, fake):
    monkeypatch.setattr(v2_adapter.httpx, "Client", lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(fake), **kw))
    monkeypatch.setattr(v2_adapter, "POLL_S", 0.001)
    v2_adapter.http_events(clear=True)


# ------------------------------------------------------------------ the mapping
def test_adapter_maps_every_v1_call_used_by_scenarios():
    calls = v1_calls_in_scenarios()
    # the grep must see the calls we know about, or this test would pass on an empty list
    assert {"/health", "/session/create", "/session/remove", "/session/heartbeat", "/latest/ocsr/generate_smiles",
            "run_paper", "parse_server_log"} <= calls
    missing = calls - set(v2_adapter.V1_TO_V2)
    assert not missing, f"v1 calls in scenarios.py without a v2 mapping: {sorted(missing)}"
    for v1_call, m in v2_adapter.V1_TO_V2.items():
        assert m["v2"] and m["v1"], v1_call
        fn = getattr(v2_adapter, m["adapter"])
        assert callable(fn), v1_call
        # the v1 side offers the same name, so scenario code is the same for both clients
        assert callable(getattr(scenarios.V1Api, m["adapter"])), m["adapter"]


def test_run_paper_is_client_v2():
    assert v2_adapter.run_paper is client_v2.run_paper


def test_health_and_server_ok_use_api_v2_health(api):
    assert v2_adapter.health_call("http://x")(5) == 200
    assert v2_adapter.server_ok("http://x") is True
    assert [p for _, p, _ in api.calls] == ["/api/v2/health", "/api/v2/health"]


def test_session_is_a_cookie_owner_and_heartbeat_sends_it(api):
    owner = v2_adapter.create_session("http://x")
    assert owner and owner.cookie == "tok0"
    assert v2_adapter.heartbeat_call("http://x", owner)(5) == 200
    assert api.calls[-1] == ("GET", "/api/v2/papers", "marcus_owner=tok0")
    v2_adapter.remove_session("http://x", owner)  # v2 has no sessions: no HTTP call
    assert len(api.calls) == 2


def test_script_call_posts_image_and_polls_until_done(api):
    owner = v2_adapter.create_session("http://x")
    call = v2_adapter.script_call("http://x", owner, b"\x89PNG fake", "fake")
    assert call(5) == 200
    posts = [c for c in api.calls if c[:2] == ("POST", "/api/v2/images")]
    polls = [c for c in api.calls if c[:2] == ("GET", f"/api/v2/images/{JOB}")]
    assert len(posts) == 1 and len(polls) == 2
    assert all(c[2] == "marcus_owner=tok0" for c in posts + polls)
    assert 'name="engine"' in api.bodies[0] and "fake" in api.bodies[0] and 'name="file"' in api.bodies[0]


def test_script_call_failed_job_is_not_ok(monkeypatch):
    fake = FakeApi(job_end="failed")
    patch(monkeypatch, fake)
    owner = v2_adapter.create_session("http://x")
    assert v2_adapter.script_call("http://x", owner, b"png", "fake")(5) == "job_failed"


def test_script_user_gets_a_new_owner_before_the_upload_limit(api):
    """10 uploads per owner per minute in v2; the v1 script user had its own bucket, so v2 rotates owners."""
    owner = v2_adapter.create_session("http://x", uploads_per_owner=2)
    call = v2_adapter.script_call("http://x", owner, b"png", "fake")
    for _ in range(5):
        assert call(5) == 200
    cookies = [c for m, p, c in api.calls if (m, p) == ("POST", "/api/v2/images")]
    # tok0 from create_session: 2 uploads; then a request without cookie -> new owner tok1 (2 uploads), tok2 ...
    assert cookies == ["marcus_owner=tok0", "marcus_owner=tok0", None, "marcus_owner=tok1", None]
    assert owner.owners_used == 3


def test_breaker_503_is_recorded(monkeypatch):
    fake = FakeApi(upload_status=503)
    patch(monkeypatch, fake)
    owner = v2_adapter.create_session("http://x")
    assert v2_adapter.script_call("http://x", owner, b"png", "fake")(5) == 503
    ev = v2_adapter.http_events()
    assert [(e["status"], e["detail"], e["path"]) for e in ev] == [(503, "service unavailable", "/api/v2/images")]
    assert v2_adapter.breaker_503_count(ev) == 1


def test_depict_call(api):
    owner = v2_adapter.create_session("http://x")
    assert v2_adapter.depict_call("http://x", owner)(5) == 200
    assert api.calls[-1] == ("POST", "/api/v2/tools/depict", "marcus_owner=tok0")
    assert '"smiles"' in api.bodies[-1]


def test_warmup_is_one_image_job(api):
    w = v2_adapter.warmup("http://x", None, b"png", "fake", timeout=5)
    assert w["status"] == 200 and w["ms"] >= 0
    assert ("POST", "/api/v2/images", None) in api.calls


def test_page_errors_come_from_records_not_docker_logs():
    recs = [{"page_errors": [{"page": 3, "kind": "segment_page", "error_class": "timeout", "error": "x"}]},
            {"page_errors": []}, None]
    pe = v2_adapter.page_errors_of(recs)
    assert pe == [{"page": 3, "kind": "segment_page", "error_class": "timeout", "error": "x", "paper": 0}]


def test_adapter_refuses_production(api):
    for url in ("https://marcus.decimer.ai", "http://jarvis.ian.uni-jena.de:9000"):
        with pytest.raises(SystemExit):
            v2_adapter.health_call(url)
        with pytest.raises(SystemExit):
            v2_adapter.create_session(url)
    assert api.calls == []


# ------------------------------------------------------------------ scenarios.py --client
def test_select_client():
    assert scenarios.select_client("v2") is v2_adapter
    assert scenarios.select_client("v1") is scenarios.V1Api


def test_big_cap_ignored_for_v2_with_a_log_line(capsys):
    assert scenarios.big_cap_for("v2", 80) is None
    assert "--big-cap" in capsys.readouterr().out
    assert scenarios.big_cap_for("v1", 80) == 80


def test_s4_and_s3_ocsr_depth_per_client():
    assert scenarios.s4_max_segments("v1") == 0  # v1: segmentation only (lost pages)
    assert scenarios.s4_max_segments("v2") is None  # v2: full pipeline (spec §3 throughput)


def test_result_names_keep_v1_and_v2_apart(tmp_path):
    p1 = scenarios.result_path(tmp_path, "local", "v1", "S1", "")
    p2 = scenarios.result_path(tmp_path, "jarvis", "v2", "S2", "x")
    assert p1.name.startswith("local_S1_") and p2.name.startswith("jarvis_v2_S2_") and p2.name.endswith("_x.json")


def test_s1_reference_is_per_client(tmp_path):
    import json

    def write(name, eng, wall):
        (tmp_path / name).write_text(json.dumps({"config": {}, "results": {"engines": {eng: {"runs": [
            {"wall_ms": wall, "fatal_error": None}]}}}}))
    write("local_S1_20260101T000000.json", "decimer", 200000)
    write("local_v2_S1_20260101T000000.json", "fake", 30000)
    assert scenarios.load_s1_reference("local", tmp_path, "v1") == {"decimer": {"wall_ms": 200000, "from": "local_S1_20260101T000000.json"}}
    assert scenarios.load_s1_reference("local", tmp_path, "v2") == {"fake": {"wall_ms": 30000, "from": "local_v2_S1_20260101T000000.json"}}


def test_guard_runs_for_jarvis_target_even_with_a_base_url_override():
    assert scenarios.guard_enabled("jarvis", "http://localhost:29090") is True
    assert scenarios.guard_enabled("local", "http://localhost:29000") is True  # the v1 jarvis tunnel port
    assert scenarios.guard_enabled("local", "http://localhost:18090") is False


def test_guard_trip_closes_v2_clients(monkeypatch, tmp_path):
    closed = []
    monkeypatch.setattr(guard_jarvis, "RESULTS", tmp_path)
    monkeypatch.setattr(guard_jarvis.client_v1, "abort_all", lambda: closed.append("v1") or 1)
    monkeypatch.setattr(guard_jarvis.client_v2, "abort_all", lambda: closed.append("v2") or 2)
    g = guard_jarvis.Guard("http://localhost:29090", "S2", enabled=True, checker=lambda: {"prod_health": "unhealthy"},
                           use_ledger=False)
    assert g.check("before") is False
    assert g.abort.is_set() and closed == ["v1", "v2"]


def test_fairness_fields_v1_and_v2():
    v2 = {"first_segment_start_ms": 4200.0, "first_smiles_ms": 15000.0, "segments": []}
    v2["ocsr_done_ms"] = 30000.0
    assert scenarios.fairness_fields(v2) == {"first_segment_start_s": 4.2, "first_smiles_s": 15.0, "ocsr_done_s": 30.0}
    v1 = {"segments": [{"t_start_ms": 9000.0, "ocsr_ms": 2000.0, "error": None},
                       {"t_start_ms": 8000.0, "ocsr_ms": 5000.0, "error": None},
                       {"t_start_ms": 7000.0, "ocsr_ms": 100.0, "error": "boom"}]}
    v1["wall_ms"] = 20000.0
    assert scenarios.fairness_fields(v1) == {"first_segment_start_s": None, "first_smiles_s": 11.0, "ocsr_done_s": 20.0}


def test_lat_stats_counts_503():
    s = scenarios.lat_stats([{"ms": 5, "status": 200, "error": None}, {"ms": 3, "status": 503, "error": None},
                             {"ms": 9, "status": "job_failed", "error": None}])
    assert s["n_ok"] == 1 and s["n_503"] == 1 and s["n_429"] == 0


def test_probe_threads_share_one_owner_safely(api):
    owner = v2_adapter.create_session("http://x")
    call = v2_adapter.heartbeat_call("http://x", owner)
    ths = [threading.Thread(target=call, args=(5,)) for _ in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert all(c == "marcus_owner=tok0" for m, p, c in api.calls[1:])


def test_jarvis_v2_through_a_tunnel_reaches_the_guard_in_prod_stopped_mode(monkeypatch, tmp_path):
    """D4: --target jarvis --client v2 --base-url <tunnel> --prod-stopped -> guard enabled, production must be
    stopped, result file jarvis_v2_*."""
    seen = {}

    class FakeGuard:
        def __init__(self, base_url, name, enabled=None, prod_expected="running", **kw):
            seen.update(base_url=base_url, enabled=enabled, prod_expected=prod_expected)
            self.abort, self.tripped = threading.Event(), False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def summary(self):
            return {}

    monkeypatch.setattr(scenarios, "Guard", FakeGuard)
    monkeypatch.setattr(scenarios, "RESULTS", tmp_path)
    monkeypatch.setattr(scenarios.make_fixtures, "ensure", lambda n: None)
    monkeypatch.setattr(v2_adapter, "server_ok", lambda base_url, timeout=30: True)
    monkeypatch.setitem(scenarios.SCENARIOS, "S3", lambda b, g, a, r: r.update(summary={"ok": True}))
    rc = scenarios.main(["--target", "jarvis", "--client", "v2", "--base-url", "http://localhost:29111",
                         "--prod-stopped", "--scenarios", "S3"])
    assert rc == 0
    assert seen == {"base_url": "http://localhost:29111", "enabled": True, "prod_expected": "stopped"}
    files = list(tmp_path.glob("jarvis_v2_S3_*.json"))
    assert len(files) == 1


def test_jarvis_v2_refuses_a_production_base_url():
    with pytest.raises(SystemExit):
        scenarios.main(["--target", "jarvis", "--client", "v2", "--base-url", "https://marcus.decimer.ai", "--scenarios", "S3"])
