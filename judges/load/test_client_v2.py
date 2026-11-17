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


def _pred(smiles, ms=40, valid=True, engine="decimer"):
    return [{"id": "p", "engine": engine, "engine_version": "1", "smiles": smiles, "molfile": None,
             "valid": valid, "ms": ms, "created_at": "2026-01-01T00:00:00Z"}]


def _seg(sid, page, idx, preds):
    return {"id": sid, "page": page, "idx": idx, "bbox": [0, 0, 1, 1], "curation": None, "predictions": preds}


class FakeV2:
    def __init__(self, events, segments, status="done", pages=3, sse=True, end="done", poll_statuses=None):
        self.events, self.segments, self.status, self.pages = events, segments, status, pages
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
                                _seg(S1, 2, 1, _pred("CCN", ms=55, engine="molscribe"))])
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "molscribe", base_url="http://x", paper_id="PMC1")
    assert r["build"] == "v2-abc1234" and r["engine"] == "molscribe" and r["paper_id"] == "PMC1"
    assert r["pages_total"] == 3 and r["pages_with_segments"] == 2 and r["page_errors"] == []
    assert [s["segment_id"] for s in r["segments"]] == ["page_0_0", "page_2_1"]
    assert [s["page"] for s in r["segments"]] == [0, 2] and [s["smiles"] for s in r["segments"]] == ["CCO", "CCN"]
    assert all(s["error"] is None and s["ocsr_ms"] > 0 for s in r["segments"])
    assert r["segment_ms"] > 0 and r["wall_ms"] >= r["segment_ms"] and r["fatal_error"] is None
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
    events = [_step("render_page", "done", 0), _step("segment_page", "running", 0), _step("segment_page", "failed", 0),
              _step("render_page", "failed", 1),
              _step("ocsr", "running", 2, S1), _step("ocsr", "failed", 2, S1)]
    seg = [_seg(S1, 2, 0, [])]
    patch(monkeypatch, FakeV2(events, seg, status="done"))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert sorted((e["page"], e["kind"]) for e in r["page_errors"]) == [(0, "segment_page"), (1, "render_page")]
    assert all(e["error"] for e in r["page_errors"])
    assert r["segments"][0]["error"] and r["segments"][0]["smiles"] == ""


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
    fake = FakeV2([], [_seg(S0, 0, 0, _pred("CCO"))], sse=False, poll_statuses=["processing", "processing"])
    patch(monkeypatch, fake)
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["segments"][0]["smiles"] == "CCO" and r["fatal_error"] is None
    assert r["segments"][0]["ocsr_ms"] == 40  # no step events: the engine's own time
    assert sum(1 for m, p in fake.calls if p == f"/api/v2/papers/{PID}") >= 3
    assert r["events_mode"] == "poll"


def test_failed_paper_is_fatal_error(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([], [], status="failed", end="failed"))
    r = client_v2.run_paper(pdf, "decimer", base_url="http://x")
    assert r["fatal_error"] and "failed" in r["fatal_error"]


def test_no_segments_is_not_fatal(monkeypatch, pdf):
    patch(monkeypatch, FakeV2([_step("segment_page", "done", 0)], []))
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
