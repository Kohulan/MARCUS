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

Cold OCSR cache (controller ruling R21). v2 caches OCSR by (sha256 of the crop or image, engine, engine version) for
every real engine, image jobs included, so a repeated fixture or probe image would be served in about 0 ms.
  * ``CacheClear`` empties the cache table on the TEST stack's Postgres between scenarios, arms and repeats:
    ``docker exec <container> psql -U marcus -d marcus -c 'DELETE FROM ocsr_cache'`` (the fs-probe's ``docker exec``
    path; ``DOCKER_HOST`` reaches a remote docker). It refuses production and non-test container names.
  * each script/warm-up image gets a few near-white corner pixels changed per call, so no two calls share bytes;
  * every image job records its engine ``ms`` (0 = a cache hit; the image API has no ``cached`` flag).

Guard trip (``abandon_all``): no new image job is posted and every poll loop returns ``"aborted"`` at once; the open
image jobs are listed (v2 has no DELETE for an image job: one OCSR step each, abandoned). Papers are deleted by
``client_v2.cancel_papers``.
"""
from __future__ import annotations

import io
import os
import re
import socket
import subprocess
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

OCSR_CACHE_TABLE = "ocsr_cache"  # backend-v2 marcus.core.models.OcsrCache.__tablename__ (tested)
PG_USER = PG_DB = "marcus"  # backend-v2 docker-compose.yml POSTGRES_USER / POSTGRES_DB
_REFUSED_CONTAINER_PARTS = ("marcus-backend", "marcus-frontend", "judge", "prod")
TEST_PROJECT_PREFIX = "marcus-v2-test"  # the only project whose Postgres may be cleared on jarvis or a remote docker
_LOCAL_DOCKER_SCHEMES = ("unix://", "npipe://")
_JARVIS_HOST = re.compile(r"(^|[/@.])jarvis([.:/]|$)|uni-jena\.de", re.IGNORECASE)


def docker_host() -> str:
    """Where `docker exec` goes: DOCKER_HOST if set, else the current docker context's endpoint
    (`docker context inspect` honours DOCKER_CONTEXT). '' when it cannot be found out."""
    host = os.environ.get("DOCKER_HOST", "").strip()
    if host:
        return host
    try:
        p = subprocess.run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (p.stdout or "").strip() if p.returncode == 0 else ""


def docker_daemon_name() -> str:
    """The host name the docker daemon reports (`docker info`, same DOCKER_HOST / context as `docker exec`).
    '' when it cannot be found out."""
    try:
        p = subprocess.run(["docker", "info", "--format", "{{.Name}}"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (p.stdout or "").strip() if p.returncode == 0 else ""


def _docker_host_refusal() -> str | None:
    """Why a container without the test prefix may not be cleared on this docker host (None = local).

    Local means both: a local socket endpoint, and a daemon that reports this machine's host name. The second
    check catches a unix socket that is really a forwarded remote docker (`ssh -L /tmp/x.sock:/var/run/docker.sock`).
    Limit: a remote daemon whose host name equals this machine's would still count as local."""
    host = docker_host()
    only = f"only the {TEST_PROJECT_PREFIX} project's Postgres may be cleared"
    if _JARVIS_HOST.search(host):
        return f"the docker host {host!r} is jarvis: {only}"
    if not host.startswith(_LOCAL_DOCKER_SCHEMES):  # tcp://, ssh://, or unknown ('') count as remote
        return f"the docker host {host or '(unknown)'!r} is remote (or unknown): {only} there"
    daemon, me = docker_daemon_name(), socket.gethostname()
    if _JARVIS_HOST.search(daemon):
        return f"the docker daemon behind {host!r} is jarvis ({daemon!r}): {only}"
    if daemon != me:
        return (f"the docker daemon behind {host!r} reports host {daemon or '(unknown)'!r}, not this machine "
                f"({me!r}), so it is remote (or unknown): {only} there")
    return None

_events: list[dict] = []
_events_lock = threading.Lock()
_STOP = threading.Event()  # set by abandon_all (guard trip)
_jobs_lock = threading.Lock()
_OPEN_JOBS: set[str] = set()
_CREATED_JOBS: list[str] = []


class CacheClear:
    """Empty the v2 OCSR cache on a TEST stack (R21). Refuses production and anything that is not a test Postgres.

    A container without the marcus-v2-test prefix is refused on `--target jarvis` and whenever `docker exec` would
    reach a remote docker (DOCKER_HOST or the docker context not a local socket, or not known), jarvis above all.
    """

    def __init__(self, container: str, target_name: str):
        name = container or ""
        low = name.lower()
        why = None
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            why = "not a plain container name"
        elif any(x in low for x in _REFUSED_CONTAINER_PARTS) or low.endswith(".uni-jena.de") or "decimer.ai" in low:
            why = "a production (or v1 judge) container"
        elif "postgres" not in low:
            why = "not a Postgres container"
        elif not low.startswith(TEST_PROJECT_PREFIX):
            if target_name == "jarvis":
                why = "on jarvis only the marcus-v2-test project's Postgres may be cleared (marcus-v2 is production after the switch)"
            else:
                why = _docker_host_refusal()
        if why:
            raise SystemExit(f"Refusing to clear the OCSR cache in container {name!r}: {why}.")
        self.container, self.target_name = name, target_name
        self.log: list[dict] = []

    def argv(self) -> list[str]:
        return ["docker", "exec", self.container, "psql", "-U", PG_USER, "-d", PG_DB, "-v", "ON_ERROR_STOP=1",
                "-c", f"DELETE FROM {OCSR_CACHE_TABLE}"]

    def clear(self, label: str) -> int:
        p = subprocess.run(self.argv(), capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(f"OCSR cache clear failed in {self.container!r}: {(p.stderr or p.stdout).strip()[:300]}")
        m = re.search(r"DELETE (\d+)", p.stdout or "")
        n = int(m.group(1)) if m else 0
        self.log.append({"label": label, "deleted": n, "t": time.time()})
        return n


def abandon_all() -> dict:
    """Guard trip: stop posting image jobs and polling at once; returns the image jobs left open (abandoned)."""
    _STOP.set()
    with _jobs_lock:
        return {"image_jobs": sorted(_OPEN_JOBS)}


def reset_abandon() -> None:
    _STOP.clear()
    with _jobs_lock:
        _OPEN_JOBS.clear()


def created_image_jobs(clear: bool = False) -> list[str]:
    with _jobs_lock:
        out = list(_CREATED_JOBS)
        if clear:
            _CREATED_JOBS.clear()
    return out


def image_job_cache_hits(owner) -> int:
    return sum(1 for j in getattr(owner, "jobs", []) if j.get("cache_hit"))


def unique_image(png: bytes) -> bytes:
    """The same picture with 4 near-white corner pixels set from random bytes: different sha256, same molecule
    (values 249-254 on a white background). Bytes that are not an image are returned unchanged."""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:
        return png
    r = os.urandom(12)
    for i in range(4):
        im.putpixel((i, 0), tuple(249 + (r[3 * i + k] % 6) for k in range(3)))
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


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
        self.jobs: list[dict] = []  # one entry per finished image job: id, status, engine ms, cache_hit
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
    if _STOP.is_set():
        return "aborted"
    deadline = time.perf_counter() + timeout
    owner.before_upload()
    r = owner.request("POST", f"{API}/images", files={"file": ("probe.png", unique_image(png), "image/png")},
                      data={"engine": client_v2.ENGINES.get(engine, engine)}, timeout=timeout)
    if r.status_code != 202:
        return r.status_code
    jid = r.json()["image_job_id"]
    with _jobs_lock:
        _OPEN_JOBS.add(jid)
        _CREATED_JOBS.append(jid)
    try:
        while True:
            if _STOP.is_set():
                return "aborted"  # stays in _OPEN_JOBS: abandoned
            left = deadline - time.perf_counter()
            if left <= 0:
                return "timeout"
            g = owner.request("GET", f"{API}/images/{jid}", timeout=max(1.0, left))
            if g.status_code != 200:
                return g.status_code
            d = g.json()
            st = d.get("status")
            if st in ("done", "failed", "deleted"):
                ms = (d.get("prediction") or {}).get("ms")
                with owner._lock:
                    owner.jobs.append({"image_job_id": jid, "status": st, "ms": ms, "cache_hit": ms == 0})
                with _jobs_lock:
                    _OPEN_JOBS.discard(jid)
                return 200 if st == "done" else f"job_{st}"
            _STOP.wait(POLL_S)
    except Exception:
        with _jobs_lock:
            _OPEN_JOBS.discard(jid)
        raise


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
