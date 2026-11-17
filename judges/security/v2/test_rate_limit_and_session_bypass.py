"""v1 claim 5 on v2: rate limits actually apply, and missing credentials grant nothing.

v1: the rate-limit and session middlewares exempted every path (`startswith("/")`), so 60
requests to /latest/decimer/health were never limited and /latest/... needed no session.

v2 (marcus.api.security, Redis fixed one-minute windows):
    tools   60/min per owner          every POST /api/v2/tools/*
    upload  10/min per owner          POST /api/v2/papers + POST /api/v2/images
    ip      300/min per client IP     every route but GET /api/v2/health (IPv6: per /64)
The client IP is the socket peer, or X-Forwarded-For only when the peer is a trusted proxy
(nginx, which overwrites X-Forwarded-For with its own peer).

No credential is not an error in v2: the caller becomes a NEW anonymous owner (HttpOnly,
SameSite=Strict cookie) that owns nothing; a bad API key is 401.

docker-compose.fake.yml raises the per-IP limits (single-IP e2e): ip 6000/min, 1000 new owners
per hour, 100 active papers. The burst test meets the real tools limit (60, not raised); the
XFF test reads the API's effective ip limit and goes past it, so it is not vacuous on either
stack. The real 300/min, 10 new owners/hour and 6 active papers per IP are unit-tested in
backend-v2/tests/api (test_security_layer.py, test_owner_auth.py).
"""
from __future__ import annotations

import random
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from v2.helpers import (
    API,
    OWNER_COOKIE,
    describe,
    effective_settings,
    expect_ok,
    upload_paper,
)

TOOLS_LIMIT_PER_MIN = 60  # global constraints / spec; NOT raised by docker-compose.fake.yml
WINDOW_S = 60


def _tool(owner):
    return owner.post(f"{API}/tools/smiles-to-molfile", json={"smiles": "CCO"})


def test_burst_requests_eventually_get_rate_limited(new_owner):
    owner = new_owner()
    first = expect_ok(_tool(owner), "POST /api/v2/tools/smiles-to-molfile")
    assert "molfile" in first.json()

    # Two full windows' worth: a burst that straddles a window boundary still overflows one.
    statuses, limited = [first.status_code], None
    for _ in range(2 * TOOLS_LIMIT_PER_MIN + 10):
        resp = _tool(owner)
        statuses.append(resp.status_code)
        if resp.status_code == 429:
            limited = resp
            break

    assert limited is not None, (
        f"{len(statuses)} tool calls from one owner were never rate limited "
        f"(statuses: {sorted(set(statuses))})")
    assert len(statuses) <= 2 * TOOLS_LIMIT_PER_MIN + 1
    assert int(limited.headers.get("retry-after", "0")) >= 1, limited.headers
    assert limited.json() == {"detail": "rate limited"}

    # The limit is per owner: another owner from the same address is not limited by it.
    other = new_owner()
    expect_ok(_tool(other), "POST /api/v2/tools/smiles-to-molfile (another owner)")


def test_api_calls_without_any_session_are_rejected(new_owner):
    """v2 does not 401 a credential-less call; it gives it a new, empty owner. Proven here:
    such a caller gets a fresh HttpOnly/SameSite=Strict/Path=/api/v2 cookie and sees nothing of
    any other owner; a forged cookie is a new owner too; a forged API key is 401."""
    owner = new_owner()
    pid = upload_paper(owner)

    nobody = new_owner(anonymous=True)
    resp = expect_ok(nobody.get(f"{API}/papers"), "GET /api/v2/papers (no credential)")
    assert resp.json() == {"papers": []}, resp.text[:300]
    cookies = [c for c in resp.headers.get_list("set-cookie") if c.startswith(f"{OWNER_COOKIE}=")]
    assert len(cookies) == 1, resp.headers.get_list("set-cookie")
    attrs = {a.strip().split("=")[0].lower(): a.strip() for a in cookies[0].split(";")[1:]}
    assert "httponly" in attrs, cookies[0]
    assert attrs.get("samesite", "").lower() == "samesite=strict", cookies[0]
    assert attrs.get("path", "").lower() == "path=/api/v2", cookies[0]
    assert "secure" in attrs, cookies[0]
    token = re.match(rf"{OWNER_COOKIE}=([^;]*)", cookies[0]).group(1)
    assert token != owner.cookie

    # Each credential-less call is its own owner: there is no shared "anonymous" bucket.
    again = nobody.get(f"{API}/papers")
    assert again.json() == {"papers": []}
    token2 = re.match(rf"{OWNER_COOKIE}=([^;]*)", again.headers["set-cookie"]).group(1)
    assert token2 != token

    # A made-up cookie never resolves to an existing owner.
    forger = new_owner(anonymous=True)
    forger.http.headers["Cookie"] = f"{OWNER_COOKIE}={secrets.token_urlsafe(32)}"
    resp = forger.get(f"{API}/papers")
    assert resp.status_code == 200 and resp.json() == {"papers": []}, describe(resp)
    assert pid not in resp.text

    # A made-up API key is refused.
    resp = new_owner(api_key=f"mk_{secrets.token_urlsafe(32)}").get(f"{API}/papers")
    assert resp.status_code == 401, describe(resp)


def _rand_ip() -> str:
    return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}." \
           f"{random.randint(1, 254)}"


def _spoof_headers() -> dict:
    ip = _rand_ip()
    return {
        "X-Forwarded-For": f"{ip}, {_rand_ip()}",
        "X-Real-IP": ip,
        "CF-Connecting-IP": ip,
        "True-Client-IP": ip,
        "Forwarded": f"for={ip}",
    }


def _wait_for_window_start() -> None:
    """Fixed windows are `int(time) // 60` on the API host (same clock as here)."""
    into = time.time() % WINDOW_S
    if into > 1:
        time.sleep(WINDOW_S - into + 0.2)


@pytest.fixture
def ip_bucket_restored():
    """This test exhausts the per-IP bucket on purpose: wait for the next window afterwards so
    the rest of the suite (and anyone else on this stack) is not rate limited."""
    state = {"burst_started": False}
    yield state
    if state["burst_started"]:
        time.sleep(WINDOW_S - (time.time() % WINDOW_S) + 1)


def test_xff_spoof_cannot_escape_rate_limit(new_owner, fs_probe, ip_bucket_restored):
    owner = new_owner()
    expect_ok(owner.get(f"{API}/papers"), "GET /api/v2/papers")
    limit = effective_settings(fs_probe, "rate_limit_ip_per_min")["rate_limit_ip_per_min"]
    budget = limit + 50  # past the limit, whatever else counted in this window

    _wait_for_window_start()
    ip_bucket_restored["burst_started"] = True
    window = int(time.time()) // WINDOW_S
    stop = threading.Event()
    lock = threading.Lock()
    sent, first_429 = [0], [None]

    def worker(n: int) -> None:
        caller = new_owner(anonymous=True)  # no cookie: nothing to key on but the address
        for _ in range(n):
            if stop.is_set():
                return
            resp = caller.get(f"{API}/judge-xff-probe", headers=_spoof_headers())
            with lock:
                sent[0] += 1
                if resp.status_code == 429 and first_429[0] is None:
                    first_429[0] = resp
                    stop.set()

    threads = 8
    with ThreadPoolExecutor(threads) as pool:
        for f in [pool.submit(worker, budget // threads + 1) for _ in range(threads)]:
            f.result()

    crossed = int(time.time()) // WINDOW_S != window
    limited = first_429[0]
    assert limited is not None, (
        f"{sent[0]} requests with a different spoofed X-Forwarded-For / X-Real-IP / Forwarded "
        f"each were never rate limited (effective ip limit {limit}/min"
        + ("; the burst crossed a window boundary, rerun" if crossed else "") + ")")
    assert limited.json() == {"detail": "rate limited"}, describe(limited)
    assert sent[0] <= limit + 1 + threads, (sent[0], limit)
    print(f"ip limit {limit}/min: first 429 after {sent[0]} spoofed requests in one window")

    # Still limited for a brand-new caller with yet another spoofed address, on a real route.
    resp = new_owner(anonymous=True).get(f"{API}/papers", headers=_spoof_headers())
    if int(time.time()) // WINDOW_S == window:
        assert resp.status_code == 429, describe(resp)
