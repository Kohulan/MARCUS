"""v1 claim 3 on v2: the OCSR input must not be an existence oracle.

v1: POST /latest/ocsr/generate_smiles took an `image_path` form field and opened ANY existing
path (/etc/hostname -> 500 "cannot identify image file", a missing path -> 404).

v2 OCSR input is server-owned only:
    POST /api/v2/segments/{segment_id}/predictions   {"engine": ...}  (a crop of my paper)
    POST /api/v2/images                              multipart `file` (bytes, never a path)
Safe behaviour: a segment of another owner gets the byte-identical 404 as a random id, and an
`image_path` form field is ignored: an existing and a missing path give identical answers, both
at upload time and in the job's OUTCOME (OCSR runs asynchronously; `GET /api/v2/images/{id}`
is where an oracle would show), and both outcomes equal a plain upload of the same image.
"""
from __future__ import annotations

import uuid

from v2.helpers import API, describe, expect_ok, post_image, random_id, same_answer, wait_image


def test_ocsr_image_path_is_not_an_existence_oracle(shared_paper, new_owner, fs_probe):
    sp = shared_paper()
    sid = sp.segment_ids[0]
    resp = expect_ok(sp.owner.post(f"{API}/segments/{sid}/predictions", json={"engine": "fake"}),
                     "POST /api/v2/segments/{id}/predictions")
    assert "step_id" in resp.json()

    existing, missing = "/etc/hostname", f"/etc/judge-missing-{uuid.uuid4().hex}"
    assert fs_probe.exists(existing) and not fs_probe.exists(missing)

    oracles = []
    stranger = new_owner()
    a = stranger.post(f"{API}/segments/{sid}/predictions", json={"engine": "fake"})
    b = stranger.post(f"{API}/segments/{random_id()}/predictions", json={"engine": "fake"})
    if not (same_answer(a, b) and a.status_code == 404):
        oracles.append(f"other owner's segment {describe(a)} vs random id {describe(b)}")

    # v1's field on the v2 upload route, without a file: same rejection either way.
    a = stranger.post(f"{API}/images", data={"engine": "fake", "image_path": existing})
    b = stranger.post(f"{API}/images", data={"engine": "fake", "image_path": missing})
    if not same_answer(a, b):
        oracles.append(f"image_path without file: {describe(a)} vs {describe(b)}")

    # ... and next to a real file: the field is ignored. The upload answers AND the finished
    # jobs must match a plain upload of the same image (status, prediction, error).
    jobs = {}
    for label, extra in (("plain", None), ("existing", {"image_path": existing}),
                         ("missing", {"image_path": missing})):
        uploader = new_owner()  # one owner each: the active-work limits stay out of it
        resp = post_image(uploader, extra=extra)
        if resp.status_code != 202:
            oracles.append(f"image_path {label} upload: {describe(resp)}")
            continue
        jobs[label] = (uploader, resp.json()["image_job_id"])

    def outcome(job: dict) -> tuple:
        pred = job["prediction"] or {}
        return (job["status"], job["error"], job["engine"], pred.get("smiles"),
                pred.get("molfile"), pred.get("valid"), pred.get("engine_version"))

    outcomes = {label: outcome(wait_image(uploader, job_id))
                for label, (uploader, job_id) in jobs.items()}
    if outcomes.get("plain", (None,))[0] != "done":
        oracles.append(f"plain upload did not finish as done: {outcomes.get('plain')}")
    for label in ("existing", "missing"):
        if label in outcomes and outcomes[label] != outcomes.get("plain"):
            oracles.append(f"image_path {label}: job outcome {outcomes[label]} differs from a "
                           f"plain upload {outcomes.get('plain')}")

    assert not oracles, f"the v2 OCSR input leaks existence: {oracles}"
