"""The planner's rgroups step: request_rgroups, its result, failures, deletion, and the paper's
progress (an rgroups step never touches it); the handler against the database."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import select, update

from marcus.core.enums import ErrorClass
from marcus.core.models import Paper, Prediction, RgroupExtraction, Segment, Step
from marcus.core.pipeline import (
    RGROUPS_SEQ,
    BadResult,
    RgroupsNotAllowed,
    cancel_paper,
    complete_step,
    fail_step,
    request_annotation,
    request_ocsr,
    request_rgroups,
)
from marcus.core.settings import get_settings
from marcus.core.storage import page_image_path, text_path
from marcus.dispatcher.pick import watchdog_once
from tests.core.test_pipeline import SEG_V, SEGS, finish, run, steps, to_processing
from tests.factories import make_image_job, make_paper

SCAFFOLD = {"smiles": "[R1]c1ccccc1[R2]", "molfile": None, "valid": False, "ms": 9,
            "engine_version": "2.7"}  # fmt: skip
PLAIN = {"smiles": "CCO", "molfile": None, "valid": True, "ms": 9, "engine_version": "2.7"}
ROWS = [
    {"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}},
    {"compound": "3b", "groups": {"R1": "H", "R2": "OMe"}},
]
LIVE_WITHOUT_LLM = frozenset({"q.cpu", "q.tools", "q.segment", "q.fake"})


def result(rows=ROWS, labels=("R1", "R2"), **kw) -> dict:
    return {
        "model": "nuextract3-rgroup-v1",
        "model_version": "vision Q8_0 llama.cpp b12554",
        "labels": list(labels),
        "rows": rows,
        "truncated": False,
        "ms": 3300,
        **kw,
    }


def done_paper(s):
    """A done 1-page paper: segment 0 a scaffold (R1, R2), segment 1 a plain structure.
    Returns (paper, scaffold prediction, plain prediction)."""
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    # the paper's own engine (the other two read in the background, phase B item 3)
    first, second = [
        st for st in finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
        if st.engine == paper.engine
    ]
    finish(s, first, SCAFFOLD)
    finish(s, second, PLAIN)
    s.refresh(paper)
    assert paper.status == "done"
    preds = s.execute(
        select(Prediction).join(Segment).where(Segment.paper_id == paper.id).order_by(Segment.idx)
    ).scalars()
    scaffold, plain = list(preds)
    assert scaffold.rgroups == ["R1", "R2"] and plain.rgroups == []
    return paper, scaffold, plain


def row_of(s, prediction) -> RgroupExtraction | None:
    return s.execute(
        select(RgroupExtraction)
        .where(RgroupExtraction.prediction_id == prediction.id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def test_request_creates_a_pending_rgroup_step_and_a_queued_row(db_session):
    s = db_session
    paper, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    assert (step.kind, step.queue, step.status, step.seq) == ("rgroups", "q.rgroup", "pending",
                                                              RGROUPS_SEQ)  # fmt: skip
    assert step.paper_id == paper.id and step.segment_id == scaffold.segment_id
    assert step.page is None and step.engine is None
    row = row_of(s, scaffold)
    assert (row.status, row.step_id, row.labels, row.rows) == (
        "queued",
        step.id,
        ["R1", "R2"],
        None,
    )
    s.refresh(paper)
    assert paper.status == "done"  # never reopened


def test_repeat_clicks_get_the_waiting_step(db_session):
    s = db_session
    _, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    assert request_rgroups(s, scaffold.id).id == step.id
    run(s, step)
    assert request_rgroups(s, scaffold.id, rerun=True).id == step.id  # running: the same


def test_refusals(db_session):
    s = db_session
    paper, scaffold, plain = done_paper(s)
    with pytest.raises(RgroupsNotAllowed):
        request_rgroups(s, plain.id)
    job, job_step = make_image_job(s)
    finish(s, job_step, SCAFFOLD)
    (job_prediction,) = s.execute(
        select(Prediction).where(Prediction.image_job_id == job.id)
    ).scalars()
    with pytest.raises(ValueError):
        request_rgroups(s, job_prediction.id)  # no paper, no page
    cancel_paper(s, paper.id, remove_files=False)
    with pytest.raises(ValueError):
        request_rgroups(s, scaffold.id)
    assert s.execute(select(RgroupExtraction)).first() is None


def test_a_structure_whose_only_label_is_unlabelled_is_refused(db_session):
    """`*` alone: nothing the model was trained to be asked for. Rows read before stay."""
    s = db_session
    _, scaffold, _ = done_paper(s)
    finish(s, request_rgroups(s, scaffold.id), result())
    s.execute(update(Prediction).where(Prediction.id == scaffold.id).values(rgroups=["*"]))
    with pytest.raises(RgroupsNotAllowed):
        request_rgroups(s, scaffold.id, rerun=True)
    row = row_of(s, scaffold)
    assert (row.status, row.labels, row.rows) == ("done", ["R1", "R2"], ROWS)


def test_result_is_stored_and_a_rerun_replaces_it(db_session):
    s = db_session
    paper, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    assert finish(s, step, result()) == []
    s.refresh(step)
    assert step.status == "done" and step.model_version == "vision Q8_0 llama.cpp b12554"
    row = row_of(s, scaffold)
    assert row.status == "done" and row.rows == ROWS and row.error is None
    assert (row.model, row.truncated) == ("nuextract3-rgroup-v1", False)
    assert row.finished_at is not None
    assert request_rgroups(s, scaffold.id) is None  # has rows: no new step
    again = request_rgroups(s, scaffold.id, rerun=True)
    assert again.id != step.id
    row = row_of(s, scaffold)
    assert row.status == "queued" and row.rows == ROWS  # kept while the re-run waits
    finish(s, again, result(rows=ROWS[:1], truncated=True))
    row = row_of(s, scaffold)
    assert row.status == "done" and row.rows == ROWS[:1] and row.truncated is True
    s.refresh(paper)
    assert paper.status == "done"


def test_a_result_for_the_labels_the_text_names_keeps_only_those(db_session):
    """The worker leaves out a label the page text never names (an OCSR extra): the stored
    labels are the result's, and a re-run shows them with the old rows until it ends."""
    s = db_session
    _, scaffold, _ = done_paper(s)
    one = [{"compound": "3a", "groups": {"R1": "OMe"}}]
    finish(s, request_rgroups(s, scaffold.id), result(rows=one, labels=["R1"]))
    row = row_of(s, scaffold)
    assert (row.status, row.labels, row.rows) == ("done", ["R1"], one)
    again = request_rgroups(s, scaffold.id, rerun=True)
    row = row_of(s, scaffold)
    assert (row.status, row.labels, row.rows) == ("queued", ["R1"], one)
    run(s, again)
    fail_step(s, again.id, ErrorClass.ENGINE_ERROR, "boom", retryable=False)
    row = row_of(s, scaffold)
    assert (row.status, row.labels, row.rows) == ("failed", ["R1"], one)
    finish(s, request_rgroups(s, scaffold.id, rerun=True), result())
    row = row_of(s, scaffold)
    assert (row.status, row.labels, row.rows) == ("done", ["R1", "R2"], ROWS)


def test_a_failed_run_keeps_earlier_rows_and_says_why(db_session):
    s = db_session
    _, scaffold, _ = done_paper(s)
    finish(s, request_rgroups(s, scaffold.id), result())
    step = request_rgroups(s, scaffold.id, rerun=True)
    run(s, step)
    fail_step(s, step.id, ErrorClass.TIMEOUT, "llama-rgroup did not answer", retryable=True)
    row = row_of(s, scaffold)
    assert row.status == "queued"  # retried once
    run(s, step)
    fail_step(s, step.id, ErrorClass.TIMEOUT, "llama-rgroup did not answer", retryable=True)
    row = row_of(s, scaffold)
    assert row.status == "failed" and row.error == "timeout"  # the class, never the text
    assert row.rows == ROWS


@pytest.mark.parametrize(
    "bad",
    [
        result(model=""),
        result(labels=[]),
        result(rows=[{"compound": "1", "groups": {"R1": "H"}}]),
        result(rows=[{"compound": "1", "groups": {"R2": "H", "R1": "H"}}]),
        result(truncated="no"),
        result(ms=-1),
        result(labels=["R1", "X"], rows=[]),  # other labels than were asked for
        result(labels=["R2", "R1"], rows=[]),  # not in the asked order
    ],
)
def test_a_malformed_result_is_refused_before_anything_changes(db_session, bad):
    s = db_session
    _, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    s.commit()
    run(s, step)
    s.commit()
    with pytest.raises(BadResult):
        complete_step(s, step.id, bad)
    s.rollback()
    assert row_of(s, scaffold).status == "queued"


def test_an_rgroups_step_never_keeps_a_paper_busy(db_session):
    """A paper re-read by another engine ends `done` while its rgroups step still waits."""
    s = db_session
    paper, scaffold, _ = done_paper(s)
    rg_step = request_rgroups(s, scaffold.id)
    # decimer-hand: no background step of it waits already (that one would be returned)
    ocsr = request_ocsr(s, scaffold.segment_id, "decimer-hand")
    s.refresh(paper)
    assert paper.status == "processing"
    finish(s, ocsr, PLAIN)
    s.refresh(paper)
    assert paper.status == "done"
    s.refresh(rg_step)
    assert rg_step.status == "pending"
    finish(s, rg_step, result())
    s.refresh(paper)
    assert paper.status == "done"


def test_deleting_the_paper_cancels_the_step_and_deletes_the_rows(db_session):
    s = db_session
    paper, scaffold, _ = done_paper(s)
    finish(s, request_rgroups(s, scaffold.id), result())
    step = request_rgroups(s, scaffold.id, rerun=True)
    cancel_paper(s, paper.id, remove_files=False)
    s.refresh(step)
    assert step.status == "cancelled"
    assert row_of(s, scaffold) is None
    assert complete_step(s, step.id, result()) == []  # a late result is dropped


def test_an_unserved_rgroups_step_fails_and_says_so(db_session):
    s = db_session
    _, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    old = datetime.now(UTC) - timedelta(seconds=get_settings().annotate_max_wait_s + 30)
    s.execute(update(Step).where(Step.id == step.id).values(created_at=old))
    s.commit()
    assert watchdog_once(s, live_queues=lambda: LIVE_WITHOUT_LLM | {"q.rgroup"}) == 0
    # the annotation worker (q.llm) does not serve it: the R-group worker is missing
    assert watchdog_once(s, live_queues=lambda: LIVE_WITHOUT_LLM | {"q.llm"}) == 1
    s.expire_all()
    failed = s.get(Step, step.id)
    assert failed.status == "failed" and failed.error == "no R-group worker"
    row = row_of(s, scaffold)
    assert row.status == "failed" and row.error == "engine_error"


def test_an_unserved_annotation_does_not_fail_a_served_rgroups_step(db_session):
    """Each model service is judged on its own queue: q.rgroup live, q.llm not."""
    from tests.core.test_annotate_pipeline import _done_paper

    s = db_session
    _, scaffold, _ = done_paper(s)
    rg_step = request_rgroups(s, scaffold.id)
    ann_step = request_annotation(s, _done_paper(s).id)
    old = datetime.now(UTC) - timedelta(seconds=get_settings().annotate_max_wait_s + 30)
    s.execute(update(Step).where(Step.id.in_([rg_step.id, ann_step.id])).values(created_at=old))
    s.commit()
    assert watchdog_once(s, live_queues=lambda: LIVE_WITHOUT_LLM | {"q.rgroup"}) == 1
    s.expire_all()
    assert s.get(Step, ann_step.id).status == "failed"
    assert s.get(Step, rg_step.id).status == "pending"


def test_the_handler_reads_its_request_from_the_database(db_session, monkeypatch,
                                                         clear_settings_cache):  # fmt: skip
    from marcus.workers.rgroups.handler import extract_rgroups

    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    s = db_session
    paper, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    s.commit()
    doc = {
        "texts": [{"label": "caption", "text": "3a: R1 = OMe, R2 = H", "prov": [{"page_no": 1}]}]
    }
    text_path(paper.id).parent.mkdir(parents=True, exist_ok=True)
    text_path(paper.id).write_text(json.dumps(doc))
    page_image_path(paper.id, 0).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(page_image_path(paper.id, 0))
    out = extract_rgroups(s.get(Step, step.id), s)
    assert out["labels"] == ["R1", "R2"]
    assert out["rows"] == [{"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}}]
    run(s, s.get(Step, step.id))
    complete_step(s, step.id, out)
    assert row_of(s, scaffold).rows == out["rows"]
    assert s.get(Paper, paper.id).status == "done"


def test_the_handler_gives_a_label_to_the_nearest_drawing_of_the_page(db_session, monkeypatch,
                                                                     clear_settings_cache):  # fmt: skip
    """The series label "9a-b" is under the scaffold (segment 0) but inside the plain structure
    next to it (segment 1, lower half): it is the plain structure's, and the scaffold keeps its
    rows (marcus.core.rgroup_series). The handler reads the page's drawings from the database."""
    from marcus.workers.rgroups.handler import extract_rgroups

    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    s = db_session
    paper, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    s.commit()
    box = {"l": 0.48, "t": 9.6, "r": 1.92, "b": 12.0, "coord_origin": "TOPLEFT"}  # px 2,40,8,50
    doc = {
        "texts": [
            {"label": "caption", "text": "3a: R1 = OMe, R2 = H", "prov": [{"page_no": 1}]},
            {"label": "text", "text": "9a-b", "prov": [{"page_no": 1, "bbox": box}]},
        ]
    }
    text_path(paper.id).parent.mkdir(parents=True, exist_ok=True)
    text_path(paper.id).write_text(json.dumps(doc))
    page_image_path(paper.id, 0).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(page_image_path(paper.id, 0))
    out = extract_rgroups(s.get(Step, step.id), s)
    assert out["rows"] == [{"compound": "3a", "groups": {"R1": "OMe", "R2": "H"}}]


def test_a_rerun_asks_for_the_predictions_labels_again(db_session, monkeypatch,
                                                       clear_settings_cache):  # fmt: skip
    """The stored labels are those of the shown rows (R1 here); a re-run asks for the
    prediction's own (R1, R2), and the page text decides again."""
    from marcus.workers.rgroups.handler import extract_rgroups

    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    s = db_session
    paper, scaffold, _ = done_paper(s)
    finish(s, request_rgroups(s, scaffold.id), result(rows=[], labels=["R1"]))
    step = request_rgroups(s, scaffold.id, rerun=True)
    s.commit()
    doc = {
        "texts": [{"label": "caption", "text": "3a: R1 = OMe, R2 = H", "prov": [{"page_no": 1}]}]
    }
    text_path(paper.id).parent.mkdir(parents=True, exist_ok=True)
    text_path(paper.id).write_text(json.dumps(doc))
    page_image_path(paper.id, 0).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(page_image_path(paper.id, 0))
    out = extract_rgroups(s.get(Step, step.id), s)
    assert out["labels"] == ["R1", "R2"]


def test_the_reader_is_asked_for_every_engines_labels(db_session, monkeypatch,
                                                      clear_settings_cache):  # fmt: skip
    """One engine misreads a label (MolScribe read R5 as "Rs", BJOC 18/23): the reader is asked
    for the labels of every engine's reading of the drawing that the page text names, so a
    column one engine missed is still read (live, 2026-11-26)."""
    from marcus.workers.rgroups.handler import extract_rgroups

    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    s = db_session
    paper, scaffold, _ = done_paper(s)
    s.add(Prediction(segment_id=scaffold.segment_id, engine="molparser", engine_version="f8f1e21",
                     smiles="[R1]c1cc([R2])cc([R3])c1", valid=False, ms=1,
                     rgroups=["R1", "R2", "R3"]))  # fmt: skip
    step = request_rgroups(s, scaffold.id)
    s.commit()
    doc = {
        "texts": [
            {"label": "caption", "text": "3a: R1 = OMe, R2 = H, R3 = OH", "prov": [{"page_no": 1}]}
        ]
    }
    text_path(paper.id).parent.mkdir(parents=True, exist_ok=True)
    text_path(paper.id).write_text(json.dumps(doc))
    page_image_path(paper.id, 0).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(page_image_path(paper.id, 0))
    out = extract_rgroups(s.get(Step, step.id), s)
    assert out["labels"] == ["R1", "R2", "R3"]
    finish(s, s.get(Step, step.id), out)  # the result for another engine's label is stored
    assert row_of(s, scaffold).labels == ["R1", "R2", "R3"]


def test_another_engines_label_the_text_never_names_is_not_asked(db_session, monkeypatch,
                                                                 clear_settings_cache):  # fmt: skip
    """An engine may also invent a label (DECIMER's Z beside R1, R2 on stylissa page 6): another
    engine's label is asked only when the page text names it."""
    from marcus.workers.rgroups.handler import extract_rgroups

    monkeypatch.setenv("MARCUS_RGROUP_READER", "fake")
    monkeypatch.setenv("MARCUS_ENABLE_FAKE_ENGINES", "1")
    clear_settings_cache()
    s = db_session
    paper, scaffold, _ = done_paper(s)
    s.add(Prediction(segment_id=scaffold.segment_id, engine="molparser", engine_version="f8f1e21",
                     smiles="[R1]c1cc([R2])cc([R3])c1", valid=False, ms=1,
                     rgroups=["R1", "R2", "R3"]))  # fmt: skip
    step = request_rgroups(s, scaffold.id)
    s.commit()
    doc = {"texts": [{"label": "caption", "text": "3a: R1 = OMe, R2 = H", "prov": [{"page_no": 1}]}]}
    text_path(paper.id).parent.mkdir(parents=True, exist_ok=True)
    text_path(paper.id).write_text(json.dumps(doc))
    page_image_path(paper.id, 0).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(page_image_path(paper.id, 0))
    out = extract_rgroups(s.get(Step, step.id), s)
    assert out["labels"] == ["R1", "R2"]
