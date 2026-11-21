"""Claim 6: no auth anywhere in the session-management or listing
endpoints.

  * POST /session/reset and POST|DELETE /session/remove/{session_id}
    (backend/app/routers/session_router.py:226-233, 293-324) take no
    credential at all: `reset_all_sessions` resets every active session
    and the waiting queue for all users, and `remove_session` deletes
    whatever `session_id` it's given -- there's no check that the caller
    created it, or even knows anything about it beyond the id itself.
  * list_pdfs (docling_conversion.py:197-227), list_segments
    (decimer_segmentation.py:260-322), list_extractions and get_extraction
    (open_ai_annotation.py:222-328) iterate the shared upload directory and
    return every file to any caller, with no per-session/per-user
    filtering at all.

Safe behaviour under test:
  - a session created by one client cannot be torn down by a second,
    unrelated client that presents no credential for it;
  - a global "reset everyone" action requires some credential;
  - a file written by one client's upload is not visible to a second,
    completely unrelated client with no session/auth of its own.
"""
from __future__ import annotations

import httpx


def test_session_cannot_be_removed_by_an_unrelated_caller(backend):
    with httpx.Client(base_url=backend, timeout=30) as owner:
        created = owner.post(
            "/session/create", params={"user_id": "judge_owner"}
        ).json()
    session_id = created["session"]["session_id"]

    # A second client, sharing nothing with the owner (no cookie, no
    # header, no prior knowledge beyond the bare session id -- which is
    # the only thing the vulnerable endpoint checks).
    with httpx.Client(base_url=backend, timeout=30) as attacker:
        remove_resp = attacker.delete(f"/session/remove/{session_id}")
        status_resp = attacker.get(f"/session/status/{session_id}")

    removed = remove_resp.status_code == 200 and remove_resp.json().get("success")
    now_gone = status_resp.status_code == 404

    assert not (removed and now_gone), (
        "An unrelated caller with no credential for the session was able "
        f"to remove session {session_id!r} created by someone else "
        f"(remove status {remove_resp.status_code}: {remove_resp.text[:150]!r}; "
        f"status afterwards: {status_resp.status_code})"
    )


def test_global_session_reset_requires_a_credential(client):
    resp = client.post("/session/reset")

    assert resp.status_code in (401, 403), (
        "POST /session/reset (which tears down every active session and "
        "the waiting queue for ALL users) accepted a request with no "
        f"credential at all: status {resp.status_code}, body "
        f"{resp.text[:200]!r}"
    )


def test_uploaded_pdf_is_not_listed_to_an_unrelated_caller(backend, fs_probe):
    import uuid

    from payloads import garbage_pdf_bytes

    marker = f"judge_listing_probe_{uuid.uuid4().hex[:10]}.pdf"

    with httpx.Client(base_url=backend, timeout=120) as uploader:
        up = uploader.post(
            "/latest/docling_conversion/extract_text",
            files={"pdf_file": (marker, garbage_pdf_bytes(), "application/pdf")},
        )
        # The handler writes the file before it tries (and, for garbage
        # bytes, fails) to parse it as a PDF -- we only need the write to
        # have happened, not the extraction to succeed.
        assert up.status_code in (200, 500), (
            f"unexpected upload status {up.status_code}: {up.text[:200]!r}"
        )

    try:
        # A second, completely unrelated caller: no cookie, no
        # X-Session-ID header, no query-param session id of any kind.
        with httpx.Client(base_url=backend, timeout=30) as stranger:
            listing = stranger.get("/latest/docling_conversion/list_pdfs")

        names = {f["filename"] for f in listing.json().get("pdf_files", [])}
        assert marker not in names, (
            "list_pdfs exposed a file uploaded by a different, unrelated "
            f"caller to someone presenting no session/auth at all: {marker!r} "
            f"was in the anonymous listing of {len(names)} files"
        )
    finally:
        fs_probe.remove(f"/app/uploads/pdfs/{marker}")
