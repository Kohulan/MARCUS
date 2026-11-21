from datetime import UTC, datetime, timedelta

from marcus.core.enums import StepKind
from marcus.core.models import Step
from marcus.core.queues import QUEUE_WAIT_S, TIME_LIMITS
from marcus.dispatcher.pick import GRACE_S, fail_if_stuck, watchdog_once
from tests.factories import make_image_job, make_paper

OCSR_HARD = TIME_LIMITS[StepKind.OCSR][1]
DECIMER_WAIT = QUEUE_WAIT_S["q.decimer"]


def ago(seconds: float) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)


def ocsr_step(s, paper, seq=0, engine="decimer", **kw) -> Step:
    step = Step(
        paper_id=paper.id,
        kind=StepKind.OCSR.value,
        queue="q.decimer",
        engine=engine,
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
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(DECIMER_WAIT + 5))
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    assert s.get(Step, stuck.id).status == "pending"


def test_watchdog_lost_delivery_twice_is_final(db_session):
    """A queued step that never starts counts as an attempt, so it cannot loop forever."""
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(DECIMER_WAIT + 5))
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "pending" and row.attempts == 1
    assert row.error_class == "worker_lost"

    # Dispatched again, and the delivery is lost again: the second loss is final.
    row.status = "queued"
    row.queued_at = ago(DECIMER_WAIT + 5)
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
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(DECIMER_WAIT + 5))
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
    step.queued_at = ago(DECIMER_WAIT + 5)
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


def test_watchdog_does_not_fail_100_page_docling_at_400s(db_session):
    s = db_session
    paper = make_paper(s)
    paper.pages = 100
    big = Step(
        paper_id=paper.id, kind="docling", queue="q.cpu", seq=100_000, status="running",
        attempts=1, started_at=ago(400),
    )  # fmt: skip
    small_paper = make_paper(s)
    small_paper.pages = 2
    small = Step(
        paper_id=small_paper.id, kind="docling", queue="q.cpu", seq=100_000, status="running",
        attempts=1, started_at=ago(400),
    )  # fmt: skip
    s.add_all([big, small])
    s.commit()
    assert watchdog_once(s) == 1  # only the 2-page paper is past 360 + 30 s
    s.expire_all()
    assert s.get(Step, big.id).status == "running"
    assert s.get(Step, small.id).status != "running"


def test_watchdog_gives_decimer_hand_its_longer_deadline(db_session):
    """decimer-hand steps may run up to their own hard limit (model load on first request)."""
    from marcus.core.enums import Engine
    from marcus.core.queues import time_limits_for

    hand_hard = time_limits_for(StepKind.OCSR, None, Engine.DECIMER_HAND)[1]
    s = db_session
    paper = make_paper(s)
    loading = ocsr_step(
        s, paper, seq=0, engine="decimer-hand", status="running",
        attempts=1, queued_at=ago(OCSR_HARD + GRACE_S + 60),
        started_at=ago(OCSR_HARD + GRACE_S + 50),
    )  # fmt: skip
    normal = ocsr_step(
        s, paper, seq=1, status="running", attempts=1, queued_at=ago(OCSR_HARD + GRACE_S + 60),
        started_at=ago(OCSR_HARD + GRACE_S + 50),
    )  # fmt: skip
    stuck = ocsr_step(
        s, paper, seq=2, engine="decimer-hand", status="running", attempts=1,
        queued_at=ago(hand_hard + GRACE_S + 60), started_at=ago(hand_hard + GRACE_S + 5),
    )  # fmt: skip
    s.commit()

    assert watchdog_once(s) == 2
    s.expire_all()
    assert s.get(Step, loading.id).status == "running"
    assert s.get(Step, normal.id).status == "pending"
    assert s.get(Step, stuck.id).status == "pending"


def test_queued_step_waits_for_a_worker_restart_not_the_run_limit(db_session):
    """A q.decimer step queued while the pool process preloads its model (~100 s) is not lost:
    queued steps get QUEUE_WAIT_S[queue], not hard + grace."""
    s = db_session
    paper = make_paper(s)
    waiting = ocsr_step(s, paper, seq=0, status="queued", queued_at=ago(100))
    assert 100 > OCSR_HARD + GRACE_S  # the old allowance would have failed it
    lost = ocsr_step(s, paper, seq=1, status="queued", queued_at=ago(DECIMER_WAIT + 1))
    s.commit()

    assert watchdog_once(s) == 1
    s.expire_all()
    assert s.get(Step, waiting.id).status == "queued"
    row = s.get(Step, lost.id)
    assert row.status == "pending" and row.error_class == "worker_lost"
    assert row.attempts == 1  # a lost delivery still counts as an attempt


def test_queue_wait_is_per_queue(db_session, monkeypatch):
    from marcus.dispatcher import pick

    monkeypatch.setitem(pick.QUEUE_WAIT_S, "q.decimer", 50)
    s = db_session
    paper = make_paper(s)
    step = ocsr_step(s, paper, status="queued", queued_at=ago(60))
    cpu = Step(
        paper_id=paper.id, kind="check_pdf", queue="q.cpu", seq=100_000, status="queued",
        queued_at=ago(60),
    )  # fmt: skip
    s.add(cpu)
    s.commit()
    assert watchdog_once(s) == 1  # q.decimer at 50 s; q.cpu still has 120 s
    s.expire_all()
    assert s.get(Step, step.id).status == "pending"
    assert s.get(Step, cpu.id).status == "queued"


def test_running_deadline_unchanged(db_session):
    s = db_session
    paper = make_paper(s)
    within = ocsr_step(
        s, paper, seq=0, status="running", attempts=1, queued_at=ago(400),
        started_at=ago(OCSR_HARD + GRACE_S - 5),
    )  # fmt: skip
    over = ocsr_step(
        s, paper, seq=1, status="running", attempts=1, queued_at=ago(400),
        started_at=ago(OCSR_HARD + GRACE_S + 5),
    )  # fmt: skip
    s.commit()
    assert watchdog_once(s) == 1
    s.expire_all()
    assert s.get(Step, within.id).status == "running"
    assert s.get(Step, over.id).status == "pending"


# --- a queue with no live consumer: a lost delivery is not the step's fault ----------------


def test_unserved_queue_requeues_without_counting_an_attempt(db_session):
    """No worker consumes q.decimer (e.g. the GPU is in Exclusive_Process after a reboot):
    the step goes back to pending with no attempt counted, however often it happens, so it
    runs when a worker comes back instead of ending as a final worker_lost."""
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(DECIMER_WAIT + 5))
    s.commit()
    asked = []

    def live():
        asked.append(1)
        return {"q.cpu", "q.segment"}

    for _ in range(3):
        assert watchdog_once(s, live_queues=live) == 1
        s.expire_all()
        row = s.get(Step, stuck.id)
        assert row.status == "pending" and row.attempts == 0 and row.queued_at is None
        assert row.error_class is None and row.finished_at is None
        row.status = "queued"  # dispatched again, still nobody consumes it
        row.queued_at = ago(DECIMER_WAIT + 5)
        s.commit()
    assert len(asked) == 3  # one consumer check per watchdog run
    s.refresh(paper)
    assert paper.status != "failed"


def test_served_queue_still_counts_a_lost_delivery(db_session):
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(DECIMER_WAIT + 5))
    s.commit()
    assert watchdog_once(s, live_queues=lambda: {"q.decimer"}) == 1
    s.expire_all()
    row = s.get(Step, stuck.id)
    assert row.status == "pending" and row.attempts == 1 and row.error_class == "worker_lost"


def test_unknown_consumers_count_no_attempt(db_session):
    """The consumer check failed (None): do not burn attempts while it cannot be told."""
    s = db_session
    paper = make_paper(s)
    stuck = ocsr_step(s, paper, status="queued", queued_at=ago(DECIMER_WAIT + 5))
    s.commit()

    def broken():
        raise RuntimeError("broker gone")

    for probe in (lambda: None, broken):
        assert watchdog_once(s, live_queues=probe) == 1
        s.expire_all()
        row = s.get(Step, stuck.id)
        assert row.status == "pending" and row.attempts == 0
        row.status = "queued"
        row.queued_at = ago(DECIMER_WAIT + 5)
        s.commit()


def test_consumer_check_only_for_stuck_queued_steps(db_session):
    """A running step past its deadline is a real loss (a worker took it): no broadcast."""
    s = db_session
    paper = make_paper(s)
    ocsr_step(
        s, paper, status="running", attempts=1, queued_at=ago(200),
        started_at=ago(OCSR_HARD + GRACE_S + 5),
    )  # fmt: skip
    ocsr_step(s, paper, seq=1, status="queued", queued_at=ago(10))  # not stuck
    s.commit()

    def live():
        raise AssertionError("not asked")

    assert watchdog_once(s, live_queues=live) == 1
