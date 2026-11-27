"""Helpers for the v2 security judge (no fixtures here; see conftest.py)."""
from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field

import httpx
from common.client_v2 import ACTIVE_STEP as BUSY_STEPS
from common.client_v2 import OWNER_COOKIE, TERMINAL
from fs_probe import DockerProbe, ProbeError
from payloads import minimal_pdf, minimal_png

API = "/api/v2"
HTTP_TIMEOUT_S = 120
PAPER_TIMEOUT_S = 300
# The data root inside the API container (MARCUS_DATA_ROOT in backend-v2/docker-compose.yml).
DATA_ROOT = "/data"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # global constraints: 20 MB + 1 byte gets 413


# --- owners --------------------------------------------------------------------------------


class V2Owner:
    """One caller. Keeps the `marcus_owner` cookie the server issues.

    The server marks the cookie Secure; httpx's cookie jar then never sends it over
    http://localhost, so the Set-Cookie value is read here and sent as a Cookie header (the
    same workaround as judges/common/client_v2.py). `anonymous=True` never sends a cookie, so
    every request is a brand-new caller.
    """

    def __init__(self, base: str, *, api_key: str | None = None, anonymous: bool = False):
        self.anonymous = anonymous
        self.cookie: str | None = None
        self.set_cookie_headers: list[str] = []
        # the client header a new browser owner needs (backend-v2 api/deps.py CLIENT_HEADER)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {"X-Marcus-Client": "judge"}
        self.http = httpx.Client(
            base_url=base,
            timeout=HTTP_TIMEOUT_S,
            headers=headers,
            event_hooks={"response": [self._keep_cookie]},
        )

    def _keep_cookie(self, resp: httpx.Response) -> None:
        for sc in resp.headers.get_list("set-cookie"):
            m = re.match(rf"\s*{OWNER_COOKIE}=([^;]*)", sc)
            if m:
                self.set_cookie_headers.append(sc)
                if not self.anonymous:
                    self.cookie = m.group(1)
                    self.http.headers["Cookie"] = f"{OWNER_COOKIE}={self.cookie}"

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        return self.http.request(method, path, **kw)

    def get(self, path, **kw):
        return self.http.get(path, **kw)

    def post(self, path, **kw):
        return self.http.post(path, **kw)

    def put(self, path, **kw):
        return self.http.put(path, **kw)

    def delete(self, path, **kw):
        return self.http.delete(path, **kw)

    def raw_get(self, raw_path: str) -> httpx.Response:
        """GET with the path sent byte for byte (no dot-segment or %-normalising by httpx)."""
        req = self.http.build_request("GET", "/")
        req.url = req.url.copy_with(raw_path=raw_path.encode())
        return self.http.send(req)

    def close(self):
        self.http.close()


# --- existence check and comparisons -------------------------------------------------------


def expect_ok(resp: httpx.Response, what: str) -> httpx.Response:
    """The existence check: a valid request to the v2 route must get a 2xx, so a missing route
    (404/405) fails the test instead of letting its attack half pass vacuously."""
    assert 200 <= resp.status_code < 300, (
        f"EXISTENCE CHECK FAILED for {what}: {resp.request.method} {resp.request.url.path} "
        f"-> HTTP {resp.status_code} {resp.text[:300]!r}. The v2 route is missing or broken, "
        "so the attack would prove nothing."
    )
    return resp


def same_answer(a: httpx.Response, b: httpx.Response) -> bool:
    return a.status_code == b.status_code and a.content == b.content


def describe(resp: httpx.Response) -> str:
    return f"HTTP {resp.status_code} {resp.text[:160]!r}"


def random_id() -> str:
    return str(uuid.uuid4())


# --- uploads and waiting -------------------------------------------------------------------


def judge_pdf(*lines: str) -> bytes:
    return minimal_pdf(list(lines) or ["MARCUS security judge (v2)."])


def judge_png(size: int = 64) -> bytes:
    return minimal_png(size)


# The upload limiter fails CLOSED while its circuit breaker is open: 3 failed Redis calls (error, or
# slower than rate_limit_redis_timeout_s, default 1.0 s) within 5 s open it, and then every upload
# gets 503 {"detail": "service unavailable"} for 5 s (marcus.api.security). That is an availability
# answer, not a security result, so an upload is retried after the breaker window.
BREAKER_RETRY_S = 6.0
BREAKER_RETRIES = 2


def _upload(owner: V2Owner, path: str, **kw) -> httpx.Response:
    for _ in range(BREAKER_RETRIES):
        resp = owner.post(path, **kw)
        if not (resp.status_code == 503 and resp.content == b'{"detail":"service unavailable"}'):
            return resp
        time.sleep(BREAKER_RETRY_S)
    return owner.post(path, **kw)


def post_paper(owner: V2Owner, *, filename="judge.pdf", data: bytes | None = None,
               engine="fake", ocsr="auto") -> httpx.Response:
    return _upload(
        owner,
        f"{API}/papers",
        files={"file": (filename, data if data is not None else judge_pdf(), "application/pdf")},
        data={"engine": engine, "ocsr": ocsr},
    )


def upload_paper(owner: V2Owner, *, what="POST /api/v2/papers", **kw) -> str:
    resp = expect_ok(post_paper(owner, **kw), what)
    return resp.json()["paper_id"]


def post_image(owner: V2Owner, *, filename="judge.png", data: bytes | None = None,
               engine="fake", extra: dict | None = None) -> httpx.Response:
    return _upload(
        owner,
        f"{API}/images",
        files={"file": (filename, data if data is not None else judge_png(), "image/png")},
        data={"engine": engine, **(extra or {})},
    )


def upload_image(owner: V2Owner, *, what="POST /api/v2/images", **kw) -> str:
    resp = expect_ok(post_image(owner, **kw), what)
    return resp.json()["image_job_id"]


def wait_paper(owner: V2Owner, paper_id: str, timeout_s: float = PAPER_TIMEOUT_S) -> dict:
    """Poll GET /papers/{id} until the paper is terminal and no step is still waiting or
    running (an OCSR request after `done` keeps steps busy). Returns the detail."""
    deadline = time.monotonic() + timeout_s
    detail: dict = {}
    while time.monotonic() < deadline:
        resp = expect_ok(owner.get(f"{API}/papers/{paper_id}"), "GET /api/v2/papers/{id}")
        detail = resp.json()
        busy = {k: v for k, v in detail["counts"]["steps_by_status"].items() if k in BUSY_STEPS}
        if detail["status"] in TERMINAL and not busy:
            return detail
        time.sleep(1)
    raise AssertionError(f"paper {paper_id} not finished within {timeout_s}s: {detail}")


def wait_image(owner: V2Owner, job_id: str, timeout_s: float = 120) -> dict:
    deadline = time.monotonic() + timeout_s
    body: dict = {}
    while time.monotonic() < deadline:
        body = expect_ok(owner.get(f"{API}/images/{job_id}"), "GET /api/v2/images/{id}").json()
        if body["status"] not in ("queued", "processing"):
            return body
        time.sleep(0.5)
    raise AssertionError(f"image job {job_id} not finished within {timeout_s}s: {body}")


@dataclass
class SharedPaper:
    owner: V2Owner
    paper_id: str
    detail: dict
    segment_ids: list[str] = field(default_factory=list)


# --- filesystem probe helpers --------------------------------------------------------------


def docker_probe(fs_probe) -> DockerProbe:
    if not isinstance(fs_probe, DockerProbe):
        raise ProbeError("this check needs MARCUS_FS_PROBE=docker:<v2 api container>")
    return fs_probe


def find_names(fs_probe, token: str, dirs=("/tmp", DATA_ROOT)) -> list[str]:
    """Every file or directory under `dirs` (recursive) whose name contains `token`."""
    probe = docker_probe(fs_probe)
    r = subprocess.run(
        ["docker", "exec", probe.container, "find", *dirs, "-name", f"*{token}*"],
        capture_output=True, text=True,
    )
    if r.returncode not in (0, 1) or "No such file" in r.stderr:
        raise ProbeError(f"find in {probe.container} failed: {r.stderr.strip()}")
    return [line for line in r.stdout.splitlines() if line.strip()]


def effective_settings(fs_probe, *names: str) -> dict:
    """The API's effective settings (a stack may raise limits, e.g. docker-compose.fake.yml)."""
    probe = docker_probe(fs_probe)
    code = (
        "import json; from marcus.core.settings import get_settings as g; s = g(); "
        f"print(json.dumps({{n: getattr(s, n) for n in {list(names)!r}}}))"
    )
    r = subprocess.run(
        ["docker", "exec", probe.container, "python", "-c", code],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise ProbeError(f"could not read settings in {probe.container}: {r.stderr.strip()}")
    return json.loads(r.stdout)


# --- straight to the API, behind nginx -----------------------------------------------------

_DIRECT = r'''
import base64, http.client, json, sys
req = json.loads(sys.stdin.read())
out = []
for path in req["paths"]:
    c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=30)
    c.request("GET", path, headers=req["headers"])
    r = c.getresponse()
    out.append({"status": r.status, "ctype": r.getheader("content-type") or "",
                "body": base64.b64encode(r.read()).decode()})
    c.close()
print(json.dumps(out))
'''


@dataclass
class DirectResponse:
    status_code: int
    content_type: str
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode(errors="replace")


def direct_get_many(fs_probe, raw_paths: list[str], cookie: str | None = None) -> list:
    """GET each raw path (sent byte for byte) straight to the API inside its own container
    (127.0.0.1:8000), so nginx's own URI normalising cannot be what stops an attack."""
    import base64

    probe = docker_probe(fs_probe)
    headers = {"Cookie": f"{OWNER_COOKIE}={cookie}"} if cookie else {}
    r = subprocess.run(
        ["docker", "exec", "-i", probe.container, "python", "-c", _DIRECT],
        input=json.dumps({"paths": raw_paths, "headers": headers}),
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise ProbeError(f"direct API request in {probe.container} failed: {r.stderr[-500:]}")
    return [DirectResponse(d["status"], d["ctype"], base64.b64decode(d["body"]))
            for d in json.loads(r.stdout)]


# --- spoofed-header burst straight to the API ----------------------------------------------

_BURST = r'''
import http.client, json, random, socket, sys, threading, time
req = json.loads(sys.stdin.read())
host = req["host"] or socket.gethostbyname(socket.gethostname())
n, threads = req["n"], req["threads"]
lock = threading.Lock(); stop = threading.Event()
state = {"sent": 0, "first_429": None, "codes": {}}
def ip():
    return ".".join(str(random.randint(1, 254)) for _ in range(4))
def work(k):
    c = http.client.HTTPConnection(host, 8000, timeout=30)
    for _ in range(k):
        if stop.is_set(): return
        a = ip()
        c.request("GET", req["path"], headers={"X-Forwarded-For": f"{a}, {ip()}", "X-Real-IP": a,
                  "CF-Connecting-IP": a, "True-Client-IP": a, "Forwarded": f"for={a}"})
        r = c.getresponse(); body = r.read()
        with lock:
            state["sent"] += 1
            state["codes"][r.status] = state["codes"].get(r.status, 0) + 1
            if r.status == 429 and state["first_429"] is None:
                state["first_429"] = {"at": state["sent"], "body": body.decode(),
                                      "window": int(time.time()) // 60}
                stop.set()
ts = [threading.Thread(target=work, args=(n // threads + 1,)) for _ in range(threads)]
w0 = int(time.time()) // 60
for t in ts: t.start()
for t in ts: t.join()
state["host"] = host; state["window_start"] = w0; state["window_end"] = int(time.time()) // 60
print(json.dumps(state))
'''


def direct_burst(fs_probe, path: str, n: int, threads: int = 8) -> dict:
    """Send up to `n` GETs of `path` straight to the API from inside its container, each with a
    different spoofed X-Forwarded-For / X-Real-IP / CF-Connecting-IP / True-Client-IP /
    Forwarded; stop at the first 429. Returns {"sent", "first_429": {"at", "body", "window"} or
    None, "codes", "host", "window_start", "window_end"}.

    The request goes to the container's own network address, not 127.0.0.1: before R19 was
    fixed gunicorn ran with --forwarded-allow-ips=127.0.0.1, so uvicorn rewrote a loopback peer
    from X-Forwarded-For before the app saw it (now --forwarded-allow-ips=, no rewrite). From the
    container's own address the peer is an ordinary untrusted client, which is what an attacker
    reaching the API without nginx would be.
    """
    probe = docker_probe(fs_probe)
    r = subprocess.run(
        ["docker", "exec", "-i", probe.container, "python", "-c", _BURST],
        input=json.dumps({"host": None, "n": n, "threads": threads, "path": path}),
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise ProbeError(f"direct burst in {probe.container} failed: {r.stderr[-500:]}")
    return json.loads(r.stdout)


# --- the API's real route table ------------------------------------------------------------

_ROUTES = r'''
import json
from marcus.api.deps import current_owner
from marcus.api.main import create_app

def calls(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from calls(d)

out = []
def walk(routes):
    for r in routes:
        if hasattr(r, "effective_route_contexts"):  # FastAPI's lazily included router
            walk(list(r.effective_route_contexts()))
        elif hasattr(r, "methods") and hasattr(r, "dependant"):
            owner = any(c is current_owner for c in calls(r.dependant))
            out.extend([m, r.path, owner] for m in sorted(r.methods) if m != "HEAD")
        else:  # a mount, a plain Starlette route, a websocket: always reported
            out.append([type(r).__name__, getattr(r, "path", repr(r)), False])
walk(create_app().routes)
print(json.dumps(out))
'''


def route_table(fs_probe) -> list[tuple[str, str, bool]]:
    """(method, path, depends on current_owner) for every route of the API as the running
    container builds it (same code and environment as the served app)."""
    probe = docker_probe(fs_probe)
    r = subprocess.run(
        ["docker", "exec", probe.container, "python", "-c", _ROUTES],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise ProbeError(f"could not list routes in {probe.container}: {r.stderr[-500:]}")
    return [tuple(x) for x in json.loads(r.stdout)]
