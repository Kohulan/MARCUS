"""v1 claim 2 on v2: an upload's client filename never becomes part of a filesystem path.

v1: three upload endpoints wrote `../../../../tmp/<name>` outside their upload folder:
    /latest/docling_conversion/extract_text, /latest/decimer/extract_doi (PDF) and the OCSR
    image upload.

v2 has one PDF upload (POST /api/v2/papers: the API stores source.pdf, then check_pdf, render,
docling (text) and doi run as worker steps) and one image upload (POST /api/v2/images). The
client filename is only a display label (`sanitize_display_name`); files live at
/data/papers/<uuid>/... and /data/images/<uuid>.png.

Safe behaviour: after the upload (and, for the full-pipeline cases, after every step has run),
no file or directory whose name carries the canary token exists under /tmp or /data in the API
container (/data is the volume every worker shares), and the display name is a bare basename.
"""
from __future__ import annotations

import uuid

import pytest
from payloads import garbage_pdf_bytes

from v2.helpers import (
    API,
    expect_ok,
    find_names,
    judge_pdf,
    upload_image,
    upload_paper,
    wait_image,
    wait_paper,
)


def _canary() -> str:
    return f"judge_traversal_{uuid.uuid4().hex[:8]}"


def _escape_names(canary: str, ext: str) -> list[str]:
    return [
        f"../../../../tmp/{canary}{ext}",
        f"/tmp/{canary}{ext}",
        f"..\\..\\..\\..\\tmp\\{canary}{ext}",
        f"../../../../data/{canary}{ext}",
    ]


@pytest.mark.parametrize(
    "case",
    [
        # v1 /latest/docling_conversion/extract_text: the API's own write of the upload
        "store-upload",
        # v1 /latest/decimer/extract_doi: the full pipeline, doi + docling steps included
        "doi-pipeline",
    ],
)
def test_pdf_upload_filename_cannot_escape_pdf_dir(new_owner, fs_probe, case):
    canary = _canary()
    data = garbage_pdf_bytes() if case == "store-upload" else judge_pdf("Judge traversal probe.")
    uploads = []
    for escape_name in _escape_names(canary, ".pdf"):
        owner = new_owner()  # one paper per owner: the 3-active-papers limit stays out of it
        uploads.append((escape_name, owner, upload_paper(owner, filename=escape_name, data=data)))

    leaked, bad_names = [], []
    for escape_name, owner, pid in uploads:
        detail = wait_paper(owner, pid)
        if case == "doi-pipeline":
            assert detail["status"] == "done", f"pipeline did not finish: {detail}"
            steps = expect_ok(owner.get(f"{API}/papers/{pid}/steps"), "GET .../steps").json()
            kinds = {s["kind"] for s in steps["steps"]}
            assert {"check_pdf", "doi", "docling"} <= kinds, kinds
        name = detail["display_name"]
        if "/" in name or "\\" in name or ".." in name:
            bad_names.append((escape_name, name))
    leaked += find_names(fs_probe, canary)

    for path in leaked:
        fs_probe.remove(path)
    assert not leaked, f"POST /api/v2/papers ({case}) wrote outside the data layout: {leaked}"
    assert not bad_names, f"display_name kept path parts: {bad_names}"


def test_ocsr_upload_filename_cannot_escape_images_dir(new_owner, fs_probe):
    canary = _canary()
    leaked, bad_names = [], []
    for escape_name in _escape_names(canary, ".png"):
        owner = new_owner()
        job_id = upload_image(owner, filename=escape_name)
        body = wait_image(owner, job_id)
        assert body["status"] == "done", f"image job did not finish: {body}"
        name = body["display_name"]
        if "/" in name or "\\" in name or ".." in name:
            bad_names.append((escape_name, name))
        leaked += find_names(fs_probe, canary)

    for path in leaked:
        fs_probe.remove(path)
    assert not leaked, f"POST /api/v2/images wrote outside the data layout: {leaked}"
    assert not bad_names, f"display_name kept path parts: {bad_names}"
