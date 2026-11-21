"""Prometheus collector (DB-backed, own internal app) and the public router's 404."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client import CollectorRegistry
from sqlalchemy import text

from marcus.api import metrics as m
from marcus.core.enums import ErrorClass
from marcus.core.models import Prediction, Segment, Step
from marcus.core.queues import SLOTS, TOOLS_QUEUE
from tests.api.conftest import make_client
from tests.factories import make_paper

NOW = datetime.now(UTC)


def value(samples: dict, name: str, **labels) -> float:
    (hit,) = [s for s in samples[name] if all(s.labels.get(k) == v for k, v in labels.items())]
    return hit.value


@pytest.fixture
def collector(migrated_db, tmp_path, monkeypatch):
    c = m.MarcusCollector(cache_s=10.0)
    monkeypatch.setattr(c, "_heartbeat_age", lambda: 7.0)
    return c


def exposition(collector) -> str:
    """The OpenMetrics text (what Prometheus negotiates): gauge histograms keep their type."""
    from prometheus_client.openmetrics.exposition import generate_latest

    reg = CollectorRegistry()
    reg.register(collector)
    return generate_latest(reg).decode()


def scrape(collector) -> dict[str, list]:
    from prometheus_client.openmetrics.parser import text_string_to_metric_families as om

    out: dict[str, list] = {}
    for fam in om(exposition(collector)):
        for s in fam.samples:
            out.setdefault(s.name, []).append(s)
    return out


def bare_paper(db_session):
    """A paper without the planner's own steps, so only the seeded rows are counted."""
    paper = make_paper(db_session)
    db_session.execute(text("DELETE FROM steps WHERE paper_id = :i"), {"i": paper.id})
    return paper


def add_step(db_session, paper, **kw) -> Step:
    defaults = dict(
        paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=100 + kw.pop("n", 0),
        status="done",
    )
    defaults.update(kw)
    step = Step(**defaults)
    db_session.add(step)
    db_session.flush()
    return step


def test_metrics_lists_each_queue(collector):
    samples = scrape(collector)
    queues = {s.labels["queue"] for s in samples["marcus_queue_pending"]}
    assert queues == {*SLOTS, TOOLS_QUEUE}
    assert {s.labels["queue"] for s in samples["marcus_queue_running"]} == queues
    assert value(samples, "marcus_queue_pending", queue="q.cpu") == 0


def test_queue_counts_from_rows(collector, db_session):
    owner_paper = bare_paper(db_session)
    add_step(db_session, owner_paper, status="pending", n=1)
    add_step(db_session, owner_paper, status="queued", n=2)
    add_step(db_session, owner_paper, status="running", n=3, started_at=NOW)
    add_step(db_session, owner_paper, status="done", n=4)
    add_step(db_session, owner_paper, status="running", n=5, queue="q.segment",
             kind="segment_page", started_at=NOW)  # fmt: skip
    db_session.commit()
    samples = scrape(collector)
    assert value(samples, "marcus_queue_pending", queue="q.cpu") == 2
    assert value(samples, "marcus_queue_running", queue="q.cpu") == 1
    assert value(samples, "marcus_queue_running", queue="q.segment") == 1
    assert value(samples, "marcus_queue_pending", queue="q.segment") == 0


def test_step_seconds_histogram_per_kind_and_engine(collector, db_session):
    paper = bare_paper(db_session)
    recent = NOW - timedelta(minutes=5)
    for i, secs in enumerate([1.5, 4.0]):
        add_step(db_session, paper, kind="ocsr", engine="decimer", queue="q.decimer", n=i,
                 started_at=recent, finished_at=recent + timedelta(seconds=secs))  # fmt: skip
    add_step(db_session, paper, kind="ocsr", engine="molscribe", queue="q.molscribe", n=9,
             started_at=recent, finished_at=recent + timedelta(seconds=20))  # fmt: skip
    old = NOW - timedelta(hours=3)  # outside the last hour: not counted
    add_step(db_session, paper, kind="ocsr", engine="decimer", queue="q.decimer", n=10,
             started_at=old, finished_at=old + timedelta(seconds=100))  # fmt: skip
    db_session.commit()
    samples = scrape(collector)
    lab = dict(kind="ocsr", engine="decimer")
    assert value(samples, "marcus_step_seconds_gcount", **lab) == 2
    assert value(samples, "marcus_step_seconds_gsum", **lab) == pytest.approx(5.5, abs=0.01)
    assert value(samples, "marcus_step_seconds_bucket", le="2.0", **lab) == 1
    assert value(samples, "marcus_step_seconds_bucket", le="5.0", **lab) == 2
    assert value(samples, "marcus_step_seconds_bucket", le="+Inf", **lab) == 2
    assert value(samples, "marcus_step_seconds_gcount", kind="ocsr", engine="molscribe") == 1


def test_wait_seconds_histogram_per_queue(collector, db_session):
    paper = bare_paper(db_session)
    created = NOW - timedelta(minutes=10)
    add_step(db_session, paper, n=1, created_at=created, queued_at=created + timedelta(seconds=3),
             started_at=NOW, finished_at=NOW)  # fmt: skip
    add_step(db_session, paper, n=2, status="pending", created_at=created)  # never queued: skip
    db_session.commit()
    samples = scrape(collector)
    assert value(samples, "marcus_wait_seconds_gcount", queue="q.cpu") == 1
    assert value(samples, "marcus_wait_seconds_gsum", queue="q.cpu") == pytest.approx(3.0, abs=0.01)


def test_first_smiles_seconds_per_paper(collector, db_session):
    paper = bare_paper(db_session)
    db_session.execute(
        text("UPDATE papers SET created_at = :t WHERE id = :i"),
        {"t": NOW - timedelta(minutes=2), "i": paper.id},
    )
    seg = Segment(paper_id=paper.id, page=0, idx=0, bbox=[0, 0, 1, 1], image_sha256="0" * 64)
    db_session.add(seg)
    db_session.flush()
    for delay in (30, 60):  # the FIRST prediction counts
        db_session.add(Prediction(
            segment_id=seg.id, engine="decimer", engine_version="t", smiles="C", valid=True,
            ms=1, created_at=NOW - timedelta(minutes=2) + timedelta(seconds=delay),
        ))  # fmt: skip
    bare_paper(db_session)  # a paper without predictions: not counted
    db_session.commit()
    samples = scrape(collector)
    assert samples["marcus_first_smiles_seconds_gcount"][0].value == 1
    assert samples["marcus_first_smiles_seconds_gsum"][0].value == pytest.approx(30.0, abs=0.5)


def test_failures_gauge_counts_only_the_last_hour(collector, db_session):
    paper = bare_paper(db_session)
    recent, old = NOW - timedelta(minutes=5), NOW - timedelta(hours=2)
    add_step(db_session, paper, status="failed", error_class="timeout", n=1, finished_at=recent)
    add_step(db_session, paper, status="failed", error_class="timeout", n=2, finished_at=recent)
    add_step(db_session, paper, status="failed", error_class="bad_input", n=3, finished_at=recent)
    add_step(db_session, paper, status="failed", error_class="timeout", n=4, finished_at=old)
    db_session.commit()
    samples = scrape(collector)
    assert value(samples, "marcus_steps_failed", error_class="timeout") == 2
    assert value(samples, "marcus_steps_failed", error_class="bad_input") == 1
    classes = {s.labels["error_class"] for s in samples["marcus_steps_failed"]}
    assert classes == {e.value for e in ErrorClass}  # zero series exist for the others


def test_windowed_values_are_gauges_never_counters_or_histograms(collector):
    text_ = exposition(collector)
    types = dict(
        line.split()[2:4] for line in text_.splitlines() if line.startswith("# TYPE ")
    )
    for name in ("marcus_step_seconds", "marcus_wait_seconds", "marcus_first_smiles_seconds"):
        assert types[name] == "gaugehistogram", name
    assert types["marcus_steps_failed"] == "gauge"
    assert "counter" not in types.values() and "histogram" not in types.values()
    assert "last-hour window; do not rate()" in text_
    assert "failed steps finished in the last hour" in text_.lower()


def test_heartbeat_age_is_fresh_on_a_cached_scrape(collector, monkeypatch):
    ages = iter([1.0, 2.0])
    monkeypatch.setattr(collector, "_heartbeat_age", lambda: next(ages))
    first = scrape(collector)
    second = scrape(collector)  # DB part cached, heartbeat read again
    assert first["marcus_dispatcher_heartbeat_age_seconds"][0].value == 1.0
    assert second["marcus_dispatcher_heartbeat_age_seconds"][0].value == 2.0


def test_total_deadline_stops_the_read(collector, monkeypatch):
    monkeypatch.setattr(m, "TOTAL_DEADLINE_S", -1.0)
    samples = scrape(collector)
    assert samples["marcus_scrape_db_ok"][0].value == 0


def test_disk_and_heartbeat_gauges(collector):
    samples = scrape(collector)
    (disk,) = samples["marcus_disk_free_bytes"]
    assert disk.labels == {"path": "/data"} and disk.value > 0
    assert samples["marcus_dispatcher_heartbeat_age_seconds"][0].value == 7.0
    assert samples["marcus_scrape_db_ok"][0].value == 1


def test_deadline_constant_is_under_8_seconds():
    assert 0 < m.TOTAL_DEADLINE_S < 8


def test_cache_holds_for_10_seconds(collector, db_session, monkeypatch):
    calls = {"n": 0}
    real = collector._snapshot

    def counting(conn):
        calls["n"] += 1
        return real(conn)

    monkeypatch.setattr(collector, "_snapshot", counting)
    scrape(collector)
    scrape(collector)
    assert calls["n"] == 1
    clock = {"t": time.monotonic() + 11}
    monkeypatch.setattr(m, "_monotonic", lambda: clock["t"])
    scrape(collector)
    assert calls["n"] == 2


def test_one_read_only_transaction_with_2s_statement_timeout(collector, monkeypatch):
    seen = {}
    real = collector._snapshot

    def spy(conn):
        seen["ro"] = conn.execute(text("SHOW transaction_read_only")).scalar()
        seen["timeout"] = conn.execute(text("SHOW statement_timeout")).scalar()
        seen["xid"] = conn.execute(text("SELECT txid_current_if_assigned()")).scalar()
        return real(conn)

    monkeypatch.setattr(collector, "_snapshot", spy)
    scrape(collector)
    assert seen == {"ro": "on", "timeout": "2s", "xid": None}
    assert m.STATEMENT_TIMEOUT_MS == 2000


def test_slow_query_times_out_and_scrape_still_answers(collector, monkeypatch):
    monkeypatch.setattr(m, "STATEMENT_TIMEOUT_MS", 100)

    def slow(conn):
        conn.execute(text("SELECT pg_sleep(3)"))

    monkeypatch.setattr(collector, "_snapshot", slow)
    started = time.monotonic()
    samples = scrape(collector)
    assert time.monotonic() - started < 2.5
    assert samples["marcus_scrape_db_ok"][0].value == 0
    assert "marcus_queue_pending" not in samples  # no stale or invented DB numbers
    assert samples["marcus_disk_free_bytes"][0].value > 0


# --- the HTTP side ---------------------------------------------------------------------------


async def test_metrics_not_on_public_router(app):
    async with make_client(app) as c:
        for path in ("/api/v2/metrics", "/metrics"):
            assert (await c.get(path)).status_code == 404


async def test_internal_app_serves_metrics_and_nothing_else(collector):
    import httpx

    app = m.build_app(collector)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://metrics"
    ) as c:
        r = await c.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "marcus_queue_pending" in r.text
        om = await c.get("/metrics", headers={"Accept": "application/openmetrics-text"})
        assert om.headers["content-type"].startswith("application/openmetrics-text")
        assert "gaugehistogram" in om.text
        assert (await c.get("/health")).status_code == 200
        assert (await c.get("/api/v2/papers")).status_code == 404
        assert (await c.post("/metrics")).status_code == 405
