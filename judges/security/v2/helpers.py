"""Helpers for the v2 security judge (no fixtures here; see conftest.py)."""
from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field

import httpx
from fs_probe import DockerProbe, ProbeError
from payloads import minimal_pdf, minimal_png

API = "/api/v2"
OWNER_COOKIE = "marcus_owner"
HTTP_TIMEOUT_S = 120
PAPER_TIMEOUT_S = 300
TERMINAL = {"done", "failed", "deleted"}
BUSY_STEPS = ("pending", "queued", "running")
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
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
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


def post_paper(owner: V2Owner, *, filename="judge.pdf", data: bytes | None = None,
               engine="fake", ocsr="auto") -> httpx.Response:
    return owner.post(
        f"{API}/papers",
        files={"file": (filename, data if data is not None else judge_pdf(), "application/pdf")},
        data={"engine": engine, "ocsr": ocsr},
    )


def upload_paper(owner: V2Owner, *, what="POST /api/v2/papers", **kw) -> str:
    resp = expect_ok(post_paper(owner, **kw), what)
    return resp.json()["paper_id"]


def post_image(owner: V2Owner, *, filename="judge.png", data: bytes | None = None,
               engine="fake", extra: dict | None = None) -> httpx.Response:
    return owner.post(
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
