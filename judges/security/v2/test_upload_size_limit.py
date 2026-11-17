"""v1 claim 7 on v2: the 20 MB upload cap is enforced by the backend itself.

v1: MAX_UPLOAD_SIZE was dead configuration; a 20 MB + 1 byte image to /latest/ocsr/
generate_smiles was accepted.

v2: both uploads (POST /api/v2/papers, POST /api/v2/images) read the body through
`read_limited(MAX_UPLOAD_BYTES = 20 MiB)` and answer 413 {"detail": "File too large"}. nginx's own
cap is 21 MiB (a guard for spooling), so 20 MiB + 1 byte passes nginx and reaches the API: the
JSON body below is the API's answer, never nginx's HTML 413.
"""
from __future__ import annotations

from payloads import minimal_png

from v2.helpers import (
    MAX_UPLOAD_BYTES,
    describe,
    expect_ok,
    post_image,
    post_paper,
)


def _padded(prefix: bytes, total: int) -> bytes:
    return prefix + b"\x00" * (total - len(prefix))


def test_oversized_image_upload_is_rejected_by_the_backend_directly(new_owner):
    owner = new_owner()
    expect_ok(post_image(owner), "POST /api/v2/images")
    expect_ok(post_paper(owner), "POST /api/v2/papers")

    over = MAX_UPLOAD_BYTES + 1
    image = post_image(owner, filename="judge_oversize.png", data=_padded(minimal_png(), over))
    paper = post_paper(owner, filename="judge_oversize.pdf",
                       data=_padded(b"%PDF-1.4\n%judge oversize probe\n", over))

    problems = []
    for name, resp in (("POST /images", image), ("POST /papers", paper)):
        is_api_413 = (resp.status_code == 413
                      and resp.headers.get("content-type", "").startswith("application/json")
                      and resp.json().get("detail") == "File too large")
        if not is_api_413:
            problems.append(f"{name} with {over} bytes -> {describe(resp)}")

    assert not problems, (
        "an upload 1 byte over the backend's 20 MiB cap was not refused by the API with 413: "
        f"{problems}")
