"""Claim 3: the `image_path` form field on /latest/ocsr/generate_smiles (and
generate_molfile, generate_both) accepts ANY path readable by the backend
process, not just files under IMAGES_DIR/SEGMENTS_DIR.

Evidence: backend/app/routers/ocsr_engine.py:62-77, `find_image_path`:

    if os.path.exists(image_path) and os.path.isfile(image_path):
        return image_path

returns the caller-supplied path verbatim whenever it exists on disk,
before any attempt to confine it to an upload directory. The router then
passes that path straight to `process_chemical_structure`
(ocsr_engine.py:199-212), so the response differs depending on whether the
path exists on the server at all -- a file-existence oracle -- and, for
anything the image-decoding/model step can open, an actual read of file
content outside the upload folders.

Observed live on this build: `image_path=/etc/hostname` (exists, not an
image) -> HTTP 500 "cannot identify image file '/etc/hostname'";
`image_path=/etc/<nonexistent>` -> HTTP 404 "Image file not found: ...".
Those two outcomes are indistinguishable for a safe implementation that
confines `image_path` to IMAGES_DIR/SEGMENTS_DIR: both should be a uniform
"not found"/"invalid" response that doesn't depend on what else lives on
the server's filesystem.

Safe behaviour under test: asking the OCSR endpoint to read a path outside
the upload directories gets the exact same rejection whether or not that
path exists on the server -- no oracle.
"""
from __future__ import annotations

import uuid


def test_ocsr_image_path_is_not_an_existence_oracle(client, fs_probe):
    # A file that certainly exists on the backend's filesystem but was never
    # uploaded through the app (outside IMAGES_DIR/SEGMENTS_DIR).
    existing_outside_path = "/etc/hostname"
    assert fs_probe.exists(existing_outside_path), (
        "test setup assumption failed: /etc/hostname should exist in the "
        "backend container"
    )

    # A path that certainly does not exist anywhere on the backend.
    missing_path = f"/etc/judge-missing-{uuid.uuid4().hex}"
    assert not fs_probe.exists(missing_path)

    resp_existing = client.post(
        "/latest/ocsr/generate_smiles",
        data={"engine": "decimer", "image_path": existing_outside_path},
    )
    resp_missing = client.post(
        "/latest/ocsr/generate_smiles",
        data={"engine": "decimer", "image_path": missing_path},
    )

    # Safe: a path outside the upload directories is rejected the same way
    # (e.g. always 400/404 "invalid path") regardless of whether it exists
    # on the server, so a caller learns nothing about the filesystem.
    assert resp_existing.status_code == resp_missing.status_code, (
        "generate_smiles's image_path field leaks filesystem existence: "
        f"an existing-but-unauthorized path got {resp_existing.status_code} "
        f"({resp_existing.text[:200]!r}) while a nonexistent path got "
        f"{resp_missing.status_code} ({resp_missing.text[:200]!r})"
    )
