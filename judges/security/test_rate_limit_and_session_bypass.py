"""Claim 5: the rate-limit and session middlewares never run for real
requests, because their own exempt-path lists are matched with
`path.startswith(exempt)` and both lists include an entry that is a prefix
of literally every path.

Evidence:
  * backend/app/middleware/rate_limit_middleware.py:
    `exempt_paths = [..., "/"]` and
    `_is_exempt_path` returns
    `any(path.startswith(exempt) for exempt in self.exempt_paths)`.
    Every request path starts with "/", so every request matches the "/"
    entry and `dispatch` returns `call_next(request)` before the rate
    limiter is ever consulted.
  * backend/app/middleware/session_middleware.py:
    `exempt_paths = [..., "/", "/latest", "/v1"]` -- the same `startswith`
    bug, plus "/latest" and "/v1" (the prefix of every real API route)
    listed explicitly, so session validation can never apply to an actual
    API call either way.

Observed live on this build: 40 back-to-back GETs to
/latest/decimer/health (the rate limiter's own default rule for an
unmatched endpoint is 15 req/60s + 5 burst = 20) all returned 200, with no
429 and no rate-limit headers.

Safe behaviour under test: a burst of requests from one client to a cheap
endpoint eventually gets HTTP 429.
"""
from __future__ import annotations


def test_burst_requests_eventually_get_rate_limited(client):
    # DEFAULT_RULES["default"] = requests=15, window=60, burst=5 -> a
    # client allowed through is capped at 20 requests/60s. 60 is comfortably
    # over that if rate limiting is active, and cheap (a health endpoint)
    # either way.
    statuses = []
    for _ in range(60):
        resp = client.get("/latest/decimer/health")
        statuses.append(resp.status_code)
        if resp.status_code == 429:
            break

    assert 429 in statuses, (
        "No request in a 60-request burst from a single client was rate "
        f"limited; the rate limiter is effectively disabled. Status "
        f"counts: {sorted(set(statuses), key=statuses.count, reverse=True)} "
        f"(first few: {statuses[:10]})"
    )


def test_api_calls_without_any_session_are_rejected(client):
    """A defence-in-depth check for the same exempt-path bug on the session
    side: SessionMiddleware is supposed to require a session id (header,
    query param, or cookie) for every /latest or /v1 call and return 401
    "NO_SESSION" otherwise (session_middleware.py). Because "/latest" and
    "/v1" are themselves in its exempt list, no session is ever required."""
    resp = client.get("/latest/docling_conversion/list_pdfs")

    assert resp.status_code == 401, (
        "Called an API endpoint with no X-Session-ID header, no "
        "session_id query param, and no marcus_session_id cookie, and it "
        f"was served anyway (status {resp.status_code}): session "
        "validation is not being enforced."
    )
