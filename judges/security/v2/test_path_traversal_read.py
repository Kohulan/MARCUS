"""v1 claim 1 on v2: a file-serving route must never return a file from outside its own
server-made path.

v1: GET /latest/decimer/get_segment_image/{directory}/{image_name:path} joined a client path
onto SEGMENTS_DIR (`x//etc/passwd` served /etc/passwd).

v2 file-serving routes take only ids, and the path is built by the server
(marcus.core.storage, uuid.UUID only; crops are content-addressed by their sha256):

    GET /api/v2/segments/{segment_id}/image
    GET /api/v2/papers/{paper_id}/pages/{n}/image

Each test first fetches a real crop / page image as its owner (existence check), then sends
traversal shapes (absolute paths, `../`, %2F-encoded, extra path segments) as that owner, twice:
through the real edge (nginx), and straight to the API inside its container (nginx rejects or
normalises many of these shapes itself, so the API must be safe without it). Nothing outside
the data layout may come back.
"""
from __future__ import annotations

import uuid

from v2.helpers import API, describe, direct_get_many, expect_ok

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _existence(shared_paper):
    sp = shared_paper()
    seg = expect_ok(sp.owner.get(f"{API}/segments/{sp.segment_ids[0]}/image"),
                    "GET /api/v2/segments/{id}/image")
    assert seg.headers["content-type"] == "image/png" and seg.content.startswith(PNG_MAGIC)
    page = expect_ok(sp.owner.get(f"{API}/papers/{sp.paper_id}/pages/0/image"),
                     "GET /api/v2/papers/{id}/pages/{n}/image")
    assert page.headers["content-type"] == "image/png" and page.content.startswith(PNG_MAGIC)
    return sp


def _traversal_paths(sp, target: str) -> list[str]:
    """Raw request paths that try to reach the absolute path `target` (e.g. "/etc/passwd")."""
    rel = "../../../../../.." + target  # deep enough from /data/papers/<id>/segments/by-sha
    enc_rel = rel.replace("/", "%2F")
    enc_abs = target.replace("/", "%2F")
    sid, pid = sp.segment_ids[0], sp.paper_id
    return [
        # v1's exact shape: an absolute path after a directory segment
        f"{API}/segments/x/{target}",
        f"{API}/segments/x/{target}/image",
        f"{API}/segments/{sid}/{target}",
        f"{API}/segments/{sid}/image/{target}",
        f"{API}/segments/{sid}/image{target}",
        # %2F-encoded absolute and relative paths in the id segment
        f"{API}/segments/{enc_abs}/image",
        f"{API}/segments/{enc_rel}/image",
        f"{API}/segments/{sid}%2F{enc_rel}/image",
        # dot segments sent raw (the edge must not resolve them into another route)
        f"{API}/segments/{sid}/../../{rel}",
        f"{API}/segments/{sid}/image/{rel}",
        # the page route: in the page number and in the paper id
        f"{API}/papers/{pid}/pages/{enc_rel}/image",
        f"{API}/papers/{pid}/pages/{enc_abs}/image",
        f"{API}/papers/{pid}/pages/0/image/{rel}",
        f"{API}/papers/{enc_rel}/pages/0/image",
        f"{API}/papers/{pid}%2F{enc_rel}/pages/0/image",
        # shallow enough that nginx's normalised path stays under /api/v2/ and is proxied
        f"{API}/papers/{pid}/pages/..%2F..%2F..{enc_abs}/image",
        f"{API}/segments/{sid}/..%2F..{enc_abs}",
        f"{API}/segments/..%2F{enc_abs}/image",
        # outside /api/v2 entirely
        f"/{rel}",
        f"/{enc_rel}",
    ]


def test_get_segment_image_does_not_leak_etc_passwd(shared_paper, fs_probe):
    sp = _existence(shared_paper)

    leaks = []
    paths = _traversal_paths(sp, "/etc/passwd")
    for raw in paths:
        resp = sp.owner.raw_get(raw)
        if "root:" in resp.text:
            leaks.append(f"via nginx {raw} -> {describe(resp)}")
    for raw, resp in zip(paths, direct_get_many(fs_probe, paths, sp.owner.cookie)):
        if "root:" in resp.text:
            leaks.append(f"direct {raw} -> HTTP {resp.status_code}")

    assert not leaks, f"a v2 file route served /etc/passwd: {leaks}"


def test_get_segment_image_cannot_reach_arbitrary_container_file(shared_paper, fs_probe):
    """Probe-backed: canary files written inside the API container, outside the data layout
    (/tmp) and inside the data volume but outside any paper (/data), are never served."""
    sp = _existence(shared_paper)

    token = uuid.uuid4().hex[:12]
    contents = f"JUDGE-V2-CANARY-{token}".encode()
    canaries = [f"/tmp/judge_canary_{token}.png", f"/data/judge_canary_{token}.png"]
    for path in canaries:
        fs_probe.write_bytes(path, contents)
    try:
        served = []
        for path in canaries:
            paths = _traversal_paths(sp, path)
            for raw in paths:
                resp = sp.owner.raw_get(raw)
                if contents in resp.content:
                    served.append(f"via nginx {raw} -> HTTP {resp.status_code}")
            for raw, resp in zip(paths, direct_get_many(fs_probe, paths, sp.owner.cookie)):
                if contents in resp.content:
                    served.append(f"direct {raw} -> HTTP {resp.status_code}")
        assert not served, f"a v2 file route served a canary from outside its path: {served}"
    finally:
        for path in canaries:
            fs_probe.remove(path)
