"""The load scenarios' calls in their v2 form (``scenarios.py --client v2``).

``scenarios.py`` talks to the backend through one small interface: ``V1Api`` (v1, in scenarios.py) or this
module (v2). Same names, same signatures, same return values, so the scenario code is the same for both builds.
Papers go through ``common/client_v2.run_paper`` (no second v2 client here); this module only adds the calls
around a paper: health, the owner (v1: session), the script user's single image, the depict tool.

v1 call (scenarios.py)                    v2 form (this module)
----------------------------------------  -------------------------------------------------------------------
GET  /health                              GET /api/v2/health (no DB, exempt from the per-IP limit)
POST /session/create                      an owner cookie: GET /api/v2/papers without a cookie makes a new
                                          browser owner (Set-Cookie marcus_owner, Secure; sent by hand)
POST /session/heartbeat/{sid}             GET /api/v2/papers with the owner's cookie (owner lookup + DB read)
DELETE /session/remove/{sid}              nothing (v2 has no sessions; an owner's papers expire)
POST /latest/ocsr/generate_smiles         POST /api/v2/images (file + engine) -> 202 {image_job_id}, then
                                          GET /api/v2/images/{id} every POLL_S until done | failed
client_v1.run_paper (extract_segments,    client_v2.run_paper: POST /api/v2/papers + GET .../events (SSE) +
list_directory, generate_with_depiction)  GET /papers/{id} + GET /papers/{id}/steps (timings, page errors)
remote.parse_server_log (docker logs)     page_errors of the records (failed render_page / segment_page steps)
(new, v2 only) depiction during load      POST /api/v2/tools/depict (spec §3 Responsive: p95 < 2 s)

Owner limits: a browser owner may hold 3 active papers or image jobs and make 10 uploads per minute. client_v2
starts each paper with a new owner (as separate users would). The script user (S5) makes about 12 uploads per
minute, so it moves to a new owner before its 10th upload of an owner (``uploads_per_owner``): v1's script user
had its own rate-limit bucket for the same reason (latency, not the rate limiter, is measured). The per-IP
limits (10 new owners per hour, 6 active papers) are raised on the fake stack and must be raised for D4 too.

Every answer >= 400 is kept (``http_events``) with its ``detail``; ``breaker_503_count`` counts the
``503 {"detail": "service unavailable"}`` answers of the rate limiter's open circuit breaker.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import client_v2, target  # noqa: E402

API = client_v2.API
POLL_S = 0.25  # image job polling; GET /images/{id} counts against the per-IP limit (300/min outside the fake stack)
UPLOADS_PER_OWNER = 9  # the v2 per-owner upload limit is 10 per minute
DEPICT_SMILES = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"

run_paper = client_v2.run_paper
abort_all = client_v2.abort_all
BUILD = f"v2-{client_v2.git_short_hash()}"

V1_TO_V2 = {
    "/health": {"v1": "GET /health", "v2": "GET /api/v2/health", "adapter": "health_call"},
    "/session/create": {"v1": "POST /session/create",
                        "v2": "GET /api/v2/papers without a cookie -> new browser owner (Set-Cookie marcus_owner)",
                        "adapter": "create_session"},
    "/session/heartbeat": {"v1": "POST /session/heartbeat/{sid}", "v2": "GET /api/v2/papers with the owner cookie",
                           "adapter": "heartbeat_call"},
    "/session/remove": {"v1": "DELETE /session/remove/{sid}", "v2": "none (no sessions in v2)",
                        "adapter": "remove_session"},
    "/latest/ocsr/generate_smiles": {"v1": "POST /latest/ocsr/generate_smiles (multipart image_file, engine)",
                                     "v2": "POST /api/v2/images (multipart file, engine) + GET /api/v2/images/{id}",
                                     "adapter": "script_call"},
    "run_paper": {"v1": "client_v1.run_paper: extract_segments + list_directory + generate_with_depiction x N",
                  "v2": "client_v2.run_paper: POST /api/v2/papers + SSE events + GET /papers/{id} + /steps",
                  "adapter": "run_paper"},
    "parse_server_log": {"v1": "backend docker logs: 'Error processing page N'",
                         "v2": "failed render_page / segment_page steps in each record's page_errors",
                         "adapter": "page_errors_of"},
}

_events: list[dict] = []
_events_lock = threading.Lock()


def http_events(clear: bool = False) -> list[dict]:
    """Every answer >= 400 the adapter saw (path, status, detail, time); ``clear`` empties the list."""
    with _events_lock:
        out = list(_events)
        if clear:
            _events.clear()
    return out


def breaker_503_count(events) -> int:
    return sum(1 for e in events if e.get("status") == 503 and e.get("detail") == "service unavailable")


def _note(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        detail = r.json().get("detail")
    except Exception:
        detail = r.text[:200]
    with _events_lock:
        _events.append({"t": time.time(), "method": r.request.method, "path": r.request.url.path,
                        "status": r.status_code, "detail": detail if isinstance(detail, str) else str(detail)[:200]})


def _client(base_url: str) -> httpx.Client:
    # no keep-alive, as client_v1/client_v2 (and the nginx in front of production) do
    return httpx.Client(base_url=target._check(base_url), limits=httpx.Limits(max_keepalive_connections=0))


class Owner:
    """One browser owner: an httpx client that carries its cookie. ``renew`` drops the cookie, so the next request
    makes a new owner. Thread-safe: open-loop probes share it."""

    def __init__(self, base_url: str, uploads_per_owner: int = UPLOADS_PER_OWNER):
        self.base_url = base_url
        self.uploads_per_owner = uploads_per_owner
        self.uploads = 0
        self.owners_used = 0
        self._lock = threading.Lock()
        self.client = _client(base_url)

    @property
    def cookie(self) -> str | None:
        c = self.client.headers.get("Cookie")
        return c.split("=", 1)[1] if c else None

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        had = self.cookie
        r = self.client.request(method, path, **kw)
        client_v2._keep_owner_cookie(self.client, r)
        if had is None and self.cookie is not None:
            with self._lock:
                self.owners_used += 1
        _note(r)
        return r

    def before_upload(self) -> None:
        with self._lock:
            if self.uploads >= self.uploads_per_owner:
                old, self.client = self.client, _client(self.base_url)
                self.uploads = 0
                try:
                    old.close()
                except Exception:
                    pass
            self.uploads += 1

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass


# ------------------------------------------------------------------ the V1Api interface, v2 form
def server_ok(base_url: str, timeout=30) -> bool:
    c = _client(base_url)
    try:
        return c.get(f"{API}/health", timeout=timeout).status_code == 200
    except Exception:
        return False
    finally:
        c.close()


def create_session(base_url: str, uploads_per_owner: int = UPLOADS_PER_OWNER) -> Owner | None:
    """v1: POST /session/create. v2: a new browser owner (its cookie comes with the first answer)."""
    owner = Owner(base_url, uploads_per_owner)
    try:
        owner.request("GET", f"{API}/papers", timeout=30)
    except httpx.HTTPError:
        return None
    return owner if owner.cookie else None


def remove_session(base_url: str, sid) -> None:
    """v2 has no sessions; only the local client is closed."""
    if isinstance(sid, Owner):
        sid.close()


def health_call(base_url):
    c = _client(base_url)

    def call(timeout):
        r = c.get(f"{API}/health", timeout=timeout)
        _note(r)
        return r.status_code

    return call


def heartbeat_call(base_url, sid):
    owner = sid if isinstance(sid, Owner) else Owner(base_url)

    def call(timeout):
        return owner.request("GET", f"{API}/papers", timeout=timeout).status_code

    return call


def _image_job(owner: Owner, png: bytes, engine: str, timeout: float):
    """POST /images, then poll GET /images/{id}. Returns 200 when done, the HTTP status of a refused call,
    'job_failed' / 'job_deleted', or 'timeout'."""
    deadline = time.perf_counter() + timeout
    owner.before_upload()
    r = owner.request("POST", f"{API}/images", files={"file": ("probe.png", png, "image/png")},
                      data={"engine": client_v2.ENGINES.get(engine, engine)}, timeout=timeout)
    if r.status_code != 202:
        return r.status_code
    jid = r.json()["image_job_id"]
    while True:
        left = deadline - time.perf_counter()
        if left <= 0:
            return "timeout"
        g = owner.request("GET", f"{API}/images/{jid}", timeout=max(1.0, left))
        if g.status_code != 200:
            return g.status_code
        st = g.json().get("status")
        if st == "done":
            return 200
        if st in ("failed", "deleted"):
            return f"job_{st}"
        time.sleep(POLL_S)


def script_call(base_url, sid, png, engine="decimer"):
    """v1: generate_smiles with an uploaded PNG. v2: one image job, submit to result (queue wait included)."""
    owner = sid if isinstance(sid, Owner) else Owner(base_url)

    def call(timeout):
        return _image_job(owner, png, engine, timeout)

    return call


def warmup(base_url, sid, png, engine, timeout=1200) -> dict:
    """S1's first call of an engine (v1 loaded weights on it; v2 workers preload, so this shows the queue path)."""
    owner = sid if isinstance(sid, Owner) else Owner(base_url)
    ts = time.perf_counter()
    try:
        status = _image_job(owner, png, engine, timeout)
        return {"ms": round((time.perf_counter() - ts) * 1000, 1), "status": status}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


def depict_call(base_url, sid):
    """POST /api/v2/tools/depict (60 calls per owner per minute: probe at most once a second)."""
    owner = sid if isinstance(sid, Owner) else Owner(base_url)

    def call(timeout):
        return owner.request("POST", f"{API}/tools/depict", json={"smiles": DEPICT_SMILES, "format": "svg"},
                             timeout=timeout).status_code

    return call


def page_errors_of(recs) -> list[dict]:
    """v1 read page errors from the backend's docker log; v2 has them per paper (failed page steps)."""
    out = []
    for k, rec in enumerate(recs):
        for e in (rec or {}).get("page_errors") or []:
            out.append({**e, "paper": k})
    return out


def logsrc(base_url):
    return None  # no docker-log source: page errors come from the records
