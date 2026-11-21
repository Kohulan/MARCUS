"""Claim 1: GET /latest/decimer/get_segment_image/{directory}/{image_name:path}
lets an absolute path in `image_name` escape SEGMENTS_DIR entirely, because
the handler only checks for the substring ".." and then does
`os.path.join(SEGMENTS_DIR, directory, image_name)` -- and os.path.join
discards every earlier component once it hits an absolute path.

Evidence: backend/app/routers/decimer_segmentation.py:337-396
(get_segment_image), specifically the ".." substring check at line 367 and
the os.path.join at line 384.

Safe behaviour under test: requesting an absolute path must never return
the contents of a file outside the segments directory.
"""
from __future__ import annotations

import httpx

from security.fs_probe import ProbeError, get_probe

SEGMENTS_ENDPOINT = "/latest/decimer/get_segment_image"


def _escapes_via_absolute_path(client: httpx.Client, escape_path: str) -> httpx.Response:
    # `--path-as-is`-style request: the directory segment is an arbitrary
    # name, the image_name (a `:path` converter, so it accepts slashes)
    # is an absolute path. os.path.join(SEGMENTS_DIR, "x", escape_path)
    # == escape_path whenever escape_path starts with "/".
    url = f"{SEGMENTS_ENDPOINT}/judge-probe-dir{escape_path}"
    return client.get(url)


def test_get_segment_image_does_not_leak_etc_passwd(client):
    """FAILS on v1: GET .../get_segment_image/x//etc/passwd returns the
    container's /etc/passwd with HTTP 200."""
    resp = _escapes_via_absolute_path(client, "//etc/passwd")

    assert resp.status_code != 200 or "root:" not in resp.text, (
        "get_segment_image returned a file outside SEGMENTS_DIR: "
        f"status={resp.status_code}, body[:200]={resp.text[:200]!r}"
    )


def test_get_segment_image_cannot_reach_arbitrary_container_file(client):
    """Stronger, probe-backed version of the same claim: write a canary file
    inside the container (outside SEGMENTS_DIR) via the fs_probe, then prove
    the endpoint cannot serve it back. Confirms the vulnerability is a real
    filesystem escape, not just a coincidental match on /etc/passwd's
    contents."""
    try:
        probe = get_probe()
    except ProbeError as exc:
        import pytest

        pytest.fail(str(exc), pytrace=False)

    canary_path = "/tmp/judge_canary_claim1.txt"
    canary_contents = b"JUDGE-CANARY-CLAIM1-SHOULD-NOT-BE-SERVED\n"
    probe.write_bytes(canary_path, canary_contents)
    try:
        resp = _escapes_via_absolute_path(client, f"/{canary_path}")
        assert resp.status_code != 200 or resp.content != canary_contents, (
            "get_segment_image served a file written outside SEGMENTS_DIR "
            f"via an absolute-path escape: status={resp.status_code}"
        )
    finally:
        probe.remove(canary_path)
