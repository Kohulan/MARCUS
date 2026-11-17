"""v1 claim 6 on v2: no unauthenticated teardown, no global reset, no cross-owner listing.

v1: DELETE /session/remove/{id} removed anyone's session with no credential; POST
/session/reset reset every session; GET /latest/docling_conversion/list_pdfs listed every
upload to anyone.

v2: every resource belongs to an owner (anonymous `marcus_owner` cookie, or an `mk_` API key).
    DELETE /api/v2/papers/{id}          owner only; anyone else gets the one 404
    (no global reset over HTTP)         purge / key revocation are the `marcus` CLI only
    GET /api/v2/papers (+ every per-paper/segment/image route, incl. the new
    GET /api/v2/papers/{id}/steps)      my resources only; others' ids get the one 404
"""
from __future__ import annotations

import secrets

from payloads import garbage_pdf_bytes

from v2.helpers import (
    API,
    describe,
    expect_ok,
    random_id,
    same_answer,
    upload_image,
    upload_paper,
    wait_image,
)


def test_session_cannot_be_removed_by_an_unrelated_caller(new_owner):
    owner = new_owner()
    # Existence check: the owner deletes one of their own papers (204), then it is gone.
    doomed = upload_paper(owner, data=garbage_pdf_bytes())
    expect_ok(owner.delete(f"{API}/papers/{doomed}"), "DELETE /api/v2/papers/{id}")
    gone = owner.get(f"{API}/papers/{doomed}")
    missing = owner.get(f"{API}/papers/{random_id()}")
    assert gone.status_code == 404 and same_answer(gone, missing), (
        f"a deleted paper must get the same 404 as a missing one: {describe(gone)} vs "
        f"{describe(missing)}")

    target = upload_paper(owner, data=garbage_pdf_bytes())
    stranger = new_owner()  # a different owner, with a cookie of its own
    expect_ok(stranger.get(f"{API}/papers"), "GET /api/v2/papers (stranger gets a cookie)")
    nobody = new_owner(anonymous=True)  # no credential at all

    problems = []
    for who, caller in (("another owner", stranger), ("no credential", nobody)):
        a = caller.delete(f"{API}/papers/{target}")
        b = caller.delete(f"{API}/papers/{random_id()}")
        if not (a.status_code == 404 and same_answer(a, b)):
            problems.append(f"{who}: DELETE {describe(a)} vs random id {describe(b)}")

    after = owner.get(f"{API}/papers/{target}")
    if after.status_code != 200 or after.json().get("status") == "deleted":
        problems.append(f"owner's paper after the attempts: {describe(after)}")

    assert not problems, f"an unrelated caller could delete or probe a paper: {problems}"


# Destructive "everyone" actions a v2 build must not expose over HTTP.
GLOBAL_ACTIONS = [
    ("POST", "/session/reset"),
    ("POST", f"{API}/session/reset"),
    ("POST", f"{API}/reset"),
    ("DELETE", f"{API}/papers"),
    ("DELETE", f"{API}/images"),
    ("POST", f"{API}/purge"),
    ("POST", f"{API}/admin/purge"),
    ("DELETE", f"{API}/owners"),
    ("POST", f"{API}/apikeys"),
    ("GET", f"{API}/apikeys"),
    ("GET", f"{API}/owners"),
]


def test_global_session_reset_requires_a_credential(new_owner):
    owner = new_owner()
    # Existence check: the destructive action v2 does offer (owner-scoped) works for the owner.
    mine = upload_paper(owner, data=garbage_pdf_bytes())
    expect_ok(owner.delete(f"{API}/papers/{mine}"), "DELETE /api/v2/papers/{id}")
    keep = upload_paper(owner, data=garbage_pdf_bytes())

    problems = []
    nobody = new_owner(anonymous=True)
    for method, path in GLOBAL_ACTIONS:
        resp = nobody.request(method, path)
        if resp.status_code < 400:
            problems.append(f"{method} {path} without a credential -> {describe(resp)}")

    # A made-up API key is refused (401), never treated as an anonymous or other owner.
    forged = new_owner(api_key=f"mk_{secrets.token_urlsafe(32)}")
    for method, path in (("GET", f"{API}/papers"), ("DELETE", f"{API}/papers/{keep}"),
                         ("POST", f"{API}/tools/smiles-to-molfile")):
        kw = {"json": {"smiles": "CCO"}} if method == "POST" else {}
        resp = forged.request(method, path, **kw)
        if resp.status_code != 401:
            problems.append(f"forged API key: {method} {path} -> {describe(resp)}")

    listed = {p["id"] for p in expect_ok(owner.get(f"{API}/papers"), "GET /api/v2/papers")
              .json()["papers"]}
    if keep not in listed:
        problems.append(f"owner's paper {keep} disappeared after the attempts")

    assert not problems, f"a global/credential-less action was accepted: {problems}"


def test_uploaded_pdf_is_not_listed_to_an_unrelated_caller(shared_paper, new_owner):
    sp = shared_paper()
    pid, sid = sp.paper_id, sp.segment_ids[0]
    listing = expect_ok(sp.owner.get(f"{API}/papers"), "GET /api/v2/papers").json()
    assert pid in {p["id"] for p in listing["papers"]}, "owner's own listing misses the paper"
    expect_ok(sp.owner.get(f"{API}/papers/{pid}/steps"), "GET /api/v2/papers/{id}/steps (R18)")

    img_owner = new_owner()
    job = upload_image(img_owner)
    wait_image(img_owner, job)

    # (method, template, json body): {p} paper id, {s} segment id, {j} image job id
    routes = [
        ("GET", "/papers/{p}", None),
        ("GET", "/papers/{p}/segments", None),
        ("GET", "/papers/{p}/steps", None),
        ("GET", "/papers/{p}/text", None),
        ("GET", "/papers/{p}/export", None),
        ("GET", "/papers/{p}/export?format=csv", None),
        ("GET", "/papers/{p}/events", None),
        ("GET", "/papers/{p}/pages/0/image", None),
        ("GET", "/segments/{s}/image", None),
        ("POST", "/segments/{s}/predictions", {"engine": "fake"}),
        ("PUT", "/segments/{s}/curation", {"status": "accepted"}),
        ("GET", "/images/{j}", None),
    ]

    problems = []
    for who, caller in (("another owner", new_owner()), ("no credential",
                                                         new_owner(anonymous=True))):
        names = {p["id"] for p in expect_ok(caller.get(f"{API}/papers"),
                                            f"GET /api/v2/papers ({who})").json()["papers"]}
        if pid in names:
            problems.append(f"{who}: GET /papers lists the owner's paper")
        queue = caller.get(f"{API}/queue")
        if pid in queue.text:
            problems.append(f"{who}: GET /queue mentions the owner's paper")
        for method, template, body in routes:
            real = API + template.format(p=pid, s=sid, j=job)
            fake = API + template.format(p=random_id(), s=random_id(), j=random_id())
            a = caller.request(method, real, json=body, timeout=30)
            b = caller.request(method, fake, json=body, timeout=30)
            if not (a.status_code == 404 and same_answer(a, b)):
                problems.append(f"{who}: {method} {template}: {describe(a)} vs missing "
                                f"{describe(b)}")

    assert not problems, f"another caller can see or probe the owner's data: {problems}"
