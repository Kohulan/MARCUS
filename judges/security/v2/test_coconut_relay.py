"""The COCONUT relay (owner decision 2026-11-20): not an open proxy, login rate-limited, no
password or token in any log.

COCONUT sends no CORS headers, so the stack's nginx relays exactly three calls to the fixed
host (backend-v2/docker/nginx.conf, `location ^~ /api/v2/coconut/`). The fake stack puts a fake
COCONUT under COCONUT's name (backend-v2/tests/fake_coconut/server.py); it records what each
relayed request looked like upstream (never a body, never the Authorization value) in
/tmp/seen.jsonl, which these tests read with `docker exec`. Nothing reaches the real COCONUT.

Containers: from MARCUS_FS_PROBE=docker:<project>-api-1, the nginx and fake COCONUT containers
are <project>-nginx-1 and <project>-fake-coconut-1 (or MARCUS_NGINX_CONTAINER,
MARCUS_FAKE_COCONUT_CONTAINER).

Order matters: the login limit (3/min per address, burst 3) is shared by the whole run, so only
the log test (one login) and the rate-limit test (last in this file) send logins.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
from urllib.parse import urlsplit

from v2.helpers import docker_probe, expect_ok

RELAY = "/api/v2/coconut"
COCONUT_HOST = "coconut.naturalproducts.net"
SEARCH = {"type": "tags", "tagType": "citations", "query": "10.1/judge", "limit": 20,
          "sort": "desc", "page": 1, "offset": 0}  # fmt: skip
# What the relay sends upstream, and nothing else (connection, content-length: nginx's own).
UPSTREAM_HEADERS = {"host", "content-type", "accept", "user-agent", "connection", "content-length"}
# What may come back: COCONUT's Content-Type / Content-Length, nginx's own fixed headers.
OUR_HEADERS = {
    "content-type": None,
    "content-length": None,
    "server": "nginx",
    "date": None,
    "connection": None,
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
    "cache-control": "no-store",
}
# Client headers that must never reach COCONUT.
CLIENT_HEADERS = {
    "Cookie": "marcus_owner=judge-cookie",
    "X-Forwarded-For": "203.0.113.9",
    "X-Real-IP": "203.0.113.9",
    "Forwarded": "for=203.0.113.9",
    "Referer": "http://localhost/app/papers/judge",
    "Origin": "http://evil.example",
    "X-Judge": "1",
}


def _container(fs_probe, kind: str, env: str) -> str:
    if os.environ.get(env):
        return os.environ[env]
    api = docker_probe(fs_probe).container
    assert "-api-" in api, f"cannot derive the {kind} container from {api}; set {env}"
    return api.replace("-api-", f"-{kind}-")


def _seen(fs_probe) -> list[dict]:
    fake = _container(fs_probe, "fake-coconut", "MARCUS_FAKE_COCONUT_CONTAINER")
    r = subprocess.run(["docker", "exec", fake, "sh", "-c", "cat /tmp/seen.jsonl 2>/dev/null"],
                       capture_output=True, text=True, timeout=30)  # fmt: skip
    assert r.returncode in (0, 1), f"docker exec {fake}: {r.stderr}"
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def _logs(container: str, since: str) -> str:
    r = subprocess.run(["docker", "logs", "--since", since, container],
                       capture_output=True, text=True, timeout=60)  # fmt: skip
    assert r.returncode == 0, r.stderr
    return r.stdout + r.stderr


def _search(owner, **kw):
    return owner.post(f"{RELAY}/search", json=SEARCH, **kw)


# The fake COCONUT's token (tests/fake_coconut/server.py): an empty mutate is a 200.
FAKE_TOKEN = "fake-coconut-token"  # noqa: S105


def _exists(owner):
    """The existence check, on mutate: its per-client budget (burst 20) is the roomiest, and the
    searches (burst 10) are kept for what the tests look at."""
    r = owner.post(f"{RELAY}/reports/mutate", json={"mutate": []},
                   headers={"Authorization": f"Bearer {FAKE_TOKEN}"})  # fmt: skip
    return expect_ok(r, f"POST {RELAY}/reports/mutate (the relay to the fake COCONUT)")


def _raw(owner, target: str, host: str = "localhost") -> int:
    """POST `target` exactly as written in the request line (no client-side normalising)."""
    url = urlsplit(str(owner.http.base_url))
    raw = (f"POST {target} HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\n"
           f"Content-Length: {len(json.dumps(SEARCH))}\r\nConnection: close\r\n\r\n"
           f"{json.dumps(SEARCH)}")  # fmt: skip
    with socket.create_connection((url.hostname, url.port or 80), timeout=30) as s:
        s.sendall(raw.encode())
        status_line = s.makefile("rb").readline().decode()
    return int(status_line.split()[1])


def test_relay_reaches_only_the_three_fixed_coconut_calls(new_owner, fs_probe):
    owner = new_owner(anonymous=True)
    _exists(owner)
    before = len(_seen(fs_probe))
    assert _search(owner).status_code == 200

    # every other path under the prefix, and other ways to name a host or path: nginx's 404
    others = ["/", "/auth", "/auth/logout", "/auth/login/", "/auth/login/x", "/reports",
              "/reports/1", "/reports/mutate/x", "/search/x", "/users", "/api/auth/login",
              "/https://example.org/", "//example.org/api/search"]  # fmt: skip
    for path in others:
        r = owner.post(RELAY + path, json={})
        assert r.status_code == 404, (path, r.status_code)
    # other methods on the three
    for path in ("/auth/login", "/reports/mutate", "/search"):
        for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"):
            r = owner.request(method, RELAY + path)
            assert r.status_code == 405, (method, path, r.status_code)
        # no query, no body that is not JSON (a cross-site form post cannot make one)
        assert owner.post(f"{RELAY}{path}?url=http://example.org/", json={}).status_code == 400
        r = owner.post(RELAY + path, content=b"a=b",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})  # fmt: skip
        assert r.status_code == 415, (path, r.status_code)

    # Host from the client (a Host header, an absolute-form request line) changes nothing.
    assert _raw(owner, f"http://evil.example{RELAY}/search", host="evil.example") == 200
    r = _search(owner, headers={"Host": "evil.example"})
    assert r.status_code == 200, r.status_code
    # Spellings nginx normalises before it picks a location (dot segments, %-escapes, an
    # escaped slash) end on the fixed upstream path; path parameters and an escaped "?" are no
    # relay path at all.
    for target in (f"{RELAY}/x/../search", f"{RELAY}/se%61rch", f"{RELAY}/x%2F..%2Fsearch"):
        assert _raw(owner, target) == 200, target
    for target in (f"{RELAY}/search;a=b", f"{RELAY}/search%3Fa=b", f"{RELAY}/search%2F"):
        assert _raw(owner, target) == 404, target

    new = _seen(fs_probe)[before:]
    # exactly the six relayed searches reached the upstream, each as the fixed call
    assert [(e["method"], e["path"], e["query"]) for e in new] == [("POST", "/api/search", "")] * 6
    for e in new:
        assert e["headers"]["host"] == COCONUT_HOST, e
        assert e["sni"] == COCONUT_HOST, e


def test_relay_sends_no_client_headers_and_returns_only_status_and_body(new_owner, fs_probe):
    owner = new_owner(anonymous=True)
    before = len(_seen(fs_probe))
    r = expect_ok(_search(owner, headers=CLIENT_HEADERS), f"POST {RELAY}/search")
    # COCONUT's Set-Cookie, CORS, Location, CSP, caching and its own headers never come back
    extra = {k: v for k, v in r.headers.items() if k.lower() not in OUR_HEADERS}
    assert not extra, f"upstream headers passed back: {extra}"
    for name, value in OUR_HEADERS.items():
        if value is not None:
            assert r.headers.get(name) == value, (name, r.headers.get(name))
    assert r.headers["content-type"] == "application/json"
    assert r.json() == {"data": {"data": []}}

    # mutate carries the token upstream; search does not, whatever the client sends
    m = owner.post(f"{RELAY}/reports/mutate", json={"mutate": []},
                   headers={**CLIENT_HEADERS, "Authorization": "Bearer judge-wrong"})  # fmt: skip
    assert m.status_code == 401, m.status_code  # the fake's own answer to a wrong token
    s = _search(owner, headers={"Authorization": "Bearer judge-wrong"})
    assert s.status_code == 200
    new = _seen(fs_probe)[before:]
    assert [e["path"] for e in new] == ["/api/search", "/api/reports/mutate", "/api/search"]
    for e in new:
        assert set(e["headers"]) == UPSTREAM_HEADERS, e["headers"]
    assert [e["authorization"] for e in new] == [False, True, False]


def test_relay_keeps_coconut_status_and_body(new_owner):
    """The client's messages depend on COCONUT's status (401/403/422/429 and 5xx): the relay
    passes each one and its JSON body through unchanged (mutate: the fake answers the status
    named in the token)."""
    owner = new_owner(anonymous=True)
    _exists(owner)
    for status in (401, 403, 413, 422, 429, 500, 503):
        r = owner.post(f"{RELAY}/reports/mutate", json={"mutate": []},
                       headers={"Authorization": f"Bearer status-{status}"})  # fmt: skip
        assert r.status_code == status, (status, r.status_code)
        assert r.headers["content-type"] == "application/json", status
        assert r.json() == {"message": f"fake coconut {status}"}, status


def test_no_password_or_token_in_any_log(new_owner, fs_probe):
    """A login, a mutate and a query carrying unique canaries: none of them appears in the logs
    of nginx or the API (the relay logs its path only)."""
    owner = new_owner(anonymous=True)
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 1))
    password, token, query = (f"judge-{k}-{uuid.uuid4().hex}" for k in ("pw", "tok", "q"))
    _exists(owner)
    login = owner.post(f"{RELAY}/auth/login",
                       json={"email": "judge@example.org", "password": password})  # fmt: skip
    assert login.status_code in (401, 429), login.status_code  # wrong login (or limited)
    m = owner.post(f"{RELAY}/reports/mutate", json={"mutate": []},
                   headers={"Authorization": f"Bearer {token}"})  # fmt: skip
    assert m.status_code == 401
    assert owner.post(f"{RELAY}/search?token={query}", json=SEARCH).status_code == 400
    time.sleep(1)  # let docker flush the log lines
    nginx = _container(fs_probe, "nginx", "MARCUS_NGINX_CONTAINER")
    api = docker_probe(fs_probe).container
    for container in (nginx, api):
        logs = _logs(container, since)
        for canary in (password, token, query):
            assert canary not in logs, f"{canary[:10]}... in the logs of {container}"
    relay_lines = [ln for ln in _logs(nginx, since).splitlines() if f"{RELAY}/" in ln]
    assert len(relay_lines) >= 4, relay_lines
    assert not any("?" in ln for ln in relay_lines), relay_lines


def test_coconut_login_is_rate_limited(new_owner, fs_probe):
    """Credential stuffing through MARCUS: logins are limited per address (3/min, burst 3, then
    429 before anything is relayed). Last in this file: it uses up the login budget."""
    owner = new_owner(anonymous=True)
    _exists(owner)
    before = len(_seen(fs_probe))
    answers = []
    for i in range(10):
        r = owner.post(f"{RELAY}/auth/login",
                       json={"email": f"judge-{i}@example.org", "password": "wrong"})  # fmt: skip
        answers.append(r.status_code)
    assert set(answers) <= {401, 429}, answers
    assert answers.index(429) <= 4, answers  # at most burst + 1 before the first 429
    assert answers[5:] == [429] * 5, answers
    relayed = [e for e in _seen(fs_probe)[before:] if e["path"] == "/api/auth/login"]
    assert len(relayed) == answers.count(401) <= 5, (relayed, answers)
