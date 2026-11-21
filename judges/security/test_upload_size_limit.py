"""Claim 7: the backend documents a 20MB upload cap but never enforces it
on most upload endpoints.

Evidence:
  * backend/app/config.py: `MAX_UPLOAD_SIZE = 20 * 1024 * 1024` is defined
    and printed at startup ("Max Upload Size: 20 MB"), but is never
    imported or referenced anywhere under routers/ or modules/ -- it is
    dead configuration.
  * app.security.file_validator.FileUploadValidator (which does enforce a
    20MB `MAX_FILE_SIZE`) is only ever called from
    docling_conversion.extract_pdf_json (docling_conversion.py:22,84).
    extract_pdf_text ("/extract_text"), decimer's extract_doi, and all
    three ocsr upload endpoints never call it, so nothing checks size
    before the file is written to disk and handed to a parser/model.
  * nginx (frontend/nginx.conf) caps uploads through the frontend proxy at
    10MB, but that only protects the :18080 path -- the backend at :19000
    has no cap of its own, so anything reaching it directly sails through
    uncapped.

This is picked up with an OCSR image upload rather than a PDF upload: a
quick manual check against this build showed a 20MB+ "PDF" being accepted
and then run through several minutes of PDF/DOI-extraction fallback
libraries (pdf2doi's PyPDF2 -> pdfminer -> OCR chain) with no size guard --
real, but far too slow to use as a repeatable automated check without
tying up the single backend worker for minutes on every run. An oversized
image hits the same missing-size-check code path (ocsr_wrapper.save_uploaded_image
has no size check either) but fails fast once an image decoder looks at
the (corrupt) pixel data, giving the same proof without the multi-minute
fallback chain.

Safe behaviour under test: a file larger than the backend's own documented
20MB limit is rejected (ideally 413) before any processing, directly
against the backend -- not relying on nginx to catch it first.
"""
from __future__ import annotations

import httpx

from payloads import minimal_png


def _oversized_png_bytes(total_size: int) -> bytes:
    # Valid PNG signature + IHDR-shaped prefix so content-sniffing/magic
    # checks (if any ran) would accept it, padded with bytes that are not a
    # valid compressed IDAT stream -- an image decoder rejects this as soon
    # as it tries to inflate the pixel data, regardless of how much padding
    # follows.
    base = minimal_png()
    return base + b"\x00" * (total_size - len(base))


def test_oversized_image_upload_is_rejected_by_the_backend_directly(backend, fs_probe):
    # One byte over the backend's own documented 20MB cap.
    oversized = _oversized_png_bytes(20 * 1024 * 1024 + 1)

    with httpx.Client(base_url=backend, timeout=120) as uploader:
        resp = uploader.post(
            "/latest/ocsr/generate_smiles",
            data={"engine": "decimer"},
            files={
                "image_file": (
                    "judge_oversize_probe.png",
                    oversized,
                    "image/png",
                )
            },
        )

    # Whatever the backend wrote under IMAGES_DIR for this upload, clean it
    # up (save_uploaded_image appends a short uuid before the extension).
    import subprocess

    from fs_probe import DockerProbe

    if isinstance(fs_probe, DockerProbe):
        r = subprocess.run(
            [
                "docker", "exec", fs_probe.container,
                "sh", "-c",
                "ls -1 /app/uploads/chem_images | grep judge_oversize_probe || true",
            ],
            capture_output=True, text=True,
        )
        for name in r.stdout.splitlines():
            if name.strip():
                fs_probe.remove(f"/app/uploads/chem_images/{name.strip()}")

    assert resp.status_code == 413, (
        "Uploading an image 1 byte over the backend's own documented 20MB "
        f"cap directly to the backend was not rejected with 413: got "
        f"{resp.status_code} ({resp.text[:200]!r}). MAX_UPLOAD_SIZE is "
        "configured but not enforced on this endpoint."
    )
