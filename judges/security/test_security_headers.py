"""Claim 9: the frontend serves no security headers at all -- no CSP, no
X-Content-Type-Options, no frame-ancestors/X-Frame-Options.

Evidence: frontend/nginx.conf has no `add_header` for any of these (the
only `add_header` in the whole file is `Cache-Control` for static asset
caching). Nothing in the Vue build injects them via <meta> either (CSP's
`frame-ancestors` can only be set via a header anyway, never via <meta>).

This matters beyond style: claim 8's stored-XSS payload runs unprotected by
any CSP (which could have blocked the inline `onerror` handler or
constrained `img-src`), and the whole app can be framed by any origin
(clickjacking) since no frame-ancestors/X-Frame-Options is sent.

Safe behaviour under test: the frontend's responses include a
Content-Security-Policy, X-Content-Type-Options: nosniff, and some framing
protection (frame-ancestors in the CSP, or X-Frame-Options).
"""
from __future__ import annotations

import httpx


def test_frontend_sends_content_security_policy(frontend):
    resp = httpx.get(frontend, timeout=30)
    assert "content-security-policy" in {k.lower() for k in resp.headers}, (
        "No Content-Security-Policy header on the frontend's response. "
        f"Headers seen: {sorted(resp.headers.keys())}"
    )


def test_frontend_sends_nosniff(frontend):
    resp = httpx.get(frontend, timeout=30)
    value = resp.headers.get("x-content-type-options", "")
    assert value.lower() == "nosniff", (
        "X-Content-Type-Options: nosniff is missing from the frontend's "
        f"response (got {value!r}). Headers seen: {sorted(resp.headers.keys())}"
    )


def test_frontend_restricts_framing(frontend):
    resp = httpx.get(frontend, timeout=30)
    headers = {k.lower(): v for k, v in resp.headers.items()}

    csp = headers.get("content-security-policy", "")
    xfo = headers.get("x-frame-options", "")

    has_frame_ancestors = "frame-ancestors" in csp.lower()
    has_xfo = xfo.upper() in ("DENY", "SAMEORIGIN")

    assert has_frame_ancestors or has_xfo, (
        "No framing protection: neither a CSP frame-ancestors directive "
        "nor a DENY/SAMEORIGIN X-Frame-Options header was sent, so any "
        f"origin can embed the app in an <iframe>. CSP={csp!r}, "
        f"X-Frame-Options={xfo!r}"
    )
