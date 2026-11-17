"""Offline tests for the guard, the ssh whitelist and the backend-log parser (no network, no ssh)."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import guard_jarvis as gj  # noqa: E402
from common import remote  # noqa: E402

OK = {"prod_health": "healthy", "gpu_free_mib": 5000, "gpu_used_mib": 27000, "gpu_total_mib": 32768}


@pytest.fixture(autouse=True)
def _tmp_results(tmp_path, monkeypatch):
    monkeypatch.setattr(gj, "RESULTS", tmp_path)
    monkeypatch.setattr(gj, "_LEDGER", tmp_path / "ledger.json")


@pytest.mark.parametrize("cmd", [
    "nvidia-smi --query-gpu=memory.free,memory.used,memory.total --format=csv,noheader,nounits",
    "docker inspect -f '{{.State.Health.Status}}' marcus-backend",
    "docker inspect -f '{{.State.Health.Status}}' marcus-judge-backend",
    "docker logs --since 2026-11-16T10:00:00.123456789Z -t marcus-judge-backend",
    "docker logs -t --tail 1 marcus-judge-backend",
])
def test_whitelist_allows(cmd):
    assert remote.is_allowed(cmd)


@pytest.mark.parametrize("cmd", [
    "docker restart marcus-backend", "docker stop marcus-judge-backend", "docker rm -f marcus-judge-backend",
    "docker logs marcus-backend; rm -rf /", "docker exec marcus-backend ls", "docker logs stitch-backend",
    "docker inspect -f '{{.State.Health.Status}}' stitch-backend", "nvidia-smi -pm 1", "nvidia-smi --gpu-reset",
    "docker compose -p marcus-judge down", "cat /etc/passwd", "docker logs marcus-backend | grep x",
])
def test_whitelist_refuses(cmd):
    assert not remote.is_allowed(cmd)
    with pytest.raises(ValueError):
        remote.ssh_ro(cmd)


def test_evaluate():
    assert gj.evaluate(OK) is None
    assert "health" in gj.evaluate({**OK, "prod_health": "unhealthy"})
    assert "free GPU" in gj.evaluate({**OK, "gpu_free_mib": 3071})
    assert gj.evaluate({**OK, "gpu_free_mib": 3072}) is None


def test_noop_guard_for_local():
    with gj.Guard("http://localhost:19100", "t") as g:
        assert not g.enabled and not g.tripped
    assert g.summary()["checks"] == 0


def test_guard_trips_before():
    g = gj.Guard("http://localhost:29000", "t", checker=lambda: {**OK, "prod_health": "unhealthy"}, use_ledger=False)
    with pytest.raises(gj.GuardTripped):
        g.__enter__()
    assert g.abort.is_set() and "unhealthy" in g.tripped_reason
    assert (gj.RESULTS / "guard_events.jsonl").exists()


def test_guard_trips_during_and_sets_abort():
    seq = iter([OK, OK, {**OK, "gpu_free_mib": 1000}] + [OK] * 20)
    g = gj.Guard("http://localhost:29000", "t", interval_s=0.05, checker=lambda: next(seq), use_ledger=False)
    with g:
        for _ in range(100):
            if g.abort.is_set():
                break
            time.sleep(0.05)
        assert g.abort.is_set()
    assert g.tripped and "free GPU" in g.tripped_reason
    assert [e["when"] for e in g.events][:2] == ["before", "during"]


def test_guard_fails_closed_when_check_errors(monkeypatch):
    monkeypatch.setattr(gj.time, "sleep", lambda s: None)

    def boom():
        raise RuntimeError("ssh down")

    g = gj.Guard("http://localhost:29000", "t", checker=boom, use_ledger=False)
    with pytest.raises(gj.GuardTripped):
        g.__enter__()
    assert "could not run" in g.tripped_reason


def test_ledger_budget(monkeypatch):
    monkeypatch.setattr(gj, "BUDGET_S", 10.0)
    gj.ledger_add("x", 11.0)
    g = gj.Guard("http://localhost:29000", "t", checker=lambda: OK)
    with pytest.raises(gj.GuardTripped, match="budget"):
        g.__enter__()


def test_parse_server_log():
    lines = [
        "Error processing page 2: Exception encountered when calling layer 'roi_align_classifier' (type PyramidROIAlign).",
        "", "{{function_node}} Expected begin, end, and strides", "Call arguments received by layer 'roi_align_classifier' (type PyramidROIAlign):",
        "Error processing page 2: Exception encountered when calling layer 'roi_align_classifier' (type PyramidROIAlign).",
        "Error processing page 5: ",
        "get_segments_with_bbox took 24.50 seconds",
    ]
    p = remote.parse_server_log(lines)
    assert [(e["page"], e["layer_type"]) for e in p["page_errors"]] == [(2, "PyramidROIAlign"), (5, None)]
    assert p["page_errors"][1]["error"].startswith("(empty message")
    assert p["server_segment_s"] == [24.5]
    assert p["keyword_counts"]["PyramidROIAlign"] >= 2


# ---------------------------------------------------------------- owner's GPU window: production stopped on purpose (D4)
def test_evaluate_prod_stopped_mode():
    """With production stopped for a GPU test window, a RUNNING production is the violation (it would share the GPU)."""
    stopped = {"prod_status": "exited", "gpu_free_mib": 20000}
    assert gj.evaluate(stopped, prod_expected="stopped") is None
    assert gj.evaluate({"prod_status": "created", "gpu_free_mib": 20000}, prod_expected="stopped") is None
    assert "running" in gj.evaluate({"prod_status": "running", "gpu_free_mib": 20000}, prod_expected="stopped")
    assert gj.evaluate({"prod_status": "exited", "gpu_free_mib": 100}, prod_expected="stopped")  # GPU rule still holds
    # the default mode is unchanged: a stopped production fails it
    assert gj.evaluate({"prod_health": "unhealthy", "gpu_free_mib": 20000}) is not None


def test_prod_stopped_check_uses_the_whitelisted_status_command(monkeypatch):
    sent = []
    monkeypatch.setattr(gj.remote, "ssh_ro", lambda cmd: sent.append(cmd) or "exited\n")
    monkeypatch.setattr(gj.remote, "gpu_stats", lambda remote: {"gpu_free_mib": 20000})
    s = gj.real_check(prod_expected="stopped")
    assert s["prod_status"] == "exited" and sent == ["docker inspect -f '{{.State.Status}}' marcus-backend"]
    assert all(gj.remote.is_allowed(c) for c in sent)


def test_guard_in_prod_stopped_mode(monkeypatch):
    g = gj.Guard("http://localhost:29090", "S1", enabled=True, use_ledger=False, prod_expected="stopped",
                 checker=lambda: {"prod_status": "exited", "gpu_free_mib": 20000})
    with g:
        pass
    assert not g.tripped and g.summary()["prod_expected"] == "stopped"
    with pytest.raises(ValueError):
        gj.Guard("http://x", "S1", prod_expected="maybe")
