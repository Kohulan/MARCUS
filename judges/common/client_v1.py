"""Drive the current MARCUS build (v1) the way the browser does.

Frontend flow reproduced (frontend/src/store/modules/structures.js, services/*.js):

  [ui_extras only]  POST /session/create                      (sessionService.createSession)
  [ui_extras only]  POST /latest/decimer/extract_doi          (HomeView.handlePdfUploaded; uploads the PDF once)
                    POST /latest/decimer/extract_segments     (fetchSegments; multipart pdf_file + collect_all=true)
                    GET  /latest/decimer/list_directory/<stem>/all_segments    (listSegmentFiles)
  [ui_extras only]  GET  /latest/decimer/get_segment_image/<stem>/<file>  per segment (the <img> tags)
  per segment, one after the other (ocsrService.processSegments is a sequential for-loop):
                    POST /latest/ocsr/generate_with_depiction (image_path, engine, output_type, rdkit/svg 512x512)
                    on any error -> POST /latest/ocsr/generate_both (fallback); if that fails too the
                    segment is an error row.
  [ui_extras only]  POST /latest/depiction/generate per structure (the structure cards)

Core pipeline = 2 + N calls (N = segments), +1 per failed first attempt. With ``ui_extras`` it is
4 + 3N. Heartbeats (HTTP or websocket every 15 s) are not counted.

Things the UI does not do and this client adds (all recorded in the run line):
  * a unique upload filename and unique PDF bytes per run (the backend reuses an existing upload by
    filename, and caches segmentation results by MD5 of the PDF), so every run really segments;
  * HTTP 429 handling: the backend rate limiter (about 20 requests/min per client IP, shared by all
    endpoints) can reject a call. The UI shows an error row. By default (on_429="retry") this client
    waits for Retry-After and retries so recognition numbers are not polluted, and records the events.
    Use on_429="fail" for raw UI behaviour.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
import uuid
import weakref
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import remote

BUILD = "v1-976396a5"
API = "/latest"  # the UI's axios instance prefixes every call with /latest

# UI timeouts (frontend/src/services/api.js: 300 s for every call on the shared axios instance, uploads included;
# ocsrService.js: 60 s for generate_with_depiction and generate_both)
UI_SEGMENT_TIMEOUT_S = 300
UI_OCSR_TIMEOUT_S = 60

_ACTIVE: "weakref.WeakSet[httpx.Client]" = weakref.WeakSet()
_SEG_FILE = re.compile(r"^page_(\d+)_(\d+)_segmented\.png$")


class Aborted(RuntimeError):
    """The guard (or caller) asked the run to stop."""


def abort_all() -> int:
    """Close every client opened by run_paper (used by guard_jarvis to stop in-flight calls)."""
    n = 0
    for c in list(_ACTIVE):
        try:
            c.close()
            n += 1
        except Exception:
            pass
    return n


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


LOCAL_CONTAINERS = {19000: "marcus-judge-backend", 19100: "marcus-judge-load"}  # port -> local container name


def _container_for_port(port: int) -> str | None:
    """Name of the local docker container that publishes ``port`` (any local copy), else None."""
    if port in LOCAL_CONTAINERS:
        return LOCAL_CONTAINERS[port]
    try:
        out = remote.local_run(["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"], timeout=10)
        names = [n for n in out.split() if n]
        return names[0] if names else None
    except Exception:
        return None


def default_log_source(base_url: str):
    """Pick the log reader for a base URL: local container publishing the port, jarvis (ssh) for :29000."""
    u = httpx.URL(base_url)
    if u.port == 29000:
        return remote.DockerLogs(remote.REMOTE_JUDGE_CONTAINER, remote=True)
    if u.host in ("localhost", "127.0.0.1") and u.port:
        name = _container_for_port(u.port)
        if name:
            return remote.DockerLogs(name, remote=False)
    return None


class _Calls:
    """Per-run HTTP call recorder."""

    def __init__(self, t0: float, keep_log: bool):
        self.t0 = t0
        self.keep_log = keep_log
        self.count = 0
        self.by_step: dict[str, int] = {}
        self.ms_by_step: dict[str, float] = {}
        self.log: list[dict] = []
        self.rate_limit_events: list[dict] = []

    def add(self, step: str, method: str, path: str, status: int | None, t_start: float, ms: float, err: str | None = None):
        self.count += 1
        self.by_step[step] = self.by_step.get(step, 0) + 1
        self.ms_by_step[step] = self.ms_by_step.get(step, 0.0) + ms
        if self.keep_log:
            self.log.append({"step": step, "method": method, "path": path, "status": status,
                             "t_ms": round((t_start - self.t0) * 1000, 1), "ms": round(ms, 1), "error": err})


def _err_text(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        try:
            d = e.response.json().get("detail")
        except Exception:
            d = e.response.text[:200]
        return f"HTTP {e.response.status_code}: {str(d)[:300]}"
    return f"{type(e).__name__}: {str(e)[:300]}"


def run_paper(
    pdf_path,
    engine: str,
    *,
    base_url: str,
    paper_id: str | None = None,
    max_segments: int | None = None,
    reuse_upload: bool = False,
    unique_bytes: bool = True,
    on_429: str = "retry",
    max_429_retries: int = 8,
    ui_extras: bool = False,
    segment_timeout_s: float = UI_SEGMENT_TIMEOUT_S,
    ocsr_timeout_s: float = UI_OCSR_TIMEOUT_S,
    abort: threading.Event | None = None,
    log_source="auto",
    keep_http_log: bool = False,
    tag: str | None = None,
    on_event=None,
) -> dict:
    """Run one paper through v1 and return one run record (README format plus extra fields).

    pdf_path        local PDF. ``pdf_sha256`` in the record is the sha256 of this file as given.
    paper_id        manifest paper id; defaults to the file stem.
    max_segments    only run OCSR on the first N listed segments (load tests of huge papers).
    reuse_upload    keep the upload name/bytes stable so a second engine run reuses the first
                    segmentation (what the UI does when you switch engine). segment_ms is then ~0.
    on_429          "retry" (default) or "fail" (UI behaviour), see module doc.
    log_source      "auto" (docker logs of the local container that publishes the port; ssh read-only docker logs
                    for :29000), None/False (off), or a remote.DockerLogs. Used only to read the page errors and
                    crash lines the API hides.
    tag             free text copied into the record (scenario name etc.).
    on_event        optional callable(dict) for progress, called per OCSR segment.
    """
    pdf_path = Path(pdf_path)
    paper_id = paper_id or pdf_path.stem
    pdf_sha = sha256_file(pdf_path)
    data = pdf_path.read_bytes()
    nonce = uuid.uuid4().hex[:12]
    safe_id = re.sub(r"[^\w-]", "_", paper_id)
    if reuse_upload:
        up_name = f"{safe_id}__{pdf_sha[:12]}.pdf"
    else:
        up_name = f"{safe_id}__{nonce}.pdf"
        if unique_bytes:
            data = data + b"\n%judge-nonce " + nonce.encode() + b"\n"
    up_sha = hashlib.sha256(data).hexdigest()
    stem = up_name[:-4]

    started_at = now_iso()
    t0 = time.perf_counter()
    calls = _Calls(t0, keep_http_log)
    rec: dict = {
        "paper_id": paper_id, "pdf_sha256": pdf_sha, "engine": engine, "build": BUILD,
        "started_at": started_at, "wall_ms": None, "segment_ms": None,
        "pages_total": count_pdf_pages(pdf_path), "pages_with_segments": 0,
        "page_errors": [], "segments": [],
        # extra fields (ignored by goldset/score.py)
        "client": "client_v1", "base_url": base_url, "tag": tag, "upload_name": up_name, "upload_sha256": up_sha,
        "ui_extras": ui_extras, "on_429": on_429, "segments_reported": None, "segments_listed": None,
        "segments_already_existed": None, "timings_ms": {}, "http_calls": 0, "http_calls_by_step": {},
        "rate_limit_events": [], "server_segment_s": [], "log_keywords": {}, "fatal_error": None,
        "aborted": False, "max_segments": max_segments, "backend_crash": None, "no_segments": False,
    }

    if log_source == "auto":
        log_source = default_log_source(base_url)
    mark = log_source.mark() if log_source else None

    client = httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(connect=15.0, read=max(segment_timeout_s, ocsr_timeout_s), write=120.0, pool=30.0),
        # no keep-alive: the production nginx opens a new connection to the backend for every request (HTTP/1.0
        # upstream); reusing connections made uvicorn drop in-flight requests ("Server disconnected") on the direct path
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=0),
    )
    _ACTIVE.add(client)

    def check_abort():
        if abort is not None and abort.is_set():
            raise Aborted("aborted by guard/caller")

    def call(step, method, path, *, timeout, **kw):
        """One HTTP call with timing, optional 429 retry. Returns the httpx response (status < 400)."""
        attempts = 0
        while True:
            check_abort()
            ts = time.perf_counter()
            try:
                r = client.request(method, path, timeout=timeout, **kw)
            except Exception as e:
                calls.add(step, method, path, None, ts, (time.perf_counter() - ts) * 1000, _err_text(e))
                check_abort()
                raise
            ms = (time.perf_counter() - ts) * 1000
            calls.add(step, method, path, r.status_code, ts, ms, None if r.status_code < 400 else r.text[:120])
            if r.status_code == 429 and on_429 == "retry" and attempts < max_429_retries:
                try:
                    ra = float(r.headers.get("Retry-After") or r.json().get("retry_after") or 20)
                except Exception:
                    ra = 20.0
                ra = min(ra, 120.0) + 0.5
                calls.rate_limit_events.append({"step": step, "t_ms": round((ts - t0) * 1000, 1), "wait_s": ra, "attempt": attempts + 1})
                attempts += 1
                end = time.perf_counter() + ra
                while time.perf_counter() < end:
                    check_abort()
                    time.sleep(min(0.5, end - time.perf_counter()))
                continue
            r.raise_for_status()
            return r

    try:
        # ---------------------------------------------------------------- upload side
        if ui_extras:
            ts = time.perf_counter()
            r = call("session_create", "POST", "/session/create", timeout=30)
            sid = r.json().get("session", {}).get("session_id")
            rec["timings_ms"]["session_create"] = round((time.perf_counter() - ts) * 1000, 1)
            rec["session_id"] = sid
            ts = time.perf_counter()
            try:
                call("extract_doi", "POST", f"{API}/decimer/extract_doi", timeout=segment_timeout_s,
                     files={"pdf_file": (up_name, data, "application/pdf")})
            except Aborted:
                raise
            except Exception as e:  # the UI ignores DOI errors ("Continue without DOI - not critical")
                rec["doi_error"] = _err_text(e)
            rec["timings_ms"]["extract_doi"] = round((time.perf_counter() - ts) * 1000, 1)

        ts = time.perf_counter()
        seg_started_wall = now_iso()
        r = call("extract_segments", "POST", f"{API}/decimer/extract_segments", timeout=segment_timeout_s,
                 files={"pdf_file": (up_name, data, "application/pdf")}, data={"collect_all": "true"})
        seg_ms = (time.perf_counter() - ts) * 1000
        rec["segment_ms"] = round(seg_ms, 1)
        rec["segment_started_at"] = seg_started_wall
        rec["exceeds_ui_segment_timeout"] = seg_ms > UI_SEGMENT_TIMEOUT_S * 1000
        seg = r.json()
        rec["segments_reported"] = seg.get("segments_count")
        rec["segments_already_existed"] = seg.get("segments_already_existed")
        if not seg.get("segments_count"):
            # legitimate outcome (paper draws no structure). The UI shows "Invalid segment extraction response".
            rec["no_segments"] = True
            raise _Stop()

        directory = seg.get("segments_directory") or ""
        directory = directory.split("/all_segments")[0] if "/all_segments" in directory else directory

        ts = time.perf_counter()
        r = call("list_directory", "GET", f"{API}/decimer/list_directory/{directory}/all_segments", timeout=segment_timeout_s)
        rec["timings_ms"]["list_directory"] = round((time.perf_counter() - ts) * 1000, 1)
        files = r.json().get("files") or []
        rec["segments_listed"] = len(files)
        if len(files) != seg.get("segments_count"):
            rec["listing_mismatch"] = {"reported": seg.get("segments_count"), "listed": len(files)}

        items = []
        for fn in files:  # server order, as the UI does (no sort)
            m = _SEG_FILE.match(fn)
            page, idx = (int(m.group(1)), int(m.group(2))) if m else (None, None)
            items.append({"filename": fn, "page": page, "idx": idx})
        rec["listed_pages"] = sorted({it["page"] for it in items if it["page"] is not None})
        if max_segments is not None:
            items = items[:max_segments]

        if ui_extras:
            ts = time.perf_counter()
            for it in items:
                try:
                    call("segment_image", "GET", f"{API}/decimer/get_segment_image/{directory}/{it['filename']}", timeout=segment_timeout_s)
                except Aborted:
                    raise
                except Exception:
                    pass
            rec["timings_ms"]["segment_images"] = round((time.perf_counter() - ts) * 1000, 1)

        # ---------------------------------------------------------------- OCSR loop (sequential)
        include_molfile = engine in ("molnextr", "molscribe")  # structures.js turns this on for these engines
        ocsr_t = time.perf_counter()
        structures = []
        for n, it in enumerate(items):
            check_abort()
            image_path = f"{directory}/all_segments/{it['filename']}"
            row = {"segment_id": f"page_{it['page']}_{it['idx']}" if it["page"] is not None else it["filename"],
                   "page": it["page"], "page_number": (it["page"] + 1) if it["page"] is not None else None,
                   "filename": it["filename"], "smiles": "", "ocsr_ms": None, "error": None,
                   "fallback": False, "t_start_ms": round((time.perf_counter() - t0) * 1000, 1)}
            form = {"image_path": image_path, "engine": engine, "output_type": "both" if include_molfile else "smiles",
                    "hand_drawn": "false", "depict_engine": "rdkit", "depict_width": "512", "depict_height": "512",
                    "depict_format": "svg"}
            ts = time.perf_counter()
            n429 = len(calls.rate_limit_events)
            resp = None
            try:
                resp = call("ocsr", "POST", f"{API}/ocsr/generate_with_depiction", timeout=ocsr_timeout_s, files=_multipart(form)).json()
            except Aborted:
                raise
            except Exception as e1:
                first_err = _err_text(e1)
                row["first_error"] = first_err
                try:  # UI fallback: generateBoth
                    fb = {"image_path": image_path, "engine": engine, "hand_drawn": "false"}
                    resp = call("ocsr_fallback", "POST", f"{API}/ocsr/generate_both", timeout=ocsr_timeout_s, files=_multipart(fb)).json()
                    row["fallback"] = True
                except Aborted:
                    raise
                except Exception as e2:
                    row["error"] = first_err  # the UI reports the first error message
                    row["fallback_error"] = _err_text(e2)
            row["ocsr_ms"] = round((time.perf_counter() - ts) * 1000, 1)
            row["rate_limited"] = len(calls.rate_limit_events) - n429
            if resp is not None:
                row["smiles"] = resp.get("smiles") or ""
            structures.append(row)
            rec["segments"].append(row)
            if on_event:
                on_event({"event": "segment", "i": n, "of": len(items), "ms": row["ocsr_ms"], "error": row["error"]})
        rec["timings_ms"]["ocsr_loop"] = round((time.perf_counter() - ocsr_t) * 1000, 1)

        if ui_extras:
            ts = time.perf_counter()
            for row in structures:
                if row["smiles"]:
                    body = {"smiles": row["smiles"], "engine": "cdk", "width": 512, "height": 512, "rotate": 0,
                            "kekulize": True, "cip": True, "unicolor": False, "highlight": "", "transparent": False,
                            "format": "svg", "useMolfileDirectly": False}
                    try:
                        call("depiction", "POST", f"{API}/depiction/generate", timeout=segment_timeout_s, json=body)
                    except Aborted:
                        raise
                    except Exception:
                        pass
            rec["timings_ms"]["depictions"] = round((time.perf_counter() - ts) * 1000, 1)
    except _Stop:
        pass
    except Aborted as e:
        rec["aborted"] = True
        rec["fatal_error"] = str(e)
    except Exception as e:
        rec["fatal_error"] = _err_text(e)
        if abort is not None and abort.is_set():
            rec["aborted"] = True
    finally:
        try:
            client.close()
        except Exception:
            pass
        _ACTIVE.discard(client)

    rec["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    rec["pages_with_segments"] = len(rec.get("listed_pages") or {s["page"] for s in rec["segments"] if s["page"] is not None})
    rec["http_calls"] = calls.count
    rec["http_calls_by_step"] = calls.by_step
    rec["rate_limit_events"] = calls.rate_limit_events
    if keep_http_log:
        rec["http_log"] = calls.log

    # page errors the API hides (backend prints them; read after the run, only the lines written since)
    if log_source and mark is not None:
        parsed = remote.parse_server_log(log_source.since(mark))
        rec["page_errors"] = [{"page": e["page"], "error": e["error"], "kind": e["kind"]} for e in parsed["page_errors"]]
        rec["page_error_layers"] = sorted({e["layer_type"] for e in parsed["page_errors"] if e["layer_type"]})
        rec["server_segment_s"] = parsed["server_segment_s"]
        rec["log_keywords"] = parsed["keyword_counts"]
        rec["backend_crash"] = parsed["backend_crash"]
        rec["page_errors_source"] = "docker logs (time window; ambiguous if other runs overlapped)"
    else:
        rec["page_errors_source"] = "unavailable"
    return rec


def _multipart(fields: dict) -> dict:
    """Form fields as multipart/form-data parts, like the browser's FormData (httpx sends urlencoded otherwise)."""
    return {k: (None, v) for k, v in fields.items()}


class _Stop(Exception):
    pass
