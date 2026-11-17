"""v1 claim 4 on v2: the page-image route must not be a filesystem-existence oracle.

v1: GET /latest/decimer/get_highlighted_page/{segment_filename}?pdf_filename=... joined
`pdf_filename` onto PDF_DIR unchecked: an existing outside path gave 500, a missing one 404.

v2: GET /api/v2/papers/{paper_id}/pages/{n}/image serves the server-rendered page PNG, built from
(paper uuid, int page) only; the page with the highlighted segment is drawn by the client from
the segment bbox. Safe behaviour: every pair below (an existing target vs a missing one) gets
the byte-identical answer, including another owner's existing page vs a random id, both
through nginx and straight to the API inside its container.
"""
from __future__ import annotations

import uuid

from v2.helpers import API, describe, direct_get_many, expect_ok, random_id, same_answer


def test_highlighted_page_pdf_filename_is_not_an_existence_oracle(shared_paper, new_owner,
                                                                    fs_probe):
    sp = shared_paper()
    pid = sp.paper_id
    expect_ok(sp.owner.get(f"{API}/papers/{pid}/pages/0/image"),
              "GET /api/v2/papers/{id}/pages/{n}/image")

    assert fs_probe.exists("/etc/hostname")
    missing = f"/etc/judge-missing-{uuid.uuid4().hex}"
    assert not fs_probe.exists(missing)
    up = "../../../../../.."

    def enc(p: str) -> str:
        return p.replace("/", "%2F")

    pairs = {
        # v1's parameter, now unknown to v2: must be ignored the same way either way
        "pdf_filename query": (
            f"{API}/papers/{pid}/pages/0/image?pdf_filename={up}/etc/hostname",
            f"{API}/papers/{pid}/pages/0/image?pdf_filename={up}{missing}",
        ),
        "traversal in page number": (
            f"{API}/papers/{pid}/pages/{enc(up + '/etc/hostname')}/image",
            f"{API}/papers/{pid}/pages/{enc(up + missing)}/image",
        ),
        "traversal in paper id": (
            f"{API}/papers/{enc(up + '/etc/hostname')}/pages/0/image",
            f"{API}/papers/{enc(up + missing)}/pages/0/image",
        ),
        "page past the end vs far past the end": (
            f"{API}/papers/{pid}/pages/{sp.detail['pages']}/image",
            f"{API}/papers/{pid}/pages/99999/image",
        ),
    }
    oracles = []
    for name, (existing_raw, missing_raw) in pairs.items():
        a, b = sp.owner.raw_get(existing_raw), sp.owner.raw_get(missing_raw)
        if not same_answer(a, b):
            oracles.append(f"{name} via nginx: existing {describe(a)} vs missing {describe(b)}")
    # Straight to the API too: nginx answers some of these shapes itself (400), which would
    # hide an oracle in the API behind it.
    flat = [raw for pair in pairs.values() for raw in pair]
    direct = direct_get_many(fs_probe, flat, sp.owner.cookie)
    for i, name in enumerate(pairs):
        a, b = direct[2 * i], direct[2 * i + 1]
        if (a.status_code, a.content) != (b.status_code, b.content):
            oracles.append(f"{name} direct: existing HTTP {a.status_code} {a.text[:120]!r} vs "
                           f"missing HTTP {b.status_code} {b.text[:120]!r}")

    # The v2 form of the oracle: another owner's page that exists on disk vs a random id.
    stranger = new_owner()
    a = stranger.get(f"{API}/papers/{pid}/pages/0/image")
    b = stranger.get(f"{API}/papers/{random_id()}/pages/0/image")
    if not (same_answer(a, b) and a.status_code == 404):
        oracles.append(f"other owner's page: {describe(a)} vs random id {describe(b)}")

    assert not oracles, f"the page-image route leaks existence: {oracles}"
