"""The planner's annotate step: request_annotation, its result, failures and deletion."""

import pytest
from sqlalchemy import select

from marcus.core import annotation as ann
from marcus.core.enums import ErrorClass
from marcus.core.models import Annotation, Step
from marcus.core.pipeline import (
    ANNOTATE_SEQ,
    AnnotateNotAllowed,
    BadResult,
    cancel_paper,
    complete_step,
    fail_step,
    request_annotation,
)
from tests.core.test_pipeline import SEG_V, SEGS, finish, run, steps, to_processing
from tests.factories import make_paper

IP = "198.51.100.9"


def result(**fields) -> dict:
    output = {f: list(fields.get(f, [])) for f in ann.FIELDS}
    positions = {f: {v: [[0, 0, len(v)]] for v in output[f]} for f in ann.FIELDS}
    return {
        "model": "qwen3.5-9b-marcus-v1",
        "model_version": "Q8_0 llama.cpp b12554",
        "output": output,
        "positions": positions,
        "ms": 1234,
    }


def _done_paper(s, docling: bool = True):
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=1)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    (docling_step,) = steps(s, paper, "docling")
    if docling:
        finish(s, docling_step, {"text_path": "text.json"})
    else:
        run(s, docling_step)
        fail_step(s, docling_step.id, ErrorClass.ENGINE_ERROR, "boom", retryable=False)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
    s.refresh(paper)
    assert paper.status == "done"
    return paper


def _annotation(s, paper) -> Annotation | None:
    return s.execute(
        select(Annotation)
        .where(Annotation.paper_id == paper.id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def test_request_creates_a_pending_llm_step_and_reopens_the_paper(db_session):
    s = db_session
    paper = _done_paper(s)
    paper.started_ip = None
    step = request_annotation(s, paper.id, started_ip=IP)
    assert (step.kind, step.queue, step.status, step.seq) == (
        "annotate", "q.llm", "pending", ANNOTATE_SEQ,
    )  # fmt: skip
    assert step.paper_id == paper.id and step.page is None and step.engine is None
    s.refresh(paper)
    assert paper.status == "processing" and paper.started_ip == IP


def test_result_is_stored_and_the_paper_is_done_again(db_session):
    s = db_session
    paper = _done_paper(s)
    step = request_annotation(s, paper.id)
    finish(s, step, result(organism_or_species=["Taxus brevifolia"], Kingdom=["Plant"]))
    s.refresh(paper)
    assert paper.status == "done" and paper.started_ip is None
    row = _annotation(s, paper)
    assert row.model == "qwen3.5-9b-marcus-v1" and row.model_version == "Q8_0 llama.cpp b12554"
    assert row.output["organism_or_species"] == ["Taxus brevifolia"]
    assert row.positions["Kingdom"] == {"Plant": [[0, 0, 5]]}
    assert row.curated is None and row.curated_positions is None
    s.refresh(step)
    assert step.status == "done" and step.model_version == "Q8_0 llama.cpp b12554"


def test_a_repeat_request_gets_the_active_step_back(db_session):
    s = db_session
    paper = _done_paper(s)
    first = request_annotation(s, paper.id)
    again = request_annotation(s, paper.id, rerun=True)
    assert again.id == first.id
    assert len(steps(s, paper, "annotate")) == 1


def test_an_annotated_paper_is_not_run_again_unless_asked(db_session):
    s = db_session
    paper = _done_paper(s)
    finish(s, request_annotation(s, paper.id), result(Kingdom=["Plant"]))
    assert request_annotation(s, paper.id) is None
    s.refresh(paper)
    assert paper.status == "done"
    rerun = request_annotation(s, paper.id, rerun=True)
    assert rerun is not None and rerun.status == "pending"


def test_a_rerun_replaces_the_model_output_and_keeps_the_curation(db_session):
    s = db_session
    paper = _done_paper(s)
    finish(s, request_annotation(s, paper.id), result(Kingdom=["Plant"]))
    row = _annotation(s, paper)
    row.curated = {f: [] for f in ann.FIELDS} | {"Kingdom": ["Fungi"]}
    row.curated_positions = {f: {} for f in ann.FIELDS} | {"Kingdom": {"Fungi": []}}
    s.flush()
    finish(s, request_annotation(s, paper.id, rerun=True), result(Kingdom=["Animalia"]))
    row = _annotation(s, paper)
    assert row.output["Kingdom"] == ["Animalia"]
    assert row.curated["Kingdom"] == ["Fungi"]


def test_a_failed_paper_with_text_can_be_annotated_and_stays_failed(db_session):
    s = db_session
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=1)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    render = run(s, steps(s, paper, "render_page")[0])
    fail_step(s, render.id, ErrorClass.BAD_INPUT, "bad page", retryable=False)
    s.refresh(paper)
    assert paper.status == "failed"
    step = request_annotation(s, paper.id)
    s.refresh(paper)
    assert paper.status == "processing"
    finish(s, step, result())
    s.refresh(paper)
    assert paper.status == "failed" and paper.error == "all pages failed to render"


def test_no_text_no_annotation(db_session):
    s = db_session
    paper = _done_paper(s, docling=False)
    with pytest.raises(AnnotateNotAllowed) as exc:
        request_annotation(s, paper.id)
    assert exc.value.reason == "no_text"
    busy = make_paper(s)  # still checking: no docling step yet
    with pytest.raises(AnnotateNotAllowed):
        request_annotation(s, busy.id)


def test_deleted_or_missing_paper_is_refused(db_session):
    s = db_session
    paper = _done_paper(s)
    cancel_paper(s, paper.id)
    with pytest.raises(ValueError):
        request_annotation(s, paper.id)


def test_a_final_failure_leaves_no_annotation_and_the_paper_done(db_session):
    s = db_session
    paper = _done_paper(s)
    step = run(s, request_annotation(s, paper.id))
    fail_step(s, step.id, ErrorClass.ENGINE_ERROR, "llama-server down", retryable=True)
    s.refresh(step)
    assert step.status == "pending"  # one retry
    run(s, step)
    fail_step(s, step.id, ErrorClass.ENGINE_ERROR, "llama-server down", retryable=True)
    s.refresh(paper)
    s.refresh(step)
    assert step.status == "failed" and paper.status == "done"
    assert _annotation(s, paper) is None


def test_deleting_the_paper_deletes_its_annotation_at_once(db_session):
    s = db_session
    paper = _done_paper(s)
    finish(s, request_annotation(s, paper.id), result(Kingdom=["Plant"]))
    cancel_paper(s, paper.id)
    assert _annotation(s, paper) is None


def _bad(change) -> dict:
    r = result(organism_or_species=["Taxus brevifolia"])
    change(r)
    return r


@pytest.mark.parametrize(
    "bad",
    [
        _bad(lambda r: r.pop("model")),
        _bad(lambda r: r.update(model="")),
        _bad(lambda r: r.update(model_version="v" * 201)),
        _bad(lambda r: r["output"].pop("Kingdom")),
        _bad(lambda r: r["output"].update(extra=[])),
        _bad(lambda r: r["output"].update(Kingdom="Plant")),
        _bad(lambda r: r["output"].update(Kingdom=["Pl\x00ant"])),
        _bad(lambda r: r["output"].update(Kingdom=["x" * 61])),
        _bad(lambda r: r["output"].update(Kingdom=["a"] * (ann.MAX_VALUES_PER_FIELD + 1))),
        _bad(lambda r: r["positions"].pop("Kingdom")),
        _bad(lambda r: r["positions"]["organism_or_species"].update({"Other": [[0, 0, 1]]})),
        _bad(
            lambda r: r["positions"]["organism_or_species"].update(
                {"Taxus brevifolia": [[0, -1, 2]]}
            )
        ),
        _bad(
            lambda r: r["positions"]["organism_or_species"].update({"Taxus brevifolia": [[0, 1]]})
        ),
        _bad(
            lambda r: r["positions"]["organism_or_species"].update(
                {"Taxus brevifolia": [[0, 3, 2]]}
            )
        ),
        _bad(lambda r: r.update(ms=-1)),
    ],
)
def test_a_malformed_result_changes_nothing(db_session, bad):
    s = db_session
    paper = _done_paper(s)
    step = run(s, request_annotation(s, paper.id))
    with pytest.raises(BadResult):
        complete_step(s, step.id, bad)
    s.rollback()
    assert _annotation(s, paper) is None
    assert s.get(Step, step.id) is None or s.get(Step, step.id).status != "done"
