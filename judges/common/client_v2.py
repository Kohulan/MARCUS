"""Drive the v2 API (backend-v2) and return the same run record as ``client_v1.run_paper``.

Flow (one ``httpx.Client`` per paper so the HttpOnly ``marcus_owner`` cookie issued on the upload carries):

    POST /api/v2/papers                     multipart file + engine + ocsr ("auto": OCSR runs for every segment)
    GET  /api/v2/papers/{id}/events         SSE: step events (kind, status, page, segment_id) until ``event: end``
         fallback: GET /api/v2/papers/{id}  polled every POLL_S (2 s) when the stream is refused, drops or ends
                                            without ``end``
    GET  /api/v2/papers/{id}                final state: status, pages, segments with their predictions

With ``max_segments=N`` the paper is uploaded with ocsr="off" and only the first N segments get
``POST /api/v2/segments/{id}/predictions`` (v1 ran OCSR on the first N listed segments).

Timings and errors come from ``GET /api/v2/papers/{id}/steps`` (read once the paper is terminal; step
timestamps are the server's clock, only differences of them are used). SSE is used only for progress
(``on_event``) and to detect the end. The same key means the same thing as in v1; v2-only numbers have NEW keys:

  segment_ms          v1: wall time of the extract_segments call (upload -> all segments listed). v2: the
                      client's upload round trip + (last segment_page finished_at - paper's first step
                      created_at). Includes upload, check_pdf, render, queue wait. None when no
                      segment_page step exists (e.g. segmentation cache hit) or the steps are unavailable.
  segment_compute_ms  v2 only: first segment_page started_at -> last finished_at (worker time, no queue wait).
  ocsr_ms             per segment, v1: client round trip of the OCSR call. v2: the segment's newest ocsr step
                      created_at -> finished_at: queue wait, retries and timeouts included (created_at does not
                      reset on a retry). None when the timing is missing. NEVER falls back to ocsr_compute_ms.
  ocsr_compute_ms     per segment, v2 only: the engine's own ``ms`` (0 for a cache hit). ``ocsr_attempts`` and
                      ``ocsr_ms_source`` ("step created_at -> finished_at") say what ocsr_ms is.
  ocsr_cache_hits     run, v2 only: predictions served from the OCSR cache (``cached`` flag on the prediction,
                      also per segment as ``cached``). A hit takes about 0 ms, so v2 TIMING runs are valid only
                      on a cold cache: the first run of a (paper, engine) pair or a fresh stack. The unique
                      bytes of every upload defeat the PDF-level segmentation cache but NOT the OCSR cache
                      (keyed by the crop image). Accuracy is unaffected. There is deliberately no bypass switch.
  page_errors         one entry per failed render_page / segment_page step: {page, error, kind, error_class}.
  failed_steps        v2 only: every check_pdf / docling / doi step that failed or carries an error_class (timed out and
                      was retried): {kind, status, error_class, attempts, duration_ms}. A paper can end ``done`` with a
                      failed docling (no text); its wall time is then a time limit, not the work.
  cancelled           v2 only: True when an aborted run deleted its paper (``DELETE /papers/{id}`` as its owner). On v2
                      the pipeline runs on the server, so closing the client does not stop GPU work.
  t_start_ms          per segment: ocsr started_at minus the paper's first step created_at (server clock only).
  first_segment_start_ms  v2 only: client upload round trip + (first segment_page started_at - paper's first
                      step created_at): when the paper's segmentation began, measured like segment_ms (spec §3 Fair).
  first_smiles_ms     v2 only: same origin, to the first ocsr step that finished ``done`` (first SMILES shown).
  ocsr_done_ms        v2 only: same origin, to the last ocsr step's finished_at (any final status). The v1-comparable
                      end of a paper: v1's wall_ms stops at the last OCSR answer, a v2 paper's wall_ms also waits
                      for its docling and doi steps.

Differences from v1 inputs: ``on_429``, ``max_429_retries``, ``ui_extras`` and ``log_source`` are v1-only
(no UI call sequence, page errors come from step events, not docker logs): accepted and ignored. Keys with
no v2 meaning (``server_segment_s``, ``backend_crash``, ``listing_mismatch`` ...) are None or empty, never
dropped. ``segment_timeout_s`` / ``ocsr_timeout_s`` only flag records (``exceeds_ui_segment_timeout``,
``exceeds_ocsr_timeout``); the run itself is bounded by ``paper_timeout_s``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import weakref
from datetime import datetime
from pathlib import Path

import httpx

from . import target
from .client_v1 import (
    Aborted,
    _err_text,
    close_all,
    count_pdf_pages,
    no_keepalive_client,
    now_iso,
    prepare_upload,
    retry_after_s,
    sleep_abortable,
)

API = "/api/v2"
OWNER_COOKIE = "marcus_owner"
# The API makes a new browser owner only for a request with this header, as the web app sends it
# (backend-v2 api/deps.py CLIENT_HEADER); a known cookie needs none.
CLIENT_HEADER = "X-Marcus-Client"
POLL_S = 2.0
UI_SEGMENT_TIMEOUT_S = 300
UI_OCSR_TIMEOUT_S = 60
PAPER_TIMEOUT_S = 3600.0
# v1 engine names (run_goldset.py) -> v2 engine identifiers (marcus.core.enums.Engine); "fake" only works
# against a stack started with MARCUS_ENABLE_FAKE_ENGINES=1. v2 no longer runs MolNexTR (MolParser
# replaced it, 2026-11-25): the v1 name "molnextr" runs v2's "molparser" (same slot), so v1-vs-v2
# runs still pair up; "molparser" may also be named directly.
ENGINES = {"decimer": "decimer", "decimer-hand": "decimer-hand", "molnextr": "molparser",
           "molparser": "molparser", "molscribe": "molscribe", "fake": "fake"}
TERMINAL = {"done", "failed", "deleted"}
ACTIVE_STEP = ("pending", "queued", "running")

_ACTIVE: "weakref.WeakSet[httpx.Client]" = weakref.WeakSet()
_LIVE: dict[str, tuple[str, str]] = {}  # paper id -> (base_url, owner cookie) while run_paper waits for it
_CREATED: list[str] = []
_LIVE_LOCK = threading.Lock()
NON_PAGE_KINDS = ("check_pdf", "docling", "doi")
_REPO = Path(__file__).resolve().parents[2]


def abort_all() -> int:
    """Close every client opened by run_paper (same contract as client_v1.abort_all)."""
    return close_all(_ACTIVE)


def _register(pid: str, base_url: str, cookie: str | None) -> None:
    with _LIVE_LOCK:
        _LIVE[pid] = (base_url, cookie)
        _CREATED.append(pid)


def _unregister(pid: str | None) -> None:
    with _LIVE_LOCK:
        _LIVE.pop(pid, None)


def live_papers() -> dict:
    """Papers uploaded by run_paper whose run has not ended (id -> (base_url, cookie))."""
    with _LIVE_LOCK:
        return dict(_LIVE)


def created_papers(clear: bool = False) -> list[str]:
    """Every paper id run_paper uploaded (``clear`` empties the list)."""
    with _LIVE_LOCK:
        out = list(_CREATED)
        if clear:
            _CREATED.clear()
    return out


def _delete_paper(pid: str, base_url: str, cookie: str | None) -> bool:
    """DELETE /papers/{id} as its owner (best effort, own short-lived client: the run's client may be closed)."""
    try:
        with httpx.Client(base_url=base_url, timeout=httpx.Timeout(15.0),
                          headers={"Cookie": f"{OWNER_COOKIE}={cookie}"} if cookie else {}) as c:
            r = c.request("DELETE", f"{API}/papers/{pid}")
            return r.status_code < 400 or r.status_code == 404  # 404: already gone
    except Exception:
        return False


def cancel_papers() -> list[str]:
    """Delete every live paper as its owner (a guard trip: stop the server-side work). Returns the ids sent."""
    with _LIVE_LOCK:
        items = list(_LIVE.items())
        _LIVE.clear()
    for pid, (base_url, cookie) in items:
        _delete_paper(pid, base_url, cookie)
    return [pid for pid, _ in items]


def git_short_hash() -> str:
    """The judges' git hash (the build label of v2 run lines). JUDGE_V2_BUILD overrides it where the judges run from
    a copy without git (jarvis, Task D4: the label was "v2-unknown")."""
    if os.environ.get("JUDGE_V2_BUILD"):
        return os.environ["JUDGE_V2_BUILD"]
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


def _ts(v) -> float | None:
    """ISO-8601 timestamp from the API -> epoch seconds."""
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


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
    pdf_sha, up_name, data, up_sha = prepare_upload(
        pdf_path, paper_id, reuse_upload=reuse_upload, unique_bytes=unique_bytes
    )

    started_at = now_iso()
    t0 = time.perf_counter()
    deadline = t0 + paper_timeout_s
    log: list[dict] = []
    http = {"n": 0, "by": {}}
    rate_events: list[dict] = []
    rec: dict = {
        "paper_id": paper_id, "pdf_sha256": pdf_sha, "engine": engine, "build": f"v2-{git_short_hash()}",
        "started_at": started_at, "wall_ms": None, "segment_ms": None, "segment_compute_ms": None, "ocsr_cache_hits": 0,
        "first_segment_start_ms": None, "first_smiles_ms": None, "ocsr_done_ms": None,
        "pages_total": count_pdf_pages(pdf_path), "pages_with_segments": 0,
        "page_errors": [], "segments": [],
        "client": "client_v2", "base_url": base_url, "tag": tag, "upload_name": up_name, "upload_sha256": up_sha,
        "ui_extras": False, "on_429": "retry", "segments_reported": None, "segments_listed": None,
        "segments_already_existed": None, "timings_ms": {}, "http_calls": 0, "http_calls_by_step": {},
        "rate_limit_events": [], "server_segment_s": [], "log_keywords": {}, "fatal_error": None,
        "aborted": False, "max_segments": max_segments, "backend_crash": None, "no_segments": False,
        "v2_engine": v2_engine, "v2_paper_id": None, "events_mode": None, "events_seen": 0,
        "page_errors_source": "GET /papers/{id}/steps (failed render_page/segment_page steps)",
        "failed_steps": [], "cancelled": False,
    }

    client = no_keepalive_client(
        base_url, max_connections=4, timeout=httpx.Timeout(connect=15.0, read=60.0, write=120.0, pool=30.0),
        headers={CLIENT_HEADER: "judge"},
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
                ra = retry_after_s(r)
                rate_events.append({"step": step, "t_ms": round((ts - t0) * 1000, 1), "wait_s": ra, "attempt": attempts + 1})
                attempts += 1
                sleep_abortable(ra, check_abort)
                continue
            r.raise_for_status()
            _keep_owner_cookie(client, r)
            return r

    def get_paper(pid) -> dict:
        return call("paper", "GET", f"{API}/papers/{pid}").json()

    seen = {"events": 0}
    ocsr_started: dict[str, float] = {}

    def on_step(ev: dict):
        """Progress only: counts events and reports each finished ocsr step to ``on_event``."""
        if ev.get("type") != "step":
            return
        seen["events"] += 1
        if ev.get("kind") != "ocsr":
            return
        key = ev.get("step_id") or ""
        if ev.get("status") == "running":
            ocsr_started.setdefault(key, time.perf_counter())
        elif on_event and ev.get("status") in ("done", "failed"):
            t = ocsr_started.get(key)
            on_event({"event": "segment", "i": None, "of": None,
                      "ms": round((time.perf_counter() - t) * 1000, 1) if t else None,
                      "error": "failed" if ev["status"] == "failed" else None})

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
    step_rows: list[dict] = []
    upload_ms = None
    pid = None
    try:
        check_abort()
        t_up = time.perf_counter()
        up = call("upload", "POST", f"{API}/papers", files={"file": (up_name, data, "application/pdf")},
                  data={"engine": v2_engine, "ocsr": "auto" if max_segments is None else "off"})
        upload_ms = (time.perf_counter() - t_up) * 1000
        rec["timings_ms"]["upload"] = round(upload_ms, 1)
        pid = up.json()["paper_id"]
        rec["v2_paper_id"] = pid
        cookie = client.headers.get("Cookie", "").partition("=")[2] or None
        _register(pid, base_url, cookie)

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
        if status != "deleted":
            try:
                step_rows = call("steps", "GET", f"{API}/papers/{pid}/steps").json()["steps"]
            except Aborted:
                raise
            except Exception as e:  # old backend without the endpoint: the record keeps None timings
                rec["steps_error"] = _err_text(e)
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
            pass  # best-effort close: the client may already be closed
        _ACTIVE.discard(client)
        if pid is not None:
            live = live_papers().get(pid)
            _unregister(pid)
            if rec["aborted"] and live is not None:  # stop the server-side pipeline (GPU work) of this paper
                rec["cancelled"] = _delete_paper(pid, *live)
            elif rec["aborted"]:
                rec["cancelled"] = True  # cancel_papers() (guard trip) already deleted it

    # ------------------------------------------------------------------ build the record
    segs_all = detail.get("segments") or []
    if detail.get("pages") is not None:
        rec["pages_total"] = detail["pages"]
    rec["segments_reported"] = rec["segments_listed"] = len(segs_all) if detail else None
    rec["listed_pages"] = sorted({s["page"] for s in segs_all})
    rec["pages_with_segments"] = len(rec["listed_pages"])
    rec["no_segments"] = bool(detail) and not segs_all and rec["fatal_error"] is None
    rec["events_seen"] = seen["events"]
    rec["steps_seen"] = len(step_rows)

    for st in step_rows:
        st["_start"], st["_end"] = _ts(st.get("started_at")), _ts(st.get("finished_at"))
    origin = min((t for t in (_ts(st.get("created_at")) for st in step_rows) if t), default=None)
    ocsr_by_seg: dict[str, dict] = {}
    for st in step_rows:  # ordered by created_at, seq: the last one of a segment is the newest
        if st["kind"] == "ocsr" and st.get("segment_id"):
            ocsr_by_seg[st["segment_id"]] = st
    rows = segs_all if max_segments is None else segs_all[:max_segments]
    hits = 0
    for seg in rows:
        pred = next((p for p in seg["predictions"] if p["engine"] == ENGINES[engine]), None)  # newest first
        st = ocsr_by_seg.get(seg["id"])
        wall = None
        if st:
            t_created, t_end = _ts(st.get("created_at")), st["_end"]
            if t_created is not None and t_end is not None:
                wall = round((t_end - t_created) * 1000, 1)
        error = None
        if pred is None and rec["fatal_error"] is None:
            error = "ocsr step failed" if st and st["status"] == "failed" else "no prediction"
            if st and st.get("error_class"):
                error += f" ({st['error_class']})"
        cached = (pred or {}).get("cached")
        hits += 1 if cached else 0
        row = {"segment_id": f"page_{seg['page']}_{seg['idx']}", "page": seg["page"], "page_number": seg["page"] + 1,
               "filename": None, "smiles": (pred or {}).get("smiles") or "",
               "ocsr_ms": wall, "ocsr_ms_source": "step created_at -> finished_at",
               "ocsr_compute_ms": (pred or {}).get("ms"), "ocsr_attempts": st.get("attempts") if st else None,
               "cached": cached, "error": error, "fallback": False,
               "t_start_ms": round((st["_start"] - origin) * 1000, 1) if st and st["_start"] and origin else None,
               "rate_limited": 0, "v2_segment_id": seg["id"], "valid": (pred or {}).get("valid"),
               "engine_version": (pred or {}).get("engine_version")}
        row["exceeds_ocsr_timeout"] = bool(wall and wall > ocsr_timeout_s * 1000)
        rec["segments"].append(row)
    rec["ocsr_cache_hits"] = hits

    seg_steps = [st for st in step_rows if st["kind"] == "segment_page"]
    starts = [st["_start"] for st in seg_steps if st["_start"]]
    ends = [st["_end"] for st in seg_steps if st["_end"]]
    if starts and ends:
        rec["segment_compute_ms"] = round((max(ends) - min(starts)) * 1000, 1)
        if origin is not None and upload_ms is not None:
            seg_ms = upload_ms + (max(ends) - origin) * 1000
            rec["segment_ms"] = round(seg_ms, 1)
            rec["exceeds_ui_segment_timeout"] = seg_ms > segment_timeout_s * 1000
    if origin is not None and upload_ms is not None:
        if starts:
            rec["first_segment_start_ms"] = round(upload_ms + (min(starts) - origin) * 1000, 1)
        smiles_ends = [st["_end"] for st in step_rows if st["kind"] == "ocsr" and st["status"] == "done" and st["_end"]]
        if smiles_ends:
            rec["first_smiles_ms"] = round(upload_ms + (min(smiles_ends) - origin) * 1000, 1)
        ocsr_ends = [st["_end"] for st in step_rows if st["kind"] == "ocsr" and st["_end"]]
        if ocsr_ends:
            rec["ocsr_done_ms"] = round(upload_ms + (max(ocsr_ends) - origin) * 1000, 1)
    rstarts = [st["_start"] for st in step_rows if st["kind"] == "render_page" and st["_start"]]
    rends = [st["_end"] for st in step_rows if st["kind"] == "render_page" and st["_end"]]
    if rstarts and rends:
        rec["timings_ms"]["render_pages"] = round((max(rends) - min(rstarts)) * 1000, 1)
    for st in step_rows:
        if st["kind"] in ("render_page", "segment_page") and st["status"] == "failed":
            ec = st.get("error_class")
            rec["page_errors"].append({"page": st["page"], "error": f"{st['kind']} failed" + (f": {ec}" if ec else ""),
                                       "kind": st["kind"], "error_class": ec})
    rec["page_errors"].sort(key=lambda e: (e["page"] is None, e["page"] or 0, e["kind"]))
    for st in step_rows:
        if st["kind"] in NON_PAGE_KINDS and (st["status"] == "failed" or st.get("error_class")):
            dur = round((st["_end"] - st["_start"]) * 1000, 1) if st["_start"] and st["_end"] else None
            rec["failed_steps"].append({"kind": st["kind"], "status": st["status"], "error_class": st.get("error_class"),
                                        "attempts": st.get("attempts"), "duration_ms": dur})

    rec["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    rec["http_calls"] = http["n"]
    rec["http_calls_by_step"] = http["by"]
    rec["rate_limit_events"] = rate_events
    if keep_http_log:
        rec["http_log"] = log
    return rec
