"""Drive the v2 API (backend-v2) and return the same run record as ``client_v1.run_paper``.

Flow (one ``httpx.Client`` per paper so the HttpOnly ``marcus_owner`` cookie issued on the upload carries):

    POST /api/v2/papers                     multipart file + engine + ocsr ("auto": OCSR runs for every segment)
    GET  /api/v2/papers/{id}/events         SSE: step events (kind, status, page, segment_id) until ``event: end``
         fallback: GET /api/v2/papers/{id}  polled every POLL_S (2 s) when the stream is refused, drops or ends
                                            without ``end``
    GET  /api/v2/papers/{id}                final state: status, pages, segments with their predictions

With ``max_segments=N`` the paper is uploaded with ocsr="off" and only the first N segments get
``POST /api/v2/segments/{id}/predictions`` (v1 ran OCSR on the first N listed segments).

What the v2 API does and does not expose (it has no steps endpoint): step events carry no timestamps and no
error_class, so every duration here is what this client observed on the stream (event arrival):

  segment_ms  first segment_page "running" -> last segment_page terminal event. None when no segment_page
              event was seen (polling fallback, or all events missed: the stream starts after the upload
              returns, so very early events can be missed).
  ocsr_ms     per segment: ocsr running -> terminal event; else the engine's own ``ms`` from the prediction.
  page_errors one entry per render_page / segment_page step whose last event is "failed";
              ``error_class`` is None (not exposed by the API).

Differences from v1 inputs: ``on_429``, ``max_429_retries``, ``ui_extras`` and ``log_source`` are v1-only
(no UI call sequence, page errors come from step events, not docker logs): accepted and ignored. Keys with
no v2 meaning (``server_segment_s``, ``backend_crash``, ``listing_mismatch`` ...) are None or empty, never
dropped. ``segment_timeout_s`` / ``ocsr_timeout_s`` only flag records (``exceeds_ui_segment_timeout``,
``exceeds_ocsr_timeout``); the run itself is bounded by ``paper_timeout_s``.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import time
import uuid
import weakref
from pathlib import Path

import httpx

from . import target
from .client_v1 import Aborted, count_pdf_pages, now_iso, sha256_file

API = "/api/v2"
OWNER_COOKIE = "marcus_owner"
POLL_S = 2.0
UI_SEGMENT_TIMEOUT_S = 300
UI_OCSR_TIMEOUT_S = 60
PAPER_TIMEOUT_S = 3600.0
# v1 engine names (run_goldset.py) -> v2 engine identifiers (marcus.core.enums.Engine); "fake" only works
# against a stack started with MARCUS_ENABLE_FAKE_ENGINES=1
ENGINES = {"decimer": "decimer", "decimer-hand": "decimer-hand", "molnextr": "molnextr",
           "molscribe": "molscribe", "fake": "fake"}
TERMINAL = {"done", "failed", "deleted"}
ACTIVE_STEP = ("pending", "queued", "running")

_ACTIVE: "weakref.WeakSet[httpx.Client]" = weakref.WeakSet()
_REPO = Path(__file__).resolve().parents[2]


def abort_all() -> int:
    """Close every client opened by run_paper (same contract as client_v1.abort_all)."""
    n = 0
    for c in list(_ACTIVE):
        try:
            c.close()
            n += 1
        except Exception:
            pass
    return n


def git_short_hash() -> str:
    try:
        out = subprocess.run(["git", "-C", str(_REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=True).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _keep_owner_cookie(client: httpx.Client, resp: httpx.Response) -> None:
    """Send the owner cookie ourselves. The server marks it Secure; httpx's cookie jar then refuses to send it
    over plain http (a browser treats http://localhost as secure, httpx does not), and the local stack is http."""
    for sc in resp.headers.get_list("set-cookie"):
        m = re.match(rf"\s*{OWNER_COOKIE}=([^;]*)", sc)
        if m:
            client.headers["Cookie"] = f"{OWNER_COOKIE}={m.group(1)}"


def _err_text(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        try:
            d = e.response.json().get("detail")
        except Exception:
            d = e.response.text[:200]
        return f"HTTP {e.response.status_code}: {str(d)[:300]}"
    return f"{type(e).__name__}: {str(e)[:300]}"


class _Steps:
    """Step events seen on the stream, keyed by step_id (events carry no timestamps: arrival time is used)."""

    def __init__(self):
        self.by_id: dict[str, dict] = {}
        self.count = 0

    def add(self, ev: dict, t: float) -> dict | None:
        if ev.get("type") != "step" or not ev.get("step_id"):
            return None
        self.count += 1
        s = self.by_id.setdefault(ev["step_id"], {"kind": ev.get("kind"), "page": ev.get("page"),
                                                  "segment_id": ev.get("segment_id"), "t_start": None, "t_end": None,
                                                  "status": None})
        status = ev.get("status")
        s["status"] = status
        if status == "running":
            if s["t_start"] is None:
                s["t_start"] = t
            s["t_end"] = None
        elif status in ("done", "failed", "cancelled"):
            s["t_end"] = t
        return s

    def of_kind(self, kind: str):
        return [s for s in self.by_id.values() if s["kind"] == kind]


def run_paper(
    pdf_path,
    engine: str,
    *,
    base_url: str,
    paper_id: str | None = None,
    max_segments: int | None = None,
    reuse_upload: bool = False,
    unique_bytes: bool = True,
    on_429: str = "retry",  # v1-only, ignored (429 is retried using Retry-After, up to max_429_retries)
    max_429_retries: int = 8,
    ui_extras: bool = False,  # v1-only, ignored
    segment_timeout_s: float = UI_SEGMENT_TIMEOUT_S,
    ocsr_timeout_s: float = UI_OCSR_TIMEOUT_S,
    paper_timeout_s: float = PAPER_TIMEOUT_S,
    abort: threading.Event | None = None,
    log_source=None,  # v1-only, ignored
    keep_http_log: bool = False,
    tag: str | None = None,
    on_event=None,
) -> dict:
    """Run one paper through v2 and return one run record (client_v1 format, see module doc)."""
    base_url = target._check(base_url)  # refuses production hostnames (SystemExit)
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; v2 engines: {sorted(ENGINES)}")
    v2_engine = ENGINES[engine]

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

    started_at = now_iso()
    t0 = time.perf_counter()
    deadline = t0 + paper_timeout_s
    log: list[dict] = []
    http = {"n": 0, "by": {}}
    rate_events: list[dict] = []
    rec: dict = {
        "paper_id": paper_id, "pdf_sha256": pdf_sha, "engine": engine, "build": f"v2-{git_short_hash()}",
        "started_at": started_at, "wall_ms": None, "segment_ms": None,
        "pages_total": count_pdf_pages(pdf_path), "pages_with_segments": 0,
        "page_errors": [], "segments": [],
        "client": "client_v2", "base_url": base_url, "tag": tag, "upload_name": up_name, "upload_sha256": up_sha,
        "ui_extras": False, "on_429": "retry", "segments_reported": None, "segments_listed": None,
        "segments_already_existed": None, "timings_ms": {}, "http_calls": 0, "http_calls_by_step": {},
        "rate_limit_events": [], "server_segment_s": [], "log_keywords": {}, "fatal_error": None,
        "aborted": False, "max_segments": max_segments, "backend_crash": None, "no_segments": False,
        "v2_engine": v2_engine, "v2_paper_id": None, "events_mode": None, "events_seen": 0,
        "page_errors_source": "step events (failed render_page/segment_page); error_class not exposed by the API",
    }

    client = httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(connect=15.0, read=60.0, write=120.0, pool=30.0),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=0),
    )
    _ACTIVE.add(client)

    def check_abort():
        if abort is not None and abort.is_set():
            raise Aborted("aborted by guard/caller")

    def call(step, method, path, **kw) -> httpx.Response:
        """One HTTP call with 429 retry; returns a response with status < 400."""
        attempts = 0
        while True:
            check_abort()
            ts = time.perf_counter()
            try:
                r = client.request(method, path, **kw)
            except Exception as e:
                http["n"] += 1
                http["by"][step] = http["by"].get(step, 0) + 1
                check_abort()
                if keep_http_log:
                    log.append({"step": step, "method": method, "path": path, "status": None, "error": _err_text(e)})
                raise
            http["n"] += 1
            http["by"][step] = http["by"].get(step, 0) + 1
            if keep_http_log:
                log.append({"step": step, "method": method, "path": path, "status": r.status_code,
                            "t_ms": round((ts - t0) * 1000, 1), "ms": round((time.perf_counter() - ts) * 1000, 1)})
            if r.status_code == 429 and attempts < max_429_retries:
                try:
                    ra = float(r.headers.get("Retry-After") or 20)
                except Exception:
                    ra = 20.0
                ra = min(ra, 120.0) + 0.5
                rate_events.append({"step": step, "t_ms": round((ts - t0) * 1000, 1), "wait_s": ra, "attempt": attempts + 1})
                attempts += 1
                end = time.perf_counter() + ra
                while time.perf_counter() < end:
                    check_abort()
                    time.sleep(min(0.5, end - time.perf_counter()))
                continue
            r.raise_for_status()
            _keep_owner_cookie(client, r)
            return r

    def get_paper(pid) -> dict:
        return call("paper", "GET", f"{API}/papers/{pid}").json()

    steps = _Steps()

    def on_step(ev: dict):
        s = steps.add(ev, time.perf_counter())
        if s and on_event and s["kind"] == "ocsr" and s["status"] in ("done", "failed"):
            ms = round((s["t_end"] - s["t_start"]) * 1000, 1) if s["t_start"] else None
            on_event({"event": "segment", "i": None, "of": None, "ms": ms, "error": "failed" if s["status"] == "failed" else None})

    def stream_events(pid) -> str | None:
        """SSE until ``event: end``. Returns the final status, or None when the stream gave up."""
        try:
            with client.stream("GET", f"{API}/papers/{pid}/events", timeout=httpx.Timeout(15.0, read=90.0)) as resp:
                http["n"] += 1
                http["by"]["events"] = http["by"].get("events", 0) + 1
                if resp.status_code != 200:
                    return None
                name, buf = "message", []
                for line in resp.iter_lines():
                    check_abort()
                    if time.perf_counter() > deadline:
                        raise TimeoutError(f"paper not finished after {paper_timeout_s:.0f} s")
                    if line == "":
                        if buf:
                            try:
                                payload = json.loads("\n".join(buf))
                            except ValueError:
                                payload = None
                            if name == "end" and isinstance(payload, dict):
                                return payload.get("status")
                            if name == "message" and isinstance(payload, dict):
                                on_step(payload)
                        name, buf = "message", []
                    elif line.startswith("event:"):
                        name = line[6:].strip()
                    elif line.startswith("data:"):
                        buf.append(line[5:].lstrip())
                return None
        except (TimeoutError, Aborted):
            raise
        except Exception:
            check_abort()
            return None

    def poll_until_done(pid) -> str:
        while True:
            d = get_paper(pid)
            if d["status"] in TERMINAL:
                return d["status"]
            if time.perf_counter() > deadline:
                raise TimeoutError(f"paper not finished after {paper_timeout_s:.0f} s")
            check_abort()
            time.sleep(POLL_S)

    status = None
    detail: dict = {}
    pid = None
    try:
        check_abort()
        up = call("upload", "POST", f"{API}/papers", files={"file": (up_name, data, "application/pdf")},
                  data={"engine": v2_engine, "ocsr": "auto" if max_segments is None else "off"})
        pid = up.json()["paper_id"]
        rec["v2_paper_id"] = pid

        rec["events_mode"] = "sse"
        status = stream_events(pid)
        if status is None:  # stream refused, dropped or closed without `end`: poll instead
            rec["events_mode"] = "poll"
            status = poll_until_done(pid)
        detail = get_paper(pid)

        if max_segments is not None and status == "done" and max_segments > 0:
            ts = time.perf_counter()
            wanted = [s["id"] for s in detail["segments"][:max_segments]]
            for sid in wanted:
                call("prediction", "POST", f"{API}/segments/{sid}/predictions", json={"engine": v2_engine})
            while True:  # until each has a prediction, or nothing is left to run
                detail = get_paper(pid)
                have = {s["id"]: any(p["engine"] == v2_engine for p in s["predictions"]) for s in detail["segments"]}
                counts = (detail.get("counts") or {}).get("steps_by_status") or {}
                idle = not any(counts.get(k) for k in ACTIVE_STEP)
                if all(have.get(s) for s in wanted) or idle:
                    break
                if time.perf_counter() > deadline:
                    raise TimeoutError(f"predictions not finished after {paper_timeout_s:.0f} s")
                check_abort()
                time.sleep(POLL_S)
            rec["timings_ms"]["predictions"] = round((time.perf_counter() - ts) * 1000, 1)
        if status == "failed":
            rec["fatal_error"] = "PaperFailed: v2 paper status 'failed'"
        elif status == "deleted":
            rec["fatal_error"] = "PaperDeleted: the paper was removed while running"
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

    # ------------------------------------------------------------------ build the record
    segs_all = detail.get("segments") or []
    if detail.get("pages") is not None:
        rec["pages_total"] = detail["pages"]
    rec["segments_reported"] = rec["segments_listed"] = len(segs_all) if detail else None
    rec["listed_pages"] = sorted({s["page"] for s in segs_all})
    rec["pages_with_segments"] = len(rec["listed_pages"])
    rec["no_segments"] = bool(detail) and not segs_all and rec["fatal_error"] is None
    rec["events_seen"] = steps.count

    failed_ids = {s["segment_id"] for s in steps.of_kind("ocsr") if s["status"] == "failed"}
    ocsr_by_seg = {s["segment_id"]: s for s in steps.of_kind("ocsr")}
    rows = segs_all if max_segments is None else segs_all[:max_segments]
    for seg in rows:
        pred = next((p for p in seg["predictions"] if p["engine"] == ENGINES[engine]), None)  # newest first
        st = ocsr_by_seg.get(seg["id"])
        observed = round((st["t_end"] - st["t_start"]) * 1000, 1) if st and st["t_start"] and st["t_end"] else None
        error = None
        if pred is None and rec["fatal_error"] is None:
            error = "ocsr step failed" if seg["id"] in failed_ids else "no prediction"
        row = {"segment_id": f"page_{seg['page']}_{seg['idx']}", "page": seg["page"], "page_number": seg["page"] + 1,
               "filename": None, "smiles": (pred or {}).get("smiles") or "",
               "ocsr_ms": observed if observed is not None else (pred or {}).get("ms"),
               "error": error, "fallback": False,
               "t_start_ms": round((st["t_start"] - t0) * 1000, 1) if st and st["t_start"] else None,
               "rate_limited": 0, "v2_segment_id": seg["id"], "valid": (pred or {}).get("valid"),
               "engine_ms": (pred or {}).get("ms"), "engine_version": (pred or {}).get("engine_version")}
        row["exceeds_ocsr_timeout"] = bool(row["ocsr_ms"] and row["ocsr_ms"] > ocsr_timeout_s * 1000)
        rec["segments"].append(row)

    seg_steps = steps.of_kind("segment_page")
    starts = [s["t_start"] for s in seg_steps if s["t_start"]]
    ends = [s["t_end"] for s in seg_steps if s["t_end"]]
    if starts and ends:
        seg_ms = (max(ends) - min(starts)) * 1000
        rec["segment_ms"] = round(seg_ms, 1)
        rec["exceeds_ui_segment_timeout"] = seg_ms > segment_timeout_s * 1000
    for kind in ("render_page", "segment_page"):
        for s in steps.of_kind(kind):
            if s["status"] == "failed":
                rec["page_errors"].append({"page": s["page"], "error": f"{kind} step failed", "kind": kind,
                                           "error_class": None})
    rec["page_errors"].sort(key=lambda e: (e["page"] is None, e["page"], e["kind"]))

    rec["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    rec["http_calls"] = http["n"]
    rec["http_calls_by_step"] = http["by"]
    rec["rate_limit_events"] = rate_events
    if keep_http_log:
        rec["http_log"] = log
    return rec
