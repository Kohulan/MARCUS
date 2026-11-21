"""Claim 4: GET /latest/decimer/get_highlighted_page/{segment_filename}
joins the `pdf_filename` query parameter straight onto PDF_DIR with no
traversal check at all (unlike the sibling get_segment_image, which at
least checks for ".."):

    pdf_path = os.path.join(PDF_DIR, pdf_filename)   # no ".." / absolute check
    if not os.path.exists(pdf_path): ... 404
    ...
    pdf_document = fitz.open(pdf_path)               # 500 if it exists but isn't a PDF

Evidence: backend/app/modules/decimer_segmentation_wrapper.py:402-499
(get_highlighted_segment_image), specifically line 477.

Observed live on this build:
  pdf_filename=../../../../etc/passwd         -> HTTP 500
    {"detail":"Error creating highlighted segment image: Failed to open
    file '/app/uploads/pdfs/../../../../etc/passwd'."}
  pdf_filename=../../../../etc/<nonexistent>  -> HTTP 404
    {"detail":"PDF file not found: ../../../../etc/<nonexistent>"}

The 500 response even echoes the resolved, traversed absolute path,
confirming the escape. This is a filesystem-existence oracle for anything
reachable by `../` from PDF_DIR, and a full read (rendered back as a PNG)
of any file elsewhere on disk that happens to be a valid PDF.

Safe behaviour under test: a `pdf_filename` containing `../` gets the same
rejection whether or not the traversed-to path exists.
"""
from __future__ import annotations

import uuid

# Must match the handler's own filename-format regex
# (page_(\d+)_(\d+)_segmented\.png) to get past that check and reach the
# vulnerable pdf_filename handling.
VALID_SEGMENT_FILENAME = "page_0_0_segmented.png"


def test_highlighted_page_pdf_filename_is_not_an_existence_oracle(client, fs_probe):
    existing_outside_path = "../../../../etc/hostname"
    assert fs_probe.exists("/etc/hostname")

    missing_relative = f"../../../../etc/judge-missing-{uuid.uuid4().hex}"
    assert not fs_probe.exists(f"/etc/judge-missing-shouldnotexist-{uuid.uuid4().hex}")

    resp_existing = client.get(
        f"/latest/decimer/get_highlighted_page/{VALID_SEGMENT_FILENAME}",
        params={"pdf_filename": existing_outside_path},
    )
    resp_missing = client.get(
        f"/latest/decimer/get_highlighted_page/{VALID_SEGMENT_FILENAME}",
        params={"pdf_filename": missing_relative},
    )

    assert resp_existing.status_code == resp_missing.status_code, (
        "get_highlighted_page's pdf_filename leaks filesystem existence "
        "outside PDF_DIR via '../': an existing-but-outside-PDF_DIR path "
        f"got {resp_existing.status_code} ({resp_existing.text[:200]!r}) "
        f"while a nonexistent one got {resp_missing.status_code} "
        f"({resp_missing.text[:200]!r})"
    )
