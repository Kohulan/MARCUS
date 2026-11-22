"""Every new segment read by DECIMER, MolNexTR and MolScribe (phase B item 3): the paper's own
engine in its read, the other two in the background (marcus.core.pipeline.background_engines)."""

from sqlalchemy import func, select

from marcus.core.enums import Engine, ErrorClass
from marcus.core.models import BackgroundStep, Paper, Prediction, Step
from marcus.core.pipeline import complete_step, fail_step, in_paper_progress
from marcus.dispatcher.pick import pick_next
from tests.factories import make_owner, make_paper

SEGS = [
    {"idx": 0, "bbox": [0, 0, 10, 10], "image_sha256": "0" * 64},
    {"idx": 1, "bbox": [5, 5, 50, 60], "image_sha256": "1" * 64},
]
OCSR = {"smiles": "CCO", "molfile": None, "valid": True, "ms": 12, "engine_version": "t"}


def steps(s, paper, kind=None, status=None) -> list[Step]:
    q = select(Step).where(Step.paper_id == paper.id)
    if kind:
        q = q.where(Step.kind == kind)
    if status:
        q = q.where(Step.status == status)
    return list(s.execute(q.order_by(Step.seq, Step.engine)).scalars())


def finish(s, step, result):
    step.status = "running"
    step.attempts += 1
    s.flush()
    return complete_step(s, step.id, result)


def background_ids(s) -> set:
    return set(s.execute(select(BackgroundStep.step_id)).scalars())


def segmented(s, engine=Engine.DECIMER, owner=None) -> Paper:
    """A 1-page paper read up to its segments (docling and doi done)."""
    paper = make_paper(s, owner, engine=engine)
    (check,) = steps(s, paper, "check_pdf")
    finish(s, check, {"pages": 1})
    for st in steps(s, paper, "doi"):
        finish(s, st, {"doi": None})
    for st in steps(s, paper, "docling"):
        finish(s, st, {})
    (seg_step,) = finish(s, steps(s, paper, "render_page")[0], {})
    finish(s, seg_step, {"segments": SEGS, "seg_version": "v"})
    return paper


def test_each_segment_gets_the_three_engines(db_session):
    s = db_session
    paper = segmented(s)
    ocsr = steps(s, paper, "ocsr")
    got = sorted((st.seq, st.engine, st.queue) for st in ocsr)
    assert got == [
        (0, "decimer", "q.decimer"), (0, "molnextr", "q.molnextr"), (0, "molscribe", "q.molscribe"),
        (1, "decimer", "q.decimer"), (1, "molnextr", "q.molnextr"), (1, "molscribe", "q.molscribe"),
    ]  # fmt: skip
    background = background_ids(s)
    assert {st.engine for st in ocsr if st.id in background} == {"molnextr", "molscribe"}
    assert len(background) == 4


def test_the_paper_engine_is_the_read_whatever_it_is(db_session):
    s = db_session
    paper = segmented(s, engine=Engine.MOLSCRIBE)
    background = background_ids(s)
    own = [st.engine for st in steps(s, paper, "ocsr") if st.id not in background]
    assert own == ["molscribe", "molscribe"]
    # DECIMER hand-drawn stays the user's choice: such a paper gets the three beside it
    hand = segmented(s, engine=Engine.DECIMER_HAND)
    first = steps(s, hand, "ocsr")[0].segment_id
    engines = sorted(st.engine for st in steps(s, hand, "ocsr") if st.segment_id == first)
    assert engines == ["decimer", "decimer-hand", "molnextr", "molscribe"]


def test_the_fake_engine_has_no_background(db_session):
    s = db_session
    paper = segmented(s, engine=Engine.FAKE)
    assert [st.engine for st in steps(s, paper, "ocsr")] == ["fake", "fake"]
    assert background_ids(s) == set()


def test_done_after_its_own_engine_and_a_background_failure_changes_nothing(db_session):
    s = db_session
    paper = segmented(s)
    background = background_ids(s)
    for st in steps(s, paper, "ocsr"):
        if st.id not in background:
            finish(s, st, OCSR)
    s.refresh(paper)
    assert paper.status == "done"  # the other engines are still pending
    active_in_progress = s.execute(
        select(func.count())
        .select_from(Step)
        .where(Step.paper_id == paper.id, Step.status == "pending", in_paper_progress())
    ).scalar_one()
    assert active_in_progress == 0
    late = [st for st in steps(s, paper, "ocsr") if st.id in background]
    finish(s, late[0], {**OCSR, "smiles": "OCC"})
    late[1].status, late[1].attempts = "running", 2
    s.flush()
    fail_step(s, late[1].id, ErrorClass.ENGINE_ERROR, "boom", retryable=False)
    s.refresh(paper)
    assert paper.status == "done" and paper.error is None


def test_a_prediction_keeps_its_inchikey(db_session):
    s = db_session
    paper = segmented(s, engine=Engine.FAKE)
    first, second = steps(s, paper, "ocsr")
    finish(s, first, OCSR)
    finish(s, second, {**OCSR, "smiles": "C(", "valid": False})
    keys = dict(s.execute(select(Prediction.smiles, Prediction.inchikey)).all())
    assert keys == {"CCO": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N", "C(": None}


def test_the_dispatcher_sends_a_papers_own_steps_before_background_ones(db_session):
    """On q.molnextr, an older DECIMER paper's background steps wait behind a newer MolNexTR
    paper's own read."""
    s = db_session
    owner = make_owner(s)
    older = segmented(s, owner=owner)
    newer = segmented(s, engine=Engine.MOLNEXTR, owner=owner)
    s.commit()
    step = pick_next(s, "q.molnextr")
    assert step is not None and step.paper_id == newer.id
    assert step.id not in background_ids(s)
    s.rollback()
    assert older.id != newer.id
