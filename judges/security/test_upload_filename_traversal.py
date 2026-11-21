"""Claim 2: multipart upload filenames containing `../` write outside the
intended upload folder, on three separate endpoints that each build their
own "safe" filename but never strip path separators:

  * /latest/docling_conversion/extract_text
    backend/app/routers/docling_conversion.py:137-173 (extract_pdf_text) --
    `safe_filename = original_filename.replace(" ", "_")`, no `..` or `/`
    stripping, and does not call app.security.file_validator at all.
  * /latest/decimer/extract_doi
    backend/app/routers/decimer_segmentation.py:66-116 (extract_doi) --
    `safe_filename = f"{stem}_{uuid}{ext}"` where `stem` is
    `os.path.splitext(original_filename)[0]`, which still contains any
    `../` the attacker put in the original name.
  * /latest/ocsr/* uploads
    backend/app/modules/ocsr_wrapper.py:76-86 (save_uploaded_image) -- same
    `splitext`-then-insert-uuid pattern.

Evidence that the vulnerable endpoints skip the validator that would have
caught this: app.security.file_validator.validate_pdf_upload is imported
and called only by extract_pdf_json (docling_conversion.py:22,84); the
extract_text/extract_doi/ocsr upload handlers never call it.

Safe behaviour under test: a file written by any of these endpoints always
lands inside its own upload directory, however the client names it.
"""
from __future__ import annotations

import uuid

import pytest

from payloads import garbage_pdf_bytes, minimal_png


def _canary_token() -> str:
    # A bare token with no extension: handlers that insert their own uuid
    # do so *between* the stem and the extension (`stem_uuid.ext`), so
    # searching for this token alone (rather than "<token>.pdf") is what
    # survives that mangling and still proves the write landed outside the
    # upload directory.
    return f"judge_traversal_{uuid.uuid4().hex[:8]}"


@pytest.mark.parametrize(
    "path, field, filename_field, content, content_type",
    [
        (
            "/latest/docling_conversion/extract_text",
            "pdf_file",
            "pdf_file",
            garbage_pdf_bytes(),
            "application/pdf",
        ),
        (
            "/latest/decimer/extract_doi",
            "pdf_file",
            "pdf_file",
            garbage_pdf_bytes(),
            "application/pdf",
        ),
    ],
)
def test_pdf_upload_filename_cannot_escape_pdf_dir(
    client, fs_probe, path, field, filename_field, content, content_type
):
    canary = _canary_token()
    escape_name = f"../../../../tmp/{canary}.pdf"

    resp = client.post(
        path,
        files={field: (escape_name, content, content_type)},
    )

    # Whatever filename-mangling the handler does (uuid insertion, etc.),
    # the written file must stay inside PDF_DIR: it must not appear at
    # /tmp/<anything containing our canary token>.
    found = _find_canary_under(fs_probe, "/tmp", canary)
    for leaked_path in found:
        fs_probe.remove(leaked_path)
    assert not found, (
        f"{path} wrote a file outside its upload directory via filename "
        f"{escape_name!r}: found at {found} (response status "
        f"{resp.status_code})"
    )


def test_ocsr_upload_filename_cannot_escape_images_dir(client, fs_probe):
    canary = _canary_token()
    escape_name = f"../../../../tmp/{canary}.png"

    resp = client.post(
        "/latest/ocsr/generate_smiles",
        data={"engine": "decimer"},
        files={"image_file": (escape_name, minimal_png(), "image/png")},
        timeout=300,
    )

    found = _find_canary_under(fs_probe, "/tmp", canary)
    for leaked_path in found:
        fs_probe.remove(leaked_path)
    assert not found, (
        "ocsr upload wrote a file outside IMAGES_DIR via filename "
        f"{escape_name!r}: found at {found} (response status "
        f"{resp.status_code})"
    )


def _find_canary_under(fs_probe, directory: str, token: str) -> list[str]:
    """Shell out through the probe to list any file under `directory`
    (non-recursive is enough here: our traversal targets land directly in
    /tmp) whose name contains `token`."""
    import subprocess

    from fs_probe import DockerProbe

    if not isinstance(fs_probe, DockerProbe):
        raise RuntimeError(
            "test_upload_filename_traversal's canary search only knows how "
            "to list files through a DockerProbe; extend _find_canary_under "
            "for other probe backends."
        )

    r = subprocess.run(
        [
            "docker", "exec", fs_probe.container,
            "sh", "-c", f"ls -1 {directory} | grep {token} || true",
        ],
        capture_output=True, text=True,
    )
    names = [n for n in r.stdout.splitlines() if n.strip()]
    return [f"{directory}/{n}" for n in names]
