import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from marcus.core import pipeline as pipeline_module
from marcus.core import storage
from marcus.core.db import get_sync_sessionmaker
from marcus.core.enums import Engine, ErrorClass
from marcus.core.models import Curation, DrawingFlag, Paper, Prediction, Segment, Step
from marcus.core.pipeline import (
    BadResult,
    RetryNotAllowed,
    cancel_paper,
    complete_step,
    fail_step,
    request_image_ocsr,
    request_ocsr,
    retry_page,
)
from tests.factories import make_image_job, make_paper

SEGS = [
    {"idx": 0, "bbox": [0, 0, 10, 10], "image_sha256": "0" * 64},
    {"idx": 1, "bbox": [5, 5, 50, 60], "image_sha256": "1" * 64},
]
SEG_V = "segv-test"
OCSR = {"smiles": "CCO", "molfile": None, "valid": True, "ms": 12, "engine_version": "2.7"}


def steps(s, paper, kind=None, status=None) -> list[Step]:
    q = select(Step).where(Step.paper_id == paper.id)
    if kind:
        q = q.where(Step.kind == kind)
    if status:
        q = q.where(Step.status == status)
    return list(s.execute(q.order_by(Step.seq)).scalars())


def run(s, step) -> Step:
    """What the runtime does when it starts a step."""
    step.status = "running"
    step.attempts += 1
    s.flush()
    return step


def finish(s, step, result) -> list[Step]:
    run(s, step)
    return complete_step(s, step.id, result)


def to_processing(s, paper, pages=2) -> list[Step]:
    (check,) = steps(s, paper, "check_pdf")
    return finish(s, check, {"pages": pages})


def own(paper, new: list[Step]) -> list[Step]:
    """The paper's own OCSR steps of `new` (its engine; the others read in the background)."""
    return [st for st in new if st.engine == paper.engine]


def count(s, model) -> int:
    return s.execute(select(func.count()).select_from(model)).scalar_one()


def test_check_pdf_creates_render_docling_doi(db_session):
    s = db_session
    paper = make_paper(s)
    new = to_processing(s, paper, pages=3)
    s.refresh(paper)
    assert paper.status == "processing" and paper.pages == 3
    got = sorted((st.kind, st.page, st.seq, st.queue, st.status) for st in new)
    assert got == [
        ("docling", None, 100000, "q.cpu", "pending"),
        ("doi", None, 100001, "q.cpu", "pending"),
        ("render_page", 0, 0, "q.cpu", "pending"),
        ("render_page", 1, 1, "q.cpu", "pending"),
        ("render_page", 2, 2, "q.cpu", "pending"),
    ]
    assert all(st.paper_id == paper.id for st in new)
    (check,) = steps(s, paper, "check_pdf")
    assert check.status == "done" and check.finished_at is not None


def test_render_creates_segment_step_for_same_page(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=2)
    render_p1 = steps(s, paper, "render_page")[1]
    new = finish(s, render_p1, {})
    assert [(st.kind, st.page, st.seq, st.queue) for st in new] == [
        ("segment_page", 1, 1, "q.segment")
    ]
    assert render_p1.status == "done"


@pytest.mark.parametrize("mode", ["auto", "off"])
def test_segment_creates_ocsr_steps_when_auto_and_none_when_off(db_session, mode):
    s = db_session
    paper = make_paper(s, engine=Engine.MOLPARSER, ocsr_mode=mode)
    to_processing(s, paper, pages=3)
    render_p2 = steps(s, paper, "render_page")[2]
    (seg_step,) = finish(s, render_p2, {})
    new = finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})

    segs = list(s.execute(select(Segment).order_by(Segment.idx)).scalars())
    assert [(g.paper_id, g.page, g.idx, g.bbox, g.image_sha256) for g in segs] == [
        (paper.id, 2, 0, [0, 0, 10, 10], "0" * 64),
        (paper.id, 2, 1, [5, 5, 50, 60], "1" * 64),
    ]
    curations = {c.segment_id: c.status for c in s.execute(select(Curation)).scalars()}
    assert curations == {g.id: "unchecked" for g in segs}

    if mode == "off":
        assert new == []
        return
    got = [(st.kind, st.engine, st.queue, st.page, st.seq, st.segment_id) for st in new]
    # the paper's engine, then the other two in the background (phase B item 3)
    assert got == [
        ("ocsr", "molparser", "q.molparser", 2, 2000, segs[0].id),
        ("ocsr", "decimer", "q.decimer", 2, 2000, segs[0].id),
        ("ocsr", "molscribe", "q.molscribe", 2, 2000, segs[0].id),
        ("ocsr", "molparser", "q.molparser", 2, 2001, segs[1].id),
        ("ocsr", "decimer", "q.decimer", 2, 2001, segs[1].id),
        ("ocsr", "molscribe", "q.molscribe", 2, 2001, segs[1].id),
    ]


def test_segment_page_stores_the_drawing_check(db_session):
    """A flagged segment gets its drawing_flags row; a clean one, or a result without the flag
    (an older worker), none."""
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    third = {"idx": 2, "bbox": [1, 1, 9, 9], "image_sha256": "2" * 64}
    items = [{**SEGS[0], "check_drawing": True}, {**SEGS[1], "check_drawing": False}, third]
    finish(s, seg_step, {"segments": items, "seg_version": SEG_V})
    flagged = s.execute(
        select(Segment.idx).join(DrawingFlag, DrawingFlag.segment_id == Segment.id)
    ).scalars()
    assert list(flagged) == [0]


def test_ocsr_result_stores_cached_flag(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    ocsr1, ocsr2 = own(paper, finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V}))
    finish(s, ocsr1, {**OCSR, "cached": True, "ms": 0})
    finish(s, ocsr2, OCSR)
    cached = {p.segment_id: p.cached for p in s.execute(select(Prediction)).scalars()}
    assert cached == {ocsr1.segment_id: True, ocsr2.segment_id: False}


def test_ocsr_result_writes_prediction(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    ocsr1, _ = own(paper, finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V}))
    assert finish(s, ocsr1, OCSR) == []
    (pred,) = s.execute(select(Prediction)).scalars()
    assert (pred.segment_id, pred.image_job_id, pred.engine) == (ocsr1.segment_id, None, "decimer")
    assert (pred.smiles, pred.molfile, pred.valid, pred.ms, pred.engine_version) == (
        "CCO",
        None,
        True,
        12,
        "2.7",
    )


def test_doi_and_docling_results(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (doi,) = steps(s, paper, "doi")
    (docling,) = steps(s, paper, "docling")
    assert finish(s, doi, {"doi": "10.1000/xyz"}) == []
    assert finish(s, docling, {"text_path": "text.json"}) == []
    s.refresh(paper)
    assert paper.doi == "10.1000/xyz"


def test_docling_stores_the_page_label_index(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=2)
    (docling,) = steps(s, paper, "docling")
    index = {"0": ["R1", "R2"], "1": ["X"]}
    assert finish(s, docling, {"text_path": "text.json", "rgroup_text_labels": index}) == []
    s.refresh(paper)
    assert paper.rgroup_text_labels == index


@pytest.mark.parametrize("bad", [{"2": ["R1"]}, {"0": ["OAc"]}, ["R1"], {"0": "R1"}])
def test_a_malformed_page_label_index_is_refused(db_session, bad):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=2)
    (docling,) = steps(s, paper, "docling")
    s.commit()
    run(s, docling)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, docling.id, {"text_path": "text.json", "rgroup_text_labels": bad})


def test_after_doi_stores_title(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (doi,) = steps(s, paper, "doi")
    finish(s, doi, {"doi": "10.1000/xyz", "title": "Coffea alkaloids"})
    s.refresh(paper)
    assert paper.title == "Coffea alkaloids"


def test_after_doi_stores_first_author_and_year(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (doi,) = steps(s, paper, "doi")
    finish(s, doi, {"doi": "10.1/x", "title": "T", "first_author": "Rajan", "year": 2025})
    s.refresh(paper)
    assert (paper.first_author, paper.year) == ("Rajan", 2025)


def test_after_doi_without_author_or_year_stores_null(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (doi,) = steps(s, paper, "doi")
    finish(s, doi, {"doi": "10.1/x", "title": "T"})
    s.refresh(paper)
    assert (paper.first_author, paper.year) == (None, None)


@pytest.mark.parametrize(
    "extra",
    [{"first_author": 5}, {"first_author": ["Rajan"]}, {"year": "2025"}, {"year": True},
     {"year": 2025.0}],
)  # fmt: skip
def test_check_doi_result_rejects_odd_author_or_year(extra):
    with pytest.raises(BadResult):
        pipeline_module._check_doi_result({"doi": None, **extra})


def test_check_doi_result_rejects_non_string_title():
    with pytest.raises(BadResult):
        pipeline_module._check_doi_result({"doi": None, "title": 5})


def test_check_doi_result_accepts_missing_title():
    pipeline_module._check_doi_result({"doi": "10.1/x"})
    pipeline_module._check_doi_result({"doi": None, "title": None})
    pipeline_module._check_doi_result(
        {"doi": "10.1/x", "title": "T", "first_author": None, "year": None}
    )
    pipeline_module._check_doi_result({"doi": "10.1/x", "first_author": "Rajan", "year": 2025})


def test_paper_done_when_last_step_finishes(db_session):
    s = db_session
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=1)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    s.refresh(paper)
    assert paper.status == "processing"
    finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
    s.refresh(paper)
    assert paper.status == "done"


def test_paper_done_when_some_pages_fail(db_session):
    s = db_session
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=2)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    r1, r2 = steps(s, paper, "render_page")
    run(s, r1)
    fail_step(s, r1.id, ErrorClass.BAD_INPUT, "broken page", retryable=False)
    (seg_step,) = finish(s, r2, {})
    finish(s, seg_step, {"segments": [], "seg_version": SEG_V})
    s.refresh(paper)
    assert paper.status == "done"


def test_paper_failed_when_all_pages_fail(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=2)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    for r in steps(s, paper, "render_page"):
        run(s, r)
        fail_step(s, r.id, ErrorClass.BAD_INPUT, "broken page", retryable=False)
    s.refresh(paper)
    assert paper.status == "failed"
    assert paper.error


def test_paper_failed_when_segmentation_fails_on_every_page(db_session):
    """Spec §8: a paper is failed if all pages fail; a page whose segmentation failed is a
    failed page (not `done` with zero structures)."""
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=2)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    for r in steps(s, paper, "render_page"):
        (seg_step,) = finish(s, r, {})
        run(s, seg_step)
        fail_step(s, seg_step.id, ErrorClass.ENGINE_ERROR, "segmenter crashed", retryable=False)
    s.refresh(paper)
    assert paper.status == "failed"
    assert paper.error == "all pages failed (render or segmentation)"


def test_paper_failed_when_pages_fail_by_render_and_by_segmentation(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=2)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    r1, r2 = steps(s, paper, "render_page")
    run(s, r1)
    fail_step(s, r1.id, ErrorClass.BAD_INPUT, "broken page", retryable=False)
    (seg_step,) = finish(s, r2, {})
    run(s, seg_step)
    fail_step(s, seg_step.id, ErrorClass.WORKER_LOST, "lost", retryable=False)
    s.refresh(paper)
    assert paper.status == "failed" and paper.error


def test_paper_done_when_one_page_segments(db_session):
    s = db_session
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=2)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    r1, r2 = steps(s, paper, "render_page")
    (seg1,) = finish(s, r1, {})
    run(s, seg1)
    fail_step(s, seg1.id, ErrorClass.ENGINE_ERROR, "segmenter crashed", retryable=False)
    (seg2,) = finish(s, r2, {})
    finish(s, seg2, {"segments": [], "seg_version": SEG_V})  # a page with no structures is ok
    s.refresh(paper)
    assert paper.status == "done"


def test_paper_failed_when_check_pdf_fails(db_session):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    run(s, check)
    fail_step(s, check.id, ErrorClass.BAD_INPUT, "PDF is encrypted", retryable=False)
    s.refresh(paper)
    assert paper.status == "failed"
    assert paper.error == "PDF is encrypted"
    assert check.status == "failed" and check.error_class == "bad_input"


def test_fail_retries_once_then_final(db_session):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    run(s, check)  # attempts = 1
    check.queued_at = check.started_at = func.now()
    s.flush()
    fail_step(s, check.id, ErrorClass.TIMEOUT, "soft time limit", retryable=True)
    s.refresh(check)
    s.refresh(paper)
    assert check.status == "pending" and check.attempts == 1
    assert check.started_at is None and check.queued_at is None and check.finished_at is None
    assert (check.error_class, check.error) == ("timeout", "soft time limit")
    assert paper.status == "checking"

    run(s, check)  # attempts = 2
    fail_step(s, check.id, ErrorClass.WORKER_LOST, "worker died", retryable=True)
    s.refresh(check)
    s.refresh(paper)
    assert check.status == "failed" and check.finished_at is not None
    assert (check.error_class, check.error) == ("worker_lost", "worker died")
    assert paper.status == "failed"


def test_fail_not_retryable_is_final_on_first_attempt(db_session):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    run(s, check)
    fail_step(s, check.id, ErrorClass.BAD_INPUT, "not a pdf", retryable=False)
    s.refresh(check)
    assert check.status == "failed"


def test_complete_twice_is_noop(db_session):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    assert len(finish(s, check, {"pages": 1})) == 3
    assert complete_step(s, check.id, {"pages": 1}) == []
    assert len(steps(s, paper)) == 4


def test_delete_while_running_cancels_and_drops_late_result(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    run(s, seg_step)
    assert storage.paper_dir(paper.id).is_dir()

    cancel_paper(s, paper.id)
    s.commit()
    s.refresh(paper)
    assert paper.status == "deleted"
    assert not storage.paper_dir(paper.id).exists()
    by_kind = {st.kind: st.status for st in steps(s, paper)}
    assert by_kind == {
        "check_pdf": "done",
        "render_page": "done",
        "segment_page": "cancelled",
        "docling": "cancelled",
        "doi": "cancelled",
    }

    assert complete_step(s, seg_step.id, {"segments": SEGS, "seg_version": SEG_V}) == []
    s.refresh(seg_step)
    s.refresh(paper)
    assert seg_step.status == "cancelled"
    assert paper.status == "deleted"
    assert count(s, Segment) == 0 and count(s, Curation) == 0
    assert count(s, Step) == 5
    # a late failure is dropped too
    fail_step(s, seg_step.id, ErrorClass.TIMEOUT, "late", retryable=True)
    s.refresh(seg_step)
    assert seg_step.status == "cancelled"


def test_cancel_paper_with_missing_dir(db_session):
    s = db_session
    paper = make_paper(s)
    storage.pdf_path(paper.id).unlink()
    storage.paper_dir(paper.id).rmdir()
    cancel_paper(s, paper.id)
    s.refresh(paper)
    assert paper.status == "deleted"


def test_cancel_paper_file_error_is_logged_not_raised(db_session, monkeypatch, caplog):
    s = db_session
    paper = make_paper(s)
    s.commit()

    def denied(path, *a, **kw):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(pipeline_module.shutil, "rmtree", denied)
    with caplog.at_level("WARNING", logger="marcus.core.pipeline"):
        cancel_paper(s, paper.id)
    s.commit()  # the transaction is intact
    s.refresh(paper)
    assert paper.status == "deleted"
    assert {st.status for st in steps(s, paper)} == {"cancelled"}
    assert str(paper.id) in caplog.text and "PermissionError" in caplog.text


def test_ocsr_result_stores_rgroup_labels(db_session):
    """The labels are computed once, with the row: [] for a plain structure, the labels for a
    scaffold (MolScribe's dummy atoms, DECIMER's R tokens that make it invalid)."""
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    ocsr1, ocsr2 = own(paper, finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V}))
    finish(s, ocsr1, {**OCSR, "smiles": "[1*]c1ccccc1[2*]"})
    finish(s, ocsr2, {**OCSR, "smiles": "[R1]c1ccccc1", "valid": False})
    got = {p.segment_id: p.rgroups for p in s.execute(select(Prediction)).scalars()}
    assert got == {ocsr1.segment_id: ["R1", "R2"], ocsr2.segment_id: ["R1"]}


def test_ocsr_result_plain_structure_has_no_rgroups(db_session):
    s = db_session
    job, step = make_image_job(s, engine=Engine.MOLSCRIBE)
    finish(s, step, OCSR)
    (pred,) = s.execute(select(Prediction)).scalars()
    assert pred.rgroups == []


def test_image_job_ocsr_done(db_session):
    s = db_session
    job, step = make_image_job(s, engine=Engine.MOLSCRIBE)
    assert finish(s, step, OCSR) == []
    s.refresh(job)
    assert job.status == "done"
    (pred,) = s.execute(select(Prediction)).scalars()
    assert (pred.image_job_id, pred.segment_id, pred.engine) == (job.id, None, "molscribe")


def test_image_job_ocsr_failed_after_retry(db_session):
    s = db_session
    job, step = make_image_job(s)
    run(s, step)
    fail_step(s, step.id, ErrorClass.TIMEOUT, "slow", retryable=True)
    s.refresh(job)
    assert job.status == "queued" and step.status == "pending"
    run(s, step)
    fail_step(s, step.id, ErrorClass.ENGINE_ERROR, "boom", retryable=True)
    s.refresh(job)
    assert job.status == "failed" and job.error == "boom"
    assert count(s, Prediction) == 0


def _done_paper_with_segment(s):
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=1)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
    s.refresh(paper)
    assert paper.status == "done"
    seg = s.execute(select(Segment).where(Segment.idx == 1)).scalar_one()
    return paper, seg


def test_request_ocsr_creates_step_and_reopens_done_paper(db_session):
    s = db_session
    paper, seg = _done_paper_with_segment(s)
    step = request_ocsr(s, seg.id, Engine.MOLSCRIBE)
    assert (step.kind, step.engine, step.queue, step.status) == (
        "ocsr",
        "molscribe",
        "q.molscribe",
        "pending",
    )
    assert (step.paper_id, step.segment_id, step.page, step.seq) == (paper.id, seg.id, 0, 1)
    s.refresh(paper)
    assert paper.status == "processing"
    finish(s, step, OCSR)
    s.refresh(paper)
    assert paper.status == "done"


def test_request_ocsr_refuses_deleted_paper_and_fake_engine(db_session):
    s = db_session
    paper, seg = _done_paper_with_segment(s)
    with pytest.raises(ValueError):
        request_ocsr(s, seg.id, Engine.FAKE)
    cancel_paper(s, paper.id)
    with pytest.raises(ValueError):
        request_ocsr(s, seg.id, Engine.DECIMER)


def test_concurrent_last_two_steps_mark_paper_done(db_session):
    """Two workers finish the last two steps at once; the paper must still end `done`."""
    s = db_session
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    finish(s, seg_step, {"segments": [], "seg_version": SEG_V})
    last = [run(s, st) for st in steps(s, paper, "doi") + steps(s, paper, "docling")]
    s.commit()

    results = {"doi": {"doi": None}, "docling": {"text_path": "text.json"}}
    # Both threads wait here after complete_step and before commit. With the paper lock the
    # second thread blocks inside complete_step, so the barrier times out and the first commits.
    barrier = threading.Barrier(2, timeout=1.5)
    errors: list[BaseException] = []

    def worker(step_id, kind):
        try:
            with get_sync_sessionmaker()() as ws:
                complete_step(ws, step_id, results[kind])
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass  # the other thread never arrived: commit anyway, the asserts judge it
                ws.commit()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(st.id, st.kind)) for st in last]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    s.expire_all()
    assert s.get(Paper, paper.id).status == "done"
    assert {st.status for st in steps(s, paper)} == {"done"}


def _assert_untouched(s, step_id):
    """BadResult is raised before any change: nothing pending in the session, then roll back."""
    assert not s.new and not s.dirty and not s.deleted
    s.rollback()
    st = s.get(Step, step_id)
    assert st.status == "running" and st.finished_at is None


GOOD_SEG = {"idx": 0, "bbox": [0, 0, 10, 10], "image_sha256": "0" * 64}


@pytest.mark.parametrize(
    "result",
    [
        {
            "segments": [GOOD_SEG, {"idx": 1, "bbox": [0, 0, 1], "image_sha256": "1" * 64}],
            "seg_version": SEG_V,
        },
        {"segments": [GOOD_SEG, {**GOOD_SEG}], "seg_version": SEG_V},  # duplicate idx
        {"segments": [{**GOOD_SEG, "idx": 1000}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "idx": True}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "idx": "0"}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "bbox": [0, 0, 1.5, 2]}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "bbox": [0, -1, 1, 2]}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "image_sha256": "0" * 65}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "image_sha256": "G" * 64}], "seg_version": SEG_V},
        {"segments": [{"idx": 0, "bbox": [0, 0, 1, 1]}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "check_drawing": "yes"}], "seg_version": SEG_V},
        {"segments": [{**GOOD_SEG, "check_drawing": 1}], "seg_version": SEG_V},
        {"segments": "nope", "seg_version": SEG_V},
        {"segments": [GOOD_SEG]},  # no seg_version
        {"segments": [GOOD_SEG], "seg_version": ""},
        {"segments": [GOOD_SEG], "seg_version": "v" * 201},
        {},
        None,
    ],
)
def test_malformed_segment_page_result_changes_nothing(db_session, result):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    run(s, seg_step)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, seg_step.id, result)
    _assert_untouched(s, seg_step.id)
    assert count(s, Segment) == 0 and count(s, Curation) == 0
    assert steps(s, paper, "ocsr") == []
    s.refresh(paper)
    assert paper.status == "processing"
    # the runtime then records the failure in a fresh transaction
    fail_step(s, seg_step.id, ErrorClass.BAD_INPUT, "bad result", retryable=False)
    assert seg_step.status == "failed"


@pytest.mark.parametrize(
    "bad",
    [
        {"smiles": None},
        {"smiles": "C\x00C"},
        {"valid": 1},
        {"valid": "yes"},
        {"ms": "12"},
        {"ms": -1},
        {"ms": 2**31},
        {"ms": True},
        {"molfile": 5},
        {"engine_version": ""},
        {"engine_version": None},
    ],
)
def test_malformed_ocsr_result_changes_nothing(db_session, bad):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    ocsr1, _ = own(paper, finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V}))
    run(s, ocsr1)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, ocsr1.id, {**OCSR, **bad})
    _assert_untouched(s, ocsr1.id)
    assert count(s, Prediction) == 0


def test_malformed_image_job_result_leaves_job(db_session):
    s = db_session
    job, step = make_image_job(s)
    run(s, step)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, step.id, {**OCSR, "valid": "true"})
    _assert_untouched(s, step.id)
    s.refresh(job)
    assert job.status == "queued" and count(s, Prediction) == 0


@pytest.mark.parametrize("pages", [0, 101, -1, "3", 2.0, True, None])
def test_malformed_check_pdf_pages_changes_nothing(db_session, pages):
    s = db_session
    paper = make_paper(s)
    (check,) = steps(s, paper, "check_pdf")
    run(s, check)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, check.id, {"pages": pages})
    _assert_untouched(s, check.id)
    s.refresh(paper)
    assert paper.status == "checking" and paper.pages is None
    assert len(steps(s, paper)) == 1


@pytest.mark.parametrize("result", [{}, {"doi": 123}, {"doi": ["10.1/x"]}])
def test_malformed_doi_result_changes_nothing(db_session, result):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (doi,) = steps(s, paper, "doi")
    run(s, doi)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, doi.id, result)
    _assert_untouched(s, doi.id)


def test_bad_result_is_a_value_error():
    assert issubclass(BadResult, ValueError)


def test_request_image_ocsr_reopens_done_job(db_session):
    s = db_session
    job, step = make_image_job(s)
    finish(s, step, OCSR)
    s.refresh(job)
    assert job.status == "done"
    new = request_image_ocsr(s, job.id, Engine.MOLPARSER)
    s.refresh(job)
    assert job.status == "queued"
    assert (new.kind, new.engine, new.status, new.image_job_id, new.seq) == (
        "ocsr",
        "molparser",
        "pending",
        job.id,
        1,
    )
    finish(s, new, OCSR)
    s.refresh(job)
    assert job.status == "done"


def test_request_image_ocsr_refuses_deleted_and_unknown(db_session):
    import uuid

    s = db_session
    job, _ = make_image_job(s)
    job.status = "deleted"
    s.flush()
    with pytest.raises(ValueError):
        request_image_ocsr(s, job.id, Engine.DECIMER)
    with pytest.raises(ValueError):
        request_image_ocsr(s, uuid.uuid4(), Engine.DECIMER)


# --- retry_page ----------------------------------------------------------------------------


def _paper_with_failed_page(s, pages=1, fail="render"):
    """A paper whose page 0 failed for good (render or segment_page); other pages succeed."""
    paper = make_paper(s)
    to_processing(s, paper, pages=pages)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    for r in steps(s, paper, "render_page"):
        if r.page == 0:
            if fail == "render":
                run(s, r)
                fail_step(s, r.id, ErrorClass.BAD_INPUT, "broken", retryable=False)
            else:
                (seg_step,) = finish(s, r, {})
                run(s, seg_step)
                fail_step(s, seg_step.id, ErrorClass.ENGINE_ERROR, "crash", retryable=False)
        else:
            (seg_step,) = finish(s, r, {})
            finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
    s.refresh(paper)
    return paper


def test_retry_page_reopens_failed_paper(db_session):
    s = db_session
    paper = _paper_with_failed_page(s)
    assert paper.status == "failed"
    step = retry_page(s, paper.id, 0)
    assert (step.kind, step.page, step.status, step.queue) == ("render_page", 0, "pending", "q.cpu")
    s.refresh(paper)
    assert (paper.status, paper.error) == ("processing", None)


def test_retry_page_after_segment_failure_and_success_finishes_done(db_session):
    s = db_session
    paper = _paper_with_failed_page(s, fail="segment")
    step = retry_page(s, paper.id, 0)
    (seg_step,) = finish(s, step, {})
    ocsr = finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
    s.refresh(paper)
    assert paper.status == "processing"
    for o in ocsr:
        finish(s, o, OCSR)
    s.refresh(paper)
    assert paper.status == "done"


def test_retry_page_refusals(db_session):
    s = db_session
    paper = _paper_with_failed_page(s, pages=2)
    with pytest.raises(RetryNotAllowed) as e:
        retry_page(s, paper.id, 1)  # page 1 succeeded
    assert e.value.reason == "not_failed"
    retry_page(s, paper.id, 0)
    with pytest.raises(RetryNotAllowed) as e:
        retry_page(s, paper.id, 0)  # the retry is pending
    assert e.value.reason == "busy"
    (r,) = steps(s, paper, "render_page", "pending")
    run(s, r)
    fail_step(s, r.id, ErrorClass.BAD_INPUT, "again", retryable=False)
    retry_page(s, paper.id, 0)  # second manual retry
    (r,) = steps(s, paper, "render_page", "pending")
    run(s, r)
    fail_step(s, r.id, ErrorClass.BAD_INPUT, "again", retryable=False)
    with pytest.raises(RetryNotAllowed) as e:
        retry_page(s, paper.id, 0)
    assert e.value.reason == "limit"


def test_retry_page_missing_deleted_or_out_of_range(db_session):
    s = db_session
    paper = _paper_with_failed_page(s)
    with pytest.raises(ValueError):
        retry_page(s, paper.id, 1)
    with pytest.raises(ValueError):
        retry_page(s, paper.id, -1)
    paper.status = "deleted"
    s.flush()
    with pytest.raises(ValueError):
        retry_page(s, paper.id, 0)


# --- the address kept on active work (review I-1) ------------------------------------------


def _just_now(when) -> bool:
    return when is not None and abs(datetime.now(UTC) - when) < timedelta(minutes=1)


def _paper_from(s, ip="198.51.100.7") -> Paper:
    paper = make_paper(s)
    paper.started_ip = ip
    s.flush()
    return paper


def test_new_paper_and_image_job_keep_the_starting_address(db_session):
    from marcus.core.pipeline import new_image_job, new_paper
    from tests.factories import make_owner

    s = db_session
    owner = make_owner(s)
    paper = new_paper(s, owner, "a" * 64, 9, "p.pdf", Engine.DECIMER, "auto",
                      started_ip="203.0.113.9")  # fmt: skip
    job = new_image_job(s, owner, "b" * 64, "i.png", Engine.DECIMER,
                        started_ip="2001:db8::/64")  # fmt: skip
    assert (paper.started_ip, job.started_ip) == ("203.0.113.9", "2001:db8::/64")
    assert _just_now(paper.started_ip_at) and _just_now(job.started_ip_at)
    plain = new_paper(s, owner, "c" * 64, 9, "q.pdf", Engine.DECIMER, "auto")
    assert plain.started_ip is None and plain.started_ip_at is None


def test_a_paper_that_ends_keeps_no_address(db_session):
    s = db_session
    failed = _paper_from(s)
    (check,) = steps(s, failed, "check_pdf")
    run(s, check)
    fail_step(s, check.id, ErrorClass.BAD_INPUT, "not a pdf", retryable=False)
    s.refresh(failed)
    assert failed.status == "failed" and failed.started_ip is None
    assert failed.started_ip_at is None

    deleted = _paper_from(s)
    cancel_paper(s, deleted.id, remove_files=False)
    assert deleted.started_ip is None and deleted.started_ip_at is None


def test_a_settled_image_job_keeps_no_address(db_session):
    s = db_session
    job, step = make_image_job(s)
    job.started_ip = "198.51.100.8"
    s.flush()
    finish(s, step, OCSR)
    s.refresh(job)
    assert job.status == "done" and job.started_ip is None and job.started_ip_at is None
    request_image_ocsr(s, job.id, Engine.MOLPARSER, started_ip="198.51.100.9")
    assert job.status == "queued" and job.started_ip == "198.51.100.9"  # active again
    assert _just_now(job.started_ip_at)


def test_reopened_paper_gets_the_requesting_address(db_session):
    s = db_session
    paper = _paper_from(s)
    paper.status = "done"
    paper.started_ip = None
    s.add(Segment(paper_id=paper.id, page=0, idx=0, bbox=[0, 0, 1, 1], image_sha256="0" * 64))
    s.flush()
    seg = s.execute(select(Segment).where(Segment.paper_id == paper.id)).scalar_one()
    paper.created_at = datetime.now(UTC) - timedelta(days=40)  # an old paper, reopened now
    request_ocsr(s, seg.id, Engine.DECIMER, started_ip="203.0.113.77")
    assert paper.status == "processing" and paper.started_ip == "203.0.113.77"
    assert _just_now(paper.started_ip_at)  # the purge goes by this, not by created_at


def test_an_ocsr_request_while_one_waits_gets_it_back(db_session):
    """Repeat requests (Compare closed and opened again before the steps came back, two tabs)
    never queue a second step of one engine for one segment: the planner returns the waiting
    one, under the paper's lock, so two requests at once cannot both add one."""
    s = db_session
    paper = _paper_from(s)
    s.add(Segment(paper_id=paper.id, page=0, idx=0, bbox=[0, 0, 1, 1], image_sha256="0" * 64))
    s.flush()
    seg = s.execute(select(Segment).where(Segment.paper_id == paper.id)).scalar_one()
    first = request_ocsr(s, seg.id, Engine.MOLPARSER)
    assert request_ocsr(s, seg.id, Engine.MOLPARSER).id == first.id
    other = request_ocsr(s, seg.id, Engine.MOLSCRIBE)
    assert other.id != first.id
    run(s, first)
    assert request_ocsr(s, seg.id, Engine.MOLPARSER).id == first.id  # running counts too
    complete_step(s, first.id, OCSR)
    assert request_ocsr(s, seg.id, Engine.MOLPARSER).id != first.id  # ended: a new run


def test_an_image_ocsr_request_while_one_waits_gets_it_back(db_session):
    s = db_session
    job, step = make_image_job(s)
    first = request_image_ocsr(s, job.id, Engine.MOLPARSER)
    assert request_image_ocsr(s, job.id, Engine.MOLPARSER).id == first.id
    assert request_image_ocsr(s, job.id, Engine.DECIMER).id == step.id  # the job's own, waiting
