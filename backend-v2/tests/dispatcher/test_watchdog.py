from datetime import UTC, datetime, timedelta

from marcus.core.enums import StepKind
from marcus.core.models import Step
from marcus.core.queues import TIME_LIMITS
from marcus.dispatcher.pick import GRACE_S, fail_if_stuck, watchdog_once
from tests.factories import make_image_job, make_paper

OCSR_HARD = TIME_LIMITS[StepKind.OCSR][1]


def ago(seconds: float) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)


def ocsr_step(s, paper, seq=0, **kw) -> Step:
    step = Step(
        paper_id=paper.id,
        kind=StepKind.OCSR.value,
        queue="q.decimer",
        engine="decimer",
        seq=seq,
        **kw,
    )
    s.add(step)
    s.flush()
    return step


def test_watchdog_requeues_stuck_running_step_then_fails_it(db_session):
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(
        s, paper, status="running", attempts=1, queued_at=ago(200),
        started_at=ago(OCSR_HARD + GRACE_S + 5),
    )  # fmt: skip
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "pending"
    assert row.error_class == "worker_lost"
    assert row.queued_at is None and row.started_at is None

    # The retry starts and gets stuck too: the second failure is final.
    row.status = "running"
    row.attempts = 2
    row.queued_at = ago(200)
    row.started_at = ago(OCSR_HARD + GRACE_S + 5)
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "failed" and row.error_class == "worker_lost"
    assert row.finished_at is not None


def test_watchdog_requeues_stuck_queued_step(db_session):
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(OCSR_HARD + GRACE_S + 5))
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    assert s.get(Step, stuck.id).status == "pending"


def test_watchdog_lost_delivery_twice_is_final(db_session):
    """A queued step that never starts counts as an attempt, so it cannot loop forever."""
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(OCSR_HARD + GRACE_S + 5))
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "pending" and row.attempts == 1
    assert row.error_class == "worker_lost"

    # Dispatched again, and the delivery is lost again: the second loss is final.
    row.status = "queued"
    row.queued_at = ago(OCSR_HARD + GRACE_S + 5)
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "failed" and row.error_class == "worker_lost"
    assert row.attempts == 2 and row.finished_at is not None


def test_watchdog_leaves_healthy_and_finished_steps(db_session):
    s = db_session
    paper = make_paper(s)
    within = ocsr_step(
        s, paper, seq=0, status="running", attempts=1, started_at=ago(OCSR_HARD + GRACE_S - 10)
    )
    queued = ocsr_step(s, paper, seq=1, status="queued", queued_at=ago(10))
    done = ocsr_step(s, paper, seq=2, status="done", started_at=ago(1000), finished_at=ago(900))
    # docling has a much longer hard limit than ocsr: 200 s is not stuck for docling.
    docling = Step(
        paper_id=paper.id, kind="docling", queue="q.cpu", seq=100_000, status="running",
        attempts=1, started_at=ago(200),
    )  # fmt: skip
    s.add(docling)
    s.commit()

    assert watchdog_once(s) == 0
    s.expire_all()
    assert s.get(Step, within.id).status == "running"
    assert s.get(Step, queued.id).status == "queued"
    assert s.get(Step, done.id).status == "done"
    assert s.get(Step, docling.id).status == "running"


def test_fail_if_stuck_rechecks_before_failing(db_session):
    """A step that finished (or got fresh) after the scan is left alone."""
    s = db_session
    paper = make_paper(s)
    step = ocsr_step(s, paper, status="running", attempts=1, started_at=ago(5))
    s.commit()

    assert fail_if_stuck(s, step.id) is False
    s.expire_all()
    assert s.get(Step, step.id).status == "running"


def test_fail_if_stuck_ignores_deleted_paper(db_session):
    """A deleted parent: no attempt is added and the step is not reported as failed."""
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(OCSR_HARD + GRACE_S + 5))
    paper.status = "deleted"
    s.commit()

    assert fail_if_stuck(s, stuck.id) is False
    s.rollback()
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "queued" and row.attempts == 0


def test_fail_if_stuck_ignores_deleted_image_job(db_session):
    s = db_session
    job, step = make_image_job(s)
    step.status = "queued"
    step.queued_at = ago(OCSR_HARD + GRACE_S + 5)
    job.status = "deleted"
    s.commit()

    assert fail_if_stuck(s, step.id) is False
    s.rollback()
    s.expire_all()
    row = s.get(Step, step.id)
    assert row.status == "queued" and row.attempts == 0


def test_running_step_without_started_at_uses_queued_at(db_session):
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(
        s, paper, status="running", attempts=1, queued_at=ago(OCSR_HARD + GRACE_S + 5)
    )
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "pending" and row.error_class == "worker_lost"
