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


def test_background_steps_wait_behind_every_owners_own_steps(db_session):
    """A browser owner (priority class 0) outranks an API-key owner (1), but not with a
    background step: on q.molnextr the API owner's own read goes first."""
    from marcus.core.enums import OwnerKind

    s = db_session
    browser = segmented(s, owner=make_owner(s))
    api = segmented(s, engine=Engine.MOLNEXTR, owner=make_owner(s, OwnerKind.API_KEY))
    s.commit()
    step = pick_next(s, "q.molnextr")
    assert step is not None and step.paper_id == api.id
    assert step.id not in background_ids(s)
    s.rollback()
    assert browser.id != api.id


def _age(s, paper, engine, seconds):
    from datetime import UTC, datetime, timedelta

    for st in steps(s, paper, "ocsr"):
        if st.engine == engine:
            st.created_at = datetime.now(UTC) - timedelta(seconds=seconds)
    s.commit()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _decimer_done(s, paper):
    for st in steps(s, paper, "ocsr", "pending"):
        if st.engine == "decimer":
            finish(s, st, OCSR)
    s.commit()


def test_waiting_background_steps_expire_without_failing_anything(db_session):
    """q.molscribe has no live worker: its background steps are cancelled once it was seen
    unserved for its whole wait allowance; MolNexTR's (served) wait up to
    BACKGROUND_MAX_WAIT_S. Cancelled, not failed: the paper stays done."""
    from marcus.core.queues import QUEUE_WAIT_S
    from marcus.dispatcher.pick import BACKGROUND_MAX_WAIT_S, BackgroundWatch, watchdog_once

    s = db_session
    paper = segmented(s)
    _decimer_done(s, paper)
    _age(s, paper, "molscribe", 400)
    _age(s, paper, "molnextr", 400)
    clock = Clock()
    watch = BackgroundWatch(clock)
    live = {"q.decimer", "q.molnextr", "q.cpu"}
    watchdog_once(s, live_queues=lambda: live, watch=watch)  # first seen unserved: nothing yet
    assert {st.status for st in steps(s, paper, "ocsr") if st.engine != "decimer"} == {"pending"}
    clock.t += QUEUE_WAIT_S["q.molscribe"]
    watchdog_once(s, live_queues=lambda: live, watch=watch)
    by_engine = {st.engine: st.status for st in steps(s, paper, "ocsr")}
    assert by_engine == {"decimer": "done", "molnextr": "pending", "molscribe": "cancelled"}
    _age(s, paper, "molnextr", BACKGROUND_MAX_WAIT_S + 60)
    watchdog_once(s, watch=watch)  # no liveness known: only the time limit
    assert {st.status for st in steps(s, paper, "ocsr") if st.engine == "molnextr"} == {
        "cancelled"
    }
    s.refresh(paper)
    assert paper.status == "done" and paper.error is None


def test_one_missed_probe_cancels_nothing(db_session):
    """A worker restart or one broadcast reply missed: the queue is served again before its
    allowance has passed, so the count starts over."""
    from marcus.core.queues import QUEUE_WAIT_S
    from marcus.dispatcher.pick import BACKGROUND_PROBE_EVERY_S, BackgroundWatch, watchdog_once

    s = db_session
    paper = segmented(s)
    _decimer_done(s, paper)
    _age(s, paper, "molscribe", 1200)  # waited long, but the queue is what counts
    clock = Clock()
    watch = BackgroundWatch(clock)
    served = {"q.molnextr", "q.molscribe"}
    unserved = {"q.molnextr"}
    for live in (unserved, served, unserved):
        watchdog_once(s, live_queues=lambda live=live: live, watch=watch)
        clock.t += max(QUEUE_WAIT_S["q.molscribe"] - 10, BACKGROUND_PROBE_EVERY_S)
    assert {st.status for st in steps(s, paper, "ocsr") if st.engine == "molscribe"} == {
        "pending"
    }


def test_background_steps_alone_probe_at_most_once_a_minute(db_session):
    from marcus.dispatcher.pick import BACKGROUND_PROBE_EVERY_S, BackgroundWatch, watchdog_once

    s = db_session
    paper = segmented(s)
    _decimer_done(s, paper)
    clock = Clock()
    watch = BackgroundWatch(clock)
    calls = []

    def live():
        calls.append(clock.t)
        return {"q.molnextr", "q.molscribe", "q.decimer"}

    for _ in range(3):  # watchdog runs 10 s apart
        watchdog_once(s, live_queues=live, watch=watch)
        clock.t += 10
    assert len(calls) == 1
    clock.t += BACKGROUND_PROBE_EVERY_S
    watchdog_once(s, live_queues=live, watch=watch)
    assert len(calls) == 2


def test_a_step_asked_for_meanwhile_is_not_expired(db_session):
    """Review finding: the watchdog scans, then the user asks for MolScribe (the waiting
    background step becomes the paper's own, the done paper busy again), then the expiry runs
    on its earlier scan: the step stays the paper's own, and the paper ends normally."""
    from marcus.core.pipeline import request_ocsr
    from marcus.dispatcher.pick import BACKGROUND_MAX_WAIT_S, _waiting_background, expire_background

    s = db_session
    paper = segmented(s)
    _decimer_done(s, paper)
    _age(s, paper, "molscribe", BACKGROUND_MAX_WAIT_S + 60)
    scanned = _waiting_background(s)
    s.rollback()
    target = next(st for st in steps(s, paper, "ocsr") if st.engine == "molscribe")
    request_ocsr(s, target.segment_id, Engine.MOLSCRIBE)
    s.commit()
    assert expire_background(s, scanned, {"q.molscribe"}) == 1  # the other segment's step
    s.refresh(target)
    assert target.status == "pending" and target.id not in background_ids(s)
    s.refresh(paper)
    assert paper.status == "processing"
    finish(s, target, OCSR)
    s.refresh(paper)
    assert paper.status == "done"


def test_a_young_background_step_is_left_alone(db_session):
    from marcus.dispatcher.pick import watchdog_once

    s = db_session
    paper = segmented(s)
    s.commit()
    watchdog_once(s, live_queues=set)
    assert {st.status for st in steps(s, paper, "ocsr")} == {"pending"}
