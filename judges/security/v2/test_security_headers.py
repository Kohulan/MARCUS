"""v1 claim 9 on v2: responses carry a CSP, nosniff and framing protection.

v1: the frontend (nginx, :18080) sent none of them.

v2: the React UI does not exist yet, so the target is the v2 edge itself (nginx :18090 in
front of the API). Both layers set the headers: the API's pure-ASGI SecurityMiddleware on every
API response (errors and files included), nginx on its own replies (its 404 outside /api/v2,
413, 502/504). Each check covers a set of responses of different kinds, not only one 200.
When the UI exists, point a copy of these checks at its origin too.
"""
from __future__ import annotations

from v2.helpers import API, expect_ok, random_id


def _responses(owner, sp) -> dict:
    """name -> response; the first one is the existence check."""
    return {
        "GET /papers (200 json)": expect_ok(owner.get(f"{API}/papers"), "GET /api/v2/papers"),
        "GET /health (200)": owner.get(f"{API}/health"),
        "GET page image (200 png)": sp.owner.get(f"{API}/papers/{sp.paper_id}/pages/0/image"),
        "GET /papers/{random} (404 owned)": owner.get(f"{API}/papers/{random_id()}"),
        "GET unknown /api/v2 route (404)": owner.get(f"{API}/judge-no-such-route"),
        "POST /tools/depict bad body (422)": owner.post(f"{API}/tools/depict", json={}),
        "GET / (nginx's own 404)": owner.get("/"),
    }


def test_frontend_sends_content_security_policy(new_owner, shared_paper):
    sp = shared_paper()
    missing = {name: sorted(r.headers.keys()) for name, r in _responses(new_owner(), sp).items()
               if "content-security-policy" not in r.headers}
    assert not missing, f"no Content-Security-Policy on: {missing}"


def test_frontend_sends_nosniff(new_owner, shared_paper):
    sp = shared_paper()
    bad = {name: r.headers.get("x-content-type-options")
           for name, r in _responses(new_owner(), sp).items()
           if r.headers.get("x-content-type-options", "").lower() != "nosniff"}
    assert not bad, f"X-Content-Type-Options is not nosniff on: {bad}"


def test_frontend_restricts_framing(new_owner, shared_paper):
    sp = shared_paper()
    bad = {}
    for name, r in _responses(new_owner(), sp).items():
        csp = r.headers.get("content-security-policy", "").lower()
        xfo = r.headers.get("x-frame-options", "").upper()
        if "frame-ancestors" not in csp and xfo not in ("DENY", "SAMEORIGIN"):
            bad[name] = (csp, xfo)
    assert not bad, f"no framing protection (CSP frame-ancestors or X-Frame-Options) on: {bad}"
