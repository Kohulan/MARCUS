"""Offline tests for common/client_v1.py with a fake backend (httpx.MockTransport): call sequence, fallback,
429 retry, unique upload names, empty result. No network, no docker."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import client_v1  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class Fake:
    def __init__(self, files, fail_first_ocsr=(), fail_all=(), rate_limit_first=0, count=None):
        self.files, self.calls, self.uploads = files, [], []
        self.fail_first_ocsr, self.fail_all = set(fail_first_ocsr), set(fail_all)
        self.rate_limit_first, self.count = rate_limit_first, count
        self.seen_ocsr = set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.calls.append((req.method, path))
        body = req.content.decode("latin1")
        if path.endswith("/decimer/extract_segments"):
            name = [l for l in body.split("\r\n") if 'name="pdf_file"' in l][0].split('filename="')[1].split('"')[0]
            self.uploads.append(name)
            return httpx.Response(200, json={"segments_count": len(self.files) if self.count is None else self.count,
                                             "segments_directory": f"{name[:-4]}/all_segments", "segments_already_existed": False})
        if "/decimer/list_directory/" in path:
            return httpx.Response(200, json={"files": self.files})
        if path.endswith("/ocsr/generate_with_depiction") or path.endswith("/ocsr/generate_both"):
            img = [l for l in body.split("\r\n") if "all_segments/" in l][0].strip().split("/")[-1]
            if self.rate_limit_first > 0:
                self.rate_limit_first -= 1
                return httpx.Response(429, json={"detail": "x", "retry_after": 0}, headers={"Retry-After": "0"})
            if path.endswith("with_depiction") and (img in self.fail_all or (img in self.fail_first_ocsr and img not in self.seen_ocsr)):
                self.seen_ocsr.add(img)
                return httpx.Response(500, json={"detail": "boom"})
            if path.endswith("generate_both") and img in self.fail_all:
                return httpx.Response(500, json={"detail": "boom2"})
            return httpx.Response(200, json={"smiles": "CCO"})
        return httpx.Response(404)


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "PMC1.pdf"
    p.write_bytes(PDF)
    return p


_REAL_CLIENT = httpx.Client


def patch(monkeypatch, fake):
    real = _REAL_CLIENT
    monkeypatch.setattr(client_v1.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
    monkeypatch.setattr(client_v1, "count_pdf_pages", lambda p: 3)


def test_core_flow_is_2_plus_n_calls(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png", "page_2_1_segmented.png", "page_2_0_segmented.png"])
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "molscribe", base_url="http://x", paper_id="PMC1", log_source=None)
    assert r["http_calls"] == 2 + 3 and r["http_calls_by_step"] == {"extract_segments": 1, "list_directory": 1, "ocsr": 3}
    assert [s["segment_id"] for s in r["segments"]] == ["page_0_0", "page_2_1", "page_2_0"]  # server order, not sorted
    assert [s["page"] for s in r["segments"]] == [0, 2, 2] and r["pages_with_segments"] == 2 and r["pages_total"] == 3
    assert r["build"].startswith("v1-") and r["engine"] == "molscribe" and r["paper_id"] == "PMC1"
    assert all(s["smiles"] == "CCO" and s["error"] is None for s in r["segments"])
    assert r["segment_ms"] > 0 and r["wall_ms"] >= r["segment_ms"] and r["fatal_error"] is None


def test_ui_extras_is_4_plus_3n(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png", "page_0_1_segmented.png"])
    patch(monkeypatch, fake)
    orig = fake.__call__

    def handler(req):
        if req.url.path.endswith("/session/create"):
            return httpx.Response(200, json={"session": {"session_id": "s1"}})
        if req.url.path.endswith("/extract_doi"):
            return httpx.Response(200, json={"doi": "10.1/x"})
        if "get_segment_image" in req.url.path or req.url.path.endswith("/depiction/generate"):
            return httpx.Response(200, content=b"x")
        return orig(req)

    patch(monkeypatch, handler)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", ui_extras=True, log_source=None)
    assert r["http_calls"] == 4 + 3 * 2


def test_fallback_to_generate_both(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png", "page_0_1_segmented.png"], fail_first_ocsr=["page_0_0_segmented.png"])
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    a, b = r["segments"]
    assert a["fallback"] is True and a["error"] is None and a["smiles"] == "CCO"
    assert b["fallback"] is False
    assert r["http_calls_by_step"]["ocsr_fallback"] == 1


def test_error_row_when_both_fail(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png"], fail_all=["page_0_0_segmented.png"])
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    assert r["segments"][0]["error"].startswith("HTTP 500") and r["segments"][0]["smiles"] == ""


def test_429_retry_and_fail_modes(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png"], rate_limit_first=2)
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    assert r["segments"][0]["smiles"] == "CCO" and len(r["rate_limit_events"]) == 2 and r["segments"][0]["rate_limited"] == 2
    fake = Fake(["page_0_0_segmented.png"], rate_limit_first=99)
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None, on_429="fail")
    assert r["segments"][0]["error"].startswith("HTTP 429") and not r["rate_limit_events"]


def test_unique_names_and_bytes_vs_reuse(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png"])
    patch(monkeypatch, fake)
    a = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    b = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    assert a["upload_name"] != b["upload_name"] and a["upload_sha256"] != b["upload_sha256"]
    assert a["pdf_sha256"] == b["pdf_sha256"]  # the record keeps the original file's hash (manifest join)
    c = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None, reuse_upload=True)
    d = client_v1.run_paper(pdf, "molscribe", base_url="http://x", log_source=None, reuse_upload=True)
    assert c["upload_name"] == d["upload_name"] and c["upload_sha256"] == d["upload_sha256"]


def test_no_segments_is_not_fatal(monkeypatch, pdf):
    fake = Fake([], count=0)
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    assert r["no_segments"] is True and r["fatal_error"] is None and r["segments"] == [] and r["http_calls"] == 1


def test_max_segments_zero_only_segments(monkeypatch, pdf):
    fake = Fake(["page_0_0_segmented.png", "page_1_0_segmented.png"])
    patch(monkeypatch, fake)
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None, max_segments=0)
    assert r["segments"] == [] and r["segments_listed"] == 2 and r["listed_pages"] == [0, 1] and r["pages_with_segments"] == 2


def test_abort_event_stops_before_ocsr(monkeypatch, pdf):
    import threading

    fake = Fake(["page_0_0_segmented.png", "page_0_1_segmented.png"])
    patch(monkeypatch, fake)
    ev = threading.Event()
    ev.set()
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None, abort=ev)
    assert r["aborted"] is True and r["http_calls"] == 0


def test_record_is_json_serialisable_and_has_readme_fields(monkeypatch, pdf):
    patch(monkeypatch, Fake(["page_0_0_segmented.png"]))
    r = client_v1.run_paper(pdf, "decimer", base_url="http://x", log_source=None)
    json.dumps(r)
    for k in ("paper_id", "pdf_sha256", "engine", "build", "started_at", "wall_ms", "segment_ms", "pages_total",
              "pages_with_segments", "page_errors", "segments"):
        assert k in r
    for k in ("segment_id", "page", "smiles", "ocsr_ms", "error"):
        assert k in r["segments"][0]
