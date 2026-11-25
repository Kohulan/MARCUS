"""What runs by itself (marcus.core.auto): which papers get their annotation and which
scaffolds their R-group rows without a click, and that both stay outside the paper's read."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from marcus.core import auto
from marcus.core.enums import ErrorClass
from marcus.core.models import Annotation, Paper, Prediction, RgroupExtraction, Step
from marcus.core.pipeline import (
    cancel_paper,
    complete_step,
    fail_step,
    request_annotation,
    request_ocsr,
    request_rgroups,
)
from tests.core.test_annotate_pipeline import result as annotation_result
from tests.core.test_pipeline import SEG_V, SEGS, finish, run, steps, to_processing
from tests.core.test_rgroups_pipeline import PLAIN, SCAFFOLD, done_paper
from tests.factories import make_paper


def _text_read_paper(s, docling: bool = True):
    """A done 1-page paper without structures whose text is read (or failed)."""
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
    return paper


def _age_text(s, paper, hours: float) -> None:
    s.execute(
        update(Step)
        .where(Step.paper_id == paper.id, Step.kind == "docling")
        .values(finished_at=datetime.now(UTC) - timedelta(hours=hours))
    )
    s.flush()


def _age_predictions(s, paper, hours: float) -> None:
    for p in s.query(Prediction).all():
        p.created_at = datetime.now(UTC) - timedelta(hours=hours)
    s.flush()


# --- annotation -----------------------------------------------------------------------------


def test_a_paper_whose_text_is_read_is_annotated_by_itself(db_session):
    s = db_session
    paper = _text_read_paper(s)
    assert auto.annotation_candidates(s) == [paper.id]
    assert auto.annotation_candidates(s, paper_id=paper.id) == [paper.id]


def test_no_auto_annotation_without_text_or_once_one_was_asked_for(db_session):
    s = db_session
    no_text = _text_read_paper(s, docling=False)
    asked = _text_read_paper(s)
    step = request_annotation(s, asked.id)
    assert auto.annotation_candidates(s) == []
    # a failed run is not tried again by itself (the manual action stays)
    run(s, step)
    fail_step(s, step.id, ErrorClass.ENGINE_ERROR, "down", retryable=False)
    assert auto.annotation_candidates(s) == []
    assert no_text.id not in auto.annotation_candidates(s)


def test_no_auto_annotation_for_an_annotated_deleted_expired_or_old_paper(db_session):
    s = db_session
    annotated = _text_read_paper(s)
    s.add(Annotation(paper_id=annotated.id, model="m", model_version="v", output={}, positions={}))
    deleted = _text_read_paper(s)
    cancel_paper(s, deleted.id, remove_files=False)
    expired = _text_read_paper(s)
    expired.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    old = _text_read_paper(s)
    _age_text(s, old, hours=2)  # read before the window: never run by itself
    s.flush()
    assert auto.annotation_candidates(s) == []


def test_the_window_is_a_setting(db_session, monkeypatch, clear_settings_cache):
    s = db_session
    paper = _text_read_paper(s)
    _age_text(s, paper, hours=2)
    monkeypatch.setenv("MARCUS_AUTO_WINDOW_S", str(3 * 3600))
    clear_settings_cache()
    assert auto.annotation_candidates(s) == [paper.id]


# --- R-group rows ---------------------------------------------------------------------------


def test_a_scaffold_of_the_paper_engine_is_read_by_itself(db_session):
    s = db_session
    paper, scaffold, plain = done_paper(s)
    assert auto.rgroup_candidates(s) == [scaffold.id]
    assert auto.rgroup_candidates(s, paper_id=paper.id) == [scaffold.id]


def test_no_auto_reading_once_asked_for_even_when_it_failed(db_session):
    s = db_session
    paper, scaffold, _ = done_paper(s)
    step = request_rgroups(s, scaffold.id)
    assert auto.rgroup_candidates(s) == []
    run(s, step)
    fail_step(s, step.id, ErrorClass.ENGINE_ERROR, "down", retryable=False)
    assert s.query(RgroupExtraction).one().status == "failed"
    assert auto.rgroup_candidates(s) == []


def test_only_unlabelled_points_or_no_text_are_not_read_by_itself(db_session):
    s = db_session
    paper = make_paper(s)
    to_processing(s, paper, pages=1)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    # the paper's own engine (the other two read in the background, phase B item 3)
    first, second = [
        st for st in finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
        if st.engine == paper.engine
    ]
    finish(s, first, {**SCAFFOLD, "smiles": "*c1ccccc1"})  # an unlabelled point only
    finish(s, second, SCAFFOLD)
    assert auto.rgroup_candidates(s) == []  # the text is not read yet
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    (pred,) = [p for p in s.query(Prediction).all() if p.rgroups == ["R1", "R2"]]
    assert auto.rgroup_candidates(s) == [pred.id]


def test_a_scaffold_whose_page_names_its_labels_is_read_by_itself(db_session):
    """The page's text names R1: the worker asks for the named labels (as on a click)."""
    s = db_session
    paper, scaffold, _ = done_paper(s)
    s.execute(update(Paper).where(Paper.id == paper.id).values(rgroup_text_labels={"0": ["R1"]}))
    s.flush()
    assert auto.rgroup_candidates(s) == [scaffold.id]


def test_another_engines_reading_and_an_older_one_are_not_read_by_itself(db_session):
    s = db_session
    paper, scaffold, _ = done_paper(s)
    other = request_ocsr(s, scaffold.segment_id, "molparser")
    finish(s, other, {**SCAFFOLD, "engine_version": "1.0"})
    again = request_ocsr(s, scaffold.segment_id, "decimer")
    finish(s, again, SCAFFOLD)
    (newest,) = (
        s.query(Prediction)
        .filter(Prediction.segment_id == scaffold.segment_id, Prediction.engine == "decimer")
        .filter(Prediction.id != scaffold.id)
        .all()
    )
    newest.created_at = datetime.now(UTC) + timedelta(seconds=1)  # one transaction here
    s.flush()
    assert auto.rgroup_candidates(s) == [newest.id]


def test_no_auto_reading_for_a_deleted_or_old_paper(db_session):
    s = db_session
    old, _, _ = done_paper(s)
    _age_text(s, old, hours=2)
    _age_predictions(s, old, hours=2)
    gone, _, _ = done_paper(s)
    cancel_paper(s, gone.id, remove_files=False)
    assert auto.rgroup_candidates(s) == []


def test_a_new_reading_on_an_old_paper_counts_from_the_reading(db_session):
    s = db_session
    paper, scaffold, _ = done_paper(s)
    _age_text(s, paper, hours=2)
    assert auto.rgroup_candidates(s) == [scaffold.id]  # the prediction is new


# --- outside the paper's read ---------------------------------------------------------------


def test_an_annotate_step_never_keeps_the_paper_busy(db_session):
    """Annotation is outside the read: a paper whose last read step ends while its annotation
    still runs is done, and starting one never reopens a done paper."""
    s = db_session
    paper = make_paper(s, ocsr_mode="off")
    to_processing(s, paper, pages=1)
    finish(s, steps(s, paper, "doi")[0], {"doi": None})
    finish(s, steps(s, paper, "docling")[0], {"text_path": "text.json"})
    annotate = request_annotation(s, paper.id)
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    finish(s, seg_step, {"segments": SEGS, "seg_version": SEG_V})
    s.refresh(paper)
    assert paper.status == "done"
    run(s, annotate)
    complete_step(s, annotate.id, annotation_result(Kingdom=["Plant"]))
    s.refresh(paper)
    assert paper.status == "done"
    assert request_annotation(s, paper.id, rerun=True) is not None
    s.refresh(paper)
    assert paper.status == "done"


def test_plain_structures_are_never_candidates(db_session):
    s = db_session
    paper, scaffold, plain = done_paper(s)
    assert plain.id not in auto.rgroup_candidates(s)
    assert PLAIN["smiles"] == plain.smiles


# --- one rule for the dispatcher and the API -------------------------------------------------


def test_the_rule_is_none_where_the_feature_is_off(monkeypatch, clear_settings_cache):
    from marcus.core.enums import StepKind

    monkeypatch.setenv("MARCUS_ANNOTATE_ENABLED", "0")
    monkeypatch.setenv("MARCUS_RGROUP_ENABLED", "1")
    clear_settings_cache()
    assert auto.candidates_query(StepKind.ANNOTATE) is None
    assert auto.candidates_query(StepKind.RGROUPS) is not None


def test_about_to_start_is_a_short_window(db_session, monkeypatch, clear_settings_cache):
    """The API's `auto_pending` uses the same rule over START_S, not the hour."""
    from marcus.core.enums import StepKind

    monkeypatch.setenv("MARCUS_ANNOTATE_ENABLED", "1")
    clear_settings_cache()
    s = db_session
    paper = _text_read_paper(s)
    soon = auto.candidates_query(StepKind.ANNOTATE, paper.id, within_s=auto.START_S)
    assert list(s.execute(soon).scalars()) == [paper.id]
    _age_text(s, paper, hours=auto.START_S / 3600 + 0.01)
    assert list(s.execute(soon).scalars()) == []
    assert auto.annotation_candidates(s) == [paper.id]  # the dispatcher's hour still holds


def test_the_scaffold_query_narrows_to_the_window_before_picking_the_newest():
    """DISTINCT ON over every prediction of every live paper every 3 s would grow with the
    database: the window is applied inside, before the newest per segment is picked."""
    from sqlalchemy.dialects import postgresql

    sql = str(auto.rgroup_query().compile(dialect=postgresql.dialect()))
    inner = sql[sql.index("DISTINCT ON") :]
    inner = inner[: inner.index(") AS anon")]
    assert "make_interval" in inner
