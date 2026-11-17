import threading

import pytest
from sqlalchemy import func, select

from marcus.core import storage
from marcus.core.db import get_sync_sessionmaker
from marcus.core.enums import Engine, ErrorClass
from marcus.core.models import Curation, Paper, Prediction, Segment, Step
from marcus.core.pipeline import (
    BadResult,
    cancel_paper,
    complete_step,
    fail_step,
    request_ocsr,
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
    paper = make_paper(s, engine=Engine.MOLNEXTR, ocsr_mode=mode)
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
    assert got == [
        ("ocsr", "molnextr", "q.molnextr", 2, 2000, segs[0].id),
        ("ocsr", "molnextr", "q.molnextr", 2, 2001, segs[1].id),
    ]


def test_ocsr_result_writes_prediction(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    ocsr1, _ = finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
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
                    pass
                ws.commit()
        except BaseException as exc:
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
    ocsr1, _ = finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
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
