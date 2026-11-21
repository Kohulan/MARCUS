"""Offline tests for common/client_v2.py with a fake v2 API (httpx.MockTransport): record mapping, failed
pages, production refusal, polling fallback, unknown engine. No network, no docker."""
import json
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import client_v2  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PID = "11111111-1111-1111-1111-111111111111"
S0, S1, S2 = ("00000000-0000-0000-0000-00000000000%d" % i for i in (0, 1, 2))


def _step(kind, status, page=None, segment_id=None, sid="s"):
    return {"type": "step", "step_id": f"{sid}-{kind}-{page}-{segment_id}", "kind": kind, "status": status,
            "page": page, "segment_id": segment_id}


def _sse(events, end="done", pause=0.01):
    def gen():
        yield b"event: snapshot\ndata: " + json.dumps({"status": "processing", "counts": {}}).encode() + b"\n\n"
        for ev in events:
            time.sleep(pause)
            yield b"data: " + json.dumps(ev).encode() + b"\n\n"
        if end:
            yield b"event: end\ndata: " + json.dumps({"status": end}).encode() + b"\n\n"

    return gen()


def _pred(smiles, ms=40, valid=True, engine="decimer", cached=False):
    return [{"id": "p", "engine": engine, "engine_version": "1", "smiles": smiles, "molfile": None,
             "valid": valid, "ms": ms, "cached": cached, "created_at": "2026-01-01T00:00:00Z"}]


def _seg(sid, page, idx, preds):
    return {"id": sid, "page": page, "idx": idx, "bbox": [0, 0, 1, 1], "curation": None, "predictions": preds}


def _row(kind, page=None, seg=None, t0=0.0, t1=1.0, status="done", error_class=None, created=None, attempts=1):
    """A steps-endpoint row; t0/t1 are seconds after a fixed base."""
    def iso(t):
        return None if t is None else f"2026-01-01T00:00:{t:06.3f}+00:00"
    return {"id": f"{kind}-{page}-{seg}", "kind": kind, "page": page, "segment_id": seg, "status": status,
            "attempts": attempts, "error_class": error_class, "created_at": iso(t0 if created is None else created), "started_at": iso(t0),
            "finished_at": iso(t1)}


def ok_steps():
    return [_row("check_pdf", t0=1, t1=1.5), _row("render_page", 0, t0=2, t1=3, created=1.5),
            _row("segment_page", 0, t0=4, t1=5, created=3), _row("segment_page", 2, t0=5, t1=9.5, created=3),
            _row("ocsr", 0, S0, t0=11, t1=11.25, created=5), _row("ocsr", 2, S1, t0=11.25, t1=11.75, created=9.5)]


class FakeV2:
    def __init__(self, events, segments, status="done", pages=3, sse=True, end="done", poll_statuses=None, steps=None,
                 steps_status=200):
        self.events, self.segments, self.status, self.pages = events, segments, status, pages
        self.steps, self.steps_status = steps or [], steps_status
        self.sse, self.end = sse, end
        self.poll_statuses = list(poll_statuses or [])
        self.calls, self.uploads, self.cookies_seen = [], [], []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.calls.append((req.method, path))
        self.cookies_seen.append(req.headers.get("cookie"))
        if req.method == "POST" and path == "/api/v2/papers":
            body = req.content.decode("latin1")
            self.uploads.append(body)
            return httpx.Response(202, json={"paper_id": PID, "status": "checking"},
                                  headers={"set-cookie": "marcus_owner=tok; Path=/api/v2; HttpOnly; SameSite=strict; Secure"})
        if path == f"/api/v2/papers/{PID}/events":
            if not self.sse:
                return httpx.Response(503)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(self.events, self.end))
        if path == f"/api/v2/papers/{PID}/steps":
            return httpx.Response(self.steps_status, json={"steps": self.steps})
        if path == f"/api/v2/papers/{PID}":
            status = self.poll_statuses.pop(0) if self.poll_statuses else self.status
            return httpx.Response(200, json={"id": PID, "display_name": "x.pdf", "status": status, "pages": self.pages,
                                             "doi": None, "engine": "decimer", "ocsr_mode": "auto",
                                             "created_at": "2026-01-01T00:00:00Z", "expires_at": "2026-02-01T00:00:00Z",
                                             "counts": {"steps_by_status": {}}, "segments": self.segments})
        return httpx.Response(404)


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "PMC1.pdf"
    p.write_bytes(PDF)
    return p


_REAL_CLIENT = httpx.Client


def patch(monkeypatch, fake):
    real = _REAL_CLIENT
    monkeypatch.setattr(client_v2.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
    monkeypatch.setattr(client_v2, "count_pdf_pages", lambda p: 3)
    monkeypatch.setattr(client_v2, "POLL_S", 0.01)
    monkeypatch.setattr(client_v2, "git_short_hash", lambda: "abc1234")


def ok_events():
    return [
        _step("render_page", "running", 0), _step("render_page", "done", 0),
        _step("segment_page", "running", 0), _step("segment_page", "done", 0),
        _step("ocsr", "running", 0, S0), _step("ocsr", "done", 0, S0),
        _step("ocsr", "running", 2, S1), _step("ocsr", "done", 2, S1),
    ]


def test_run_paper_maps_steps_to_paperrun(monkeypatch, pdf):
    fake = FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO", engine="molscribe")),
                                _seg(S1, 2, 1, _pred("CCN", ms=55, engine="molscribe"))], steps=ok_steps())
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "molscribe", base_url="http://x", paper_id="PMC1")
    assert r["build"] == "v2-abc1234" and r["engine"] == "molscribe" and r["paper_id"] == "PMC1"
    assert r["pages_total"] == 3 and r["pages_with_segments"] == 2 and r["page_errors"] == []
    assert [s["segment_id"] for s in r["segments"]] == ["page_0_0", "page_2_1"]
    assert [s["page"] for s in r["segments"]] == [0, 2] and [s["smiles"] for s in r["segments"]] == ["CCO", "CCN"]
    assert all(s["error"] is None for s in r["segments"])
    assert r["fatal_error"] is None and r["timings_ms"]["render_pages"] == 1000.0
    assert r["client"] == "client_v2" and r["http_calls"] == len(fake.calls)
    # the owner cookie issued on the upload is sent on the following calls
    assert fake.cookies_seen[0] is None and all("marcus_owner=tok" in (c or "") for c in fake.cookies_seen[1:])
    assert 'name="engine"' in fake.uploads[0] and "molscribe" in fake.uploads[0]
    json.dumps(r)
    for k in ("paper_id", "pdf_sha256", "engine", "build", "started_at", "wall_ms", "segment_ms", "pages_total",
              "pages_with_segments", "page_errors", "segments", "segments_reported", "segments_listed", "no_segments",
              "aborted", "backend_crash", "rate_limit_events", "tag"):
        assert k in r


def test_failed_page_becomes_page_error(monkeypatch, pdf):
    steps = [_row("render_page", 0, t0=1, t1=2), _row("segment_page", 0, t0=2, t1=3, status="failed", error_class="timeout"),
             _row("render_page", 1, t0=2, t1=3, status="failed", error_class="bad_input"),
             _row("ocsr", 2, S1, t0=4, t1=5, status="failed", error_class="engine_error")]
    seg = [_seg(S1, 2, 0, [])]
    patch(monkeypatch, FakeV2([], seg, status="done", steps=steps))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert [(e["page"], e["kind"], e["error_class"]) for e in r["page_errors"]] == [
        (0, "segment_page", "timeout"), (1, "render_page", "bad_input")]
    assert all(e["error"] for e in r["page_errors"])
    assert r["segments"][0]["error"] == "ocsr step failed (engine_error)" and r["segments"][0]["smiles"] == ""


def test_refuses_production_host(monkeypatch, pdf):
    fake = FakeV2([], [])
    patch(monkeypatch, fake)
    for url in ("https://marcus.decimer.ai", "http://jarvis.ian.uni-jena.de:9000"):
        with pytest.raises(SystemExit):
            client_v2.run_paper(pdf, "decimer", base_url=url)
    assert fake.calls == []


def test_unknown_engine_fails_clearly(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([], []))
    with pytest.raises(ValueError, match="unknown engine"):
        client_v2.run_paper(pdf, "nope", base_url="http://x")


def test_polling_fallback_when_sse_unavailable(monkeypatch, pdf):
    steps = [_row("segment_page", 0, t0=1, t1=3), _row("ocsr", 0, S0, t0=3, t1=3.5)]
    fake = FakeV2([], [_seg(S0, 0, 0, _pred("CCO"))], sse=False, poll_statuses=["processing", "processing"], steps=steps)
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["segments"][0]["smiles"] == "CCO" and r["fatal_error"] is None
    # the steps endpoint covers what the stream cannot: timings are there with no SSE at all
    assert r["segments"][0]["ocsr_ms"] == 500.0 and r["segment_compute_ms"] == 2000.0
    assert sum(1 for m, p in fake.calls if p == f"/api/v2/papers/{PID}") >= 3
    assert r["events_mode"] == "poll"


def test_missing_steps_endpoint_is_recorded_not_fatal(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([], [_seg(S0, 0, 0, _pred("CCO"))], steps_status=404))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["fatal_error"] is None and r["segment_ms"] is None and r["steps_error"].startswith("HTTP 404")
    assert r["segments"][0]["ocsr_ms"] is None and r["segments"][0]["ocsr_compute_ms"] == 40


def test_failed_paper_is_fatal_error(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([], [], status="failed", end="failed"))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["fatal_error"] and "failed" in r["fatal_error"]


def test_no_segments_is_not_fatal(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([_step("segment_page", "done", 0)], [], steps=[_row("segment_page", 0)]))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["no_segments"] is True and r["fatal_error"] is None and r["segments"] == []


def test_abort_event_stops_before_upload(monkeypatch, pdf):
    import threading

    fake = FakeV2(ok_events(), [])
    patch(monkeypatch, fake)
    ev = threading.Event()
    ev.set()
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x", abort=ev)
    assert r["aborted"] is True and fake.calls == []


def test_segment_ms_is_user_wall_time_incl_upload_check_and_queue(monkeypatch, pdf):
    """I1: same quantity as v1 (upload -> all segments ready), not the compute span."""
    fake = FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO")), _seg(S1, 2, 1, _pred("CCN"))], steps=ok_steps())
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    # server clock: first step created at 1.0 s, last segment_page finished at 9.5 s -> 8500 ms, plus the
    # client's upload round trip (a few ms against the mock)
    assert 8500.0 <= r["segment_ms"] < 8700.0
    assert r["segment_compute_ms"] == 5500.0  # first segment_page start (4 s) -> last finish (9.5 s)
    assert r["segment_ms"] > r["segment_compute_ms"]


def test_ocsr_ms_is_created_to_finished_and_compute_is_separate(monkeypatch, pdf):
    """I2: queue wait, retries included; the engine's own ms is its own key; no silent fallback."""
    steps = ok_steps()
    steps[4] = _row("ocsr", 0, S0, t0=11, t1=11.25, created=5, attempts=2)  # waited 6 s, retried
    fake = FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO", ms=40)), _seg(S1, 2, 1, _pred("CCN", ms=55))], steps=steps)
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    a, b = r["segments"]
    assert (a["ocsr_ms"], a["ocsr_compute_ms"], a["ocsr_attempts"]) == (6250.0, 40, 2)
    assert (b["ocsr_ms"], b["ocsr_compute_ms"]) == (2250.0, 55)
    assert a["ocsr_ms_source"] == "step created_at -> finished_at"


def test_ocsr_ms_is_none_without_timing_not_engine_ms(monkeypatch, pdf):
    fake = FakeV2([], [_seg(S0, 0, 0, _pred("CCO", ms=40))], steps=[_row("segment_page", 0, t0=1, t1=2)])
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    s = r["segments"][0]
    assert s["ocsr_ms"] is None and s["ocsr_compute_ms"] == 40 and s["smiles"] == "CCO"


def test_ocsr_cache_hits_are_counted(monkeypatch, pdf):
    segs = [_seg(S0, 0, 0, _pred("CCO", ms=0, cached=True)), _seg(S1, 2, 1, _pred("CCN", ms=55))]
    patch(monkeypatch, FakeV2(ok_events(), segs, steps=ok_steps()))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["ocsr_cache_hits"] == 1 and [s["cached"] for s in r["segments"]] == [True, False]
    patch(monkeypatch, FakeV2([], [], steps=[]))
    assert client_v2.run_paper(pdf, "decimer", base_url="http://x")["ocsr_cache_hits"] == 0


def test_first_segment_start_and_first_smiles_are_upload_relative(monkeypatch, pdf):
    """D3 (spec §3 Fair): when the paper's first segment_page started and its first SMILES arrived, measured like
    segment_ms (client upload round trip + server-clock delta from the paper's first step)."""
    steps = ok_steps()
    steps.append(_row("ocsr", 2, S2, t0=10, t1=10.5, created=9.5, status="failed", error_class="engine_error"))
    fake = FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO")), _seg(S1, 2, 1, _pred("CCN"))], steps=steps)
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    # origin 1.0 s (check_pdf created); first segment_page started 4.0 s -> 3000 ms + upload round trip
    assert 3000.0 <= r["first_segment_start_ms"] < 3200.0
    # first DONE ocsr step finished at 11.25 s (the failed one at 10.5 s is not a SMILES) -> 10250 ms + upload
    assert 10250.0 <= r["first_smiles_ms"] < 10450.0
    assert r["timings_ms"]["upload"] < 200.0


def test_first_times_are_none_without_steps(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([], [_seg(S0, 0, 0, _pred("CCO"))], steps_status=404))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["first_segment_start_ms"] is None and r["first_smiles_ms"] is None


def test_ocsr_done_ms_is_the_v1_comparable_end(monkeypatch, pdf):
    """v1 wall_ms ends at the last OCSR answer; a v2 paper ends after docling/doi too. ocsr_done_ms = upload round
    trip + (last ocsr step finished_at, any final status - first step created_at)."""
    steps = ok_steps() + [_row("docling", t0=1.5, t1=59.0)]
    fake = FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO")), _seg(S1, 2, 1, _pred("CCN"))], steps=steps)
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert 10750.0 <= r["ocsr_done_ms"] < 10950.0  # last ocsr finished 11.75 s, origin 1.0 s


# ------------------------------------------------------------------ D3 fix round 1
def test_failed_non_page_steps_are_recorded(monkeypatch, pdf):
    """I2: a failed or retried docling / doi / check_pdf step must show in the record (kind, error_class, duration)."""
    steps = ok_steps() + [_row("docling", t0=1.5, t1=59.0, status="failed", error_class="bad_input"),
                          _row("doi", t0=1.5, t1=3.5, status="done", error_class="timeout", attempts=2)]
    patch(monkeypatch, FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO"))], steps=steps))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["failed_steps"] == [
        {"kind": "docling", "status": "failed", "error_class": "bad_input", "attempts": 1, "duration_ms": 57500.0},
        {"kind": "doi", "status": "done", "error_class": "timeout", "attempts": 2, "duration_ms": 2000.0}]
    assert r["fatal_error"] is None  # the paper is done; the failure is visible, not fatal


def test_no_failed_steps_is_an_empty_list(monkeypatch, pdf):
    patch(monkeypatch, FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO"))], steps=ok_steps()))
    assert client_v2.run_paper(pdf, "decimer", base_url="http://x")["failed_steps"] == []


class _AbortOnEvents(FakeV2):
    """Sets the caller's abort event when the client opens the event stream (a guard trip mid-paper)."""

    def __init__(self, abort, **kw):
        super().__init__(ok_events(), [], **kw)
        self.abort = abort

    def __call__(self, req):
        if req.url.path.endswith("/events"):
            self.abort.set()
        return super().__call__(req)


def test_abort_after_upload_deletes_the_paper_as_its_owner(monkeypatch, pdf):
    """I1: on v2 the pipeline runs on the server; closing the client is not enough, the paper must be deleted."""
    import threading

    ev = threading.Event()
    fake = _AbortOnEvents(ev)
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x", abort=ev)
    assert r["aborted"] is True
    dels = [i for i, (m, p) in enumerate(fake.calls) if (m, p) == ("DELETE", f"/api/v2/papers/{PID}")]
    assert len(dels) == 1 and fake.cookies_seen[dels[0]] == "marcus_owner=tok"
    assert r["cancelled"] is True
    assert client_v2.live_papers() == {}


def test_cancel_papers_deletes_every_live_paper(monkeypatch):
    fake = FakeV2([], [])
    patch(monkeypatch, fake)
    client_v2._register(PID, "http://x", "tok")
    assert client_v2.live_papers() == {PID: ("http://x", "tok")}
    assert client_v2.cancel_papers() == [PID]
    assert fake.calls == [("DELETE", f"/api/v2/papers/{PID}")] and fake.cookies_seen == ["marcus_owner=tok"]
    assert client_v2.live_papers() == {}


def test_finished_run_leaves_no_live_paper_and_is_listed_as_created(monkeypatch, pdf):
    patch(monkeypatch, FakeV2(ok_events(), [_seg(S0, 0, 0, _pred("CCO"))], steps=ok_steps()))
    client_v2.created_papers(clear=True)
    client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert client_v2.live_papers() == {} and client_v2.created_papers() == [PID]
