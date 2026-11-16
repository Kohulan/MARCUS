"""Worker runtime: claim, handler, completion/failure mapping, attempt fencing, events.

run_step is called directly (no Celery worker); handlers are registered per test.
Events go to an in-memory fakeredis server that the test subscribes to.
"""

import json
import uuid

import fakeredis
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import func, select, update

from marcus.core import events
from marcus.core.db import sync_session
from marcus.core.enums import StepKind
from marcus.core.models import ImageJob, Paper, Prediction, Step
from marcus.workers import runtime
from marcus.workers.runtime import BadInput, register, run_step
from tests.factories import make_image_job, make_paper

OCSR_RESULT = {
    "smiles": "CCO",
    "molfile": None,
    "valid": True,
    "ms": 12,
    "engine_version": "test-1",
}


@pytest.fixture(autouse=True)
def handlers(monkeypatch):
    """Each test starts with an empty handler registry."""
    table: dict = {}
    monkeypatch.setattr(runtime, "HANDLERS", table)
    return table


@pytest.fixture
def bus(monkeypatch):
    """Route events to fakeredis; return a function that drains the received events."""
    server = fakeredis.FakeServer()
    monkeypatch.setattr(events, "get_redis", lambda: fakeredis.FakeRedis(server=server))
    sub = fakeredis.FakeRedis(server=server).pubsub(ignore_subscribe_messages=True)
    sub.psubscribe("marcus:*")

    def drain() -> list[tuple[str, dict]]:
        got, idle = [], 0
        while idle < 3:
            msg = sub.get_message(timeout=0.05)
            if msg is None:
                idle += 1
                continue
            got.append((msg["channel"].decode(), json.loads(msg["data"])))
        return got

    drain()  # consume the subscribe confirmation
    return drain


def queued_check_pdf(s) -> tuple[Paper, Step]:
    paper = make_paper(s)
    step = s.execute(select(Step).where(Step.paper_id == paper.id)).scalar_one()
    step.status = "queued"
    step.queued_at = func.now()
    s.commit()
    return paper, step


def reload(s, step_id) -> Step:
    s.expire_all()
    return s.get(Step, step_id)


def statuses(evts) -> list[str]:
    return [e["status"] for _, e in evts]


def requeue(s, step_id) -> None:
    s.execute(update(Step).where(Step.id == step_id).values(status="queued", queued_at=func.now()))
    s.commit()


# --- brief tests ---------------------------------------------------------------------------


def test_success_calls_complete_step_and_publishes(db_session, bus):
    s = db_session
    paper, step = queued_check_pdf(s)
    seen = {}

    def handler(view, session):
        seen["kind"], seen["paper_id"] = view.kind, view.paper_id
        # The claim is committed before the handler runs: another connection sees it.
        with sync_session() as other:
            seen["status"] = other.get(Step, view.id).status
        # The handler session can read.
        seen["display_name"] = session.execute(
            select(Paper.display_name).where(Paper.id == view.paper_id)
        ).scalar_one()
        return {"pages": 2}

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 0)

    assert seen == {
        "kind": "check_pdf",
        "paper_id": paper.id,
        "status": "running",
        "display_name": "paper.pdf",
    }
    row = reload(s, step.id)
    assert row.status == "done" and row.attempts == 1
    assert row.worker_name and row.started_at and row.finished_at
    kinds = sorted(k for (k,) in s.execute(select(Step.kind).where(Step.paper_id == paper.id)))
    assert kinds == ["check_pdf", "docling", "doi", "render_page", "render_page"]
    assert s.get(Paper, paper.id).status == "processing"

    evts = bus()
    assert [c for c, _ in evts] == [f"marcus:paper:{paper.id}"] * 2
    assert statuses(evts) == ["running", "done"]
    assert evts[1][1] == {
        "type": "step",
        "step_id": str(step.id),
        "kind": "check_pdf",
        "status": "done",
        "page": None,
        "segment_id": None,
    }


def test_soft_timeout_is_retried_then_failed_timeout(db_session, bus):
    s = db_session
    paper, step = queued_check_pdf(s)

    def handler(view, session):
        raise SoftTimeLimitExceeded()

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 0)
    row = reload(s, step.id)
    assert row.status == "pending" and row.attempts == 1
    assert row.error_class == "timeout" and row.error

    requeue(s, step.id)
    run_step(str(step.id), 1)
    row = reload(s, step.id)
    assert row.status == "failed" and row.attempts == 2 and row.error_class == "timeout"
    assert s.get(Paper, paper.id).status == "failed"
    assert statuses(bus()) == ["running", "pending", "running", "failed"]


def test_bad_input_not_retried(db_session, bus):
    s = db_session
    paper, step = queued_check_pdf(s)

    def handler(view, session):
        raise BadInput("not a PDF")

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 0)
    row = reload(s, step.id)
    assert row.status == "failed" and row.attempts == 1
    assert row.error_class == "bad_input" and row.error == "not a PDF"
    assert s.get(Paper, paper.id).status == "failed"
    assert statuses(bus()) == ["running", "failed"]


@pytest.mark.parametrize("status", ["cancelled", "pending", "done", "failed"])
def test_cancelled_step_is_skipped(db_session, bus, status):
    """Ruling 1: only a queued (or redelivered running) step is claimed; others are acked."""
    s = db_session
    _, step = queued_check_pdf(s)
    s.execute(update(Step).where(Step.id == step.id).values(status=status))
    s.commit()
    calls = []
    register(StepKind.CHECK_PDF, lambda view, session: calls.append(1) or {"pages": 1})

    run_step(str(step.id), 0)

    assert calls == []
    row = reload(s, step.id)
    assert row.status == status and row.attempts == 0 and row.worker_name is None
    assert bus() == []


def test_redelivered_running_step_counts_attempt_and_fails_worker_lost_after_two(db_session, bus):
    s = db_session
    _, step = queued_check_pdf(s)
    calls = []
    register(StepKind.CHECK_PDF, lambda view, session: calls.append(1) or {"pages": 1})

    # The first worker claimed it (attempt 1) and died: the redelivery is attempt 2 and runs.
    s.execute(update(Step).where(Step.id == step.id).values(status="running", attempts=1))
    s.commit()
    run_step(str(step.id), 0)  # the same message (sent at attempts=0) is redelivered
    assert calls == [1]
    row = reload(s, step.id)
    assert row.status == "done" and row.attempts == 2

    # A redelivery after two attempts is final: worker_lost, handler not called.
    _, step2 = queued_check_pdf(s)
    s.execute(update(Step).where(Step.id == step2.id).values(status="running", attempts=2))
    s.commit()
    run_step(str(step2.id), 1)  # this message (sent at attempts=1) was claimed, then lost
    assert calls == [1]
    row = reload(s, step2.id)
    assert row.status == "failed" and row.attempts == 2 and row.error_class == "worker_lost"
    assert statuses(bus()) == ["running", "done", "failed"]


# --- error mapping -------------------------------------------------------------------------


def test_engine_error_is_retried(db_session, bus):
    s = db_session
    _, step = queued_check_pdf(s)

    def handler(view, session):
        raise RuntimeError("x" * 5000)

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 0)
    row = reload(s, step.id)
    assert row.status == "pending" and row.attempts == 1
    assert row.error_class == "engine_error" and row.error == "x" * 2000


def test_bad_result_is_final_engine_error(db_session, bus):
    s = db_session
    paper, step = queued_check_pdf(s)
    register(StepKind.CHECK_PDF, lambda view, session: {"pages": "many"})

    run_step(str(step.id), 0)
    row = reload(s, step.id)
    assert row.status == "failed" and row.error_class == "engine_error"
    assert "pages" in row.error
    assert s.execute(select(func.count()).where(Step.paper_id == paper.id)).scalar_one() == 1
    assert statuses(bus()) == ["running", "failed"]


def test_missing_handler_is_final_engine_error(db_session, bus):
    s = db_session
    _, step = queued_check_pdf(s)

    run_step(str(step.id), 0)
    row = reload(s, step.id)
    assert row.status == "failed" and row.attempts == 1
    assert row.error_class == "engine_error" and row.error == "no handler for check_pdf"


def test_unknown_or_malformed_step_id_is_ignored(db_session, bus):
    run_step("not-a-uuid", 0)
    run_step("00000000-0000-0000-0000-000000000000", 0)
    assert bus() == []


# --- attempt fencing (ruling 2) ------------------------------------------------------------


def _take_over(step_id, **values) -> None:
    """Another delivery (or the watchdog) moves the step on while this handler runs."""
    with sync_session() as other:
        other.execute(update(Step).where(Step.id == step_id).values(**values))
        other.commit()


@pytest.mark.parametrize(
    "takeover",
    [
        {"attempts": Step.attempts + 1},  # redelivered and counted by another worker
        {"status": "pending", "started_at": None},  # watchdog put it back for a retry
    ],
)
def test_stale_attempt_result_is_dropped(db_session, bus, takeover):
    s = db_session
    paper, step = queued_check_pdf(s)

    def handler(view, session):
        _take_over(view.id, **takeover)
        return {"pages": 3}

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 0)

    row = reload(s, step.id)
    assert row.status in ("running", "pending") and row.finished_at is None
    assert s.execute(select(func.count()).where(Step.paper_id == paper.id)).scalar_one() == 1
    assert s.get(Paper, paper.id).pages is None
    assert statuses(bus()) == ["running"]


def test_stale_attempt_failure_is_dropped(db_session, bus):
    s = db_session
    _, step = queued_check_pdf(s)

    def handler(view, session):
        _take_over(view.id, attempts=Step.attempts + 1)
        raise BadInput("late")

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 0)

    row = reload(s, step.id)
    assert row.status == "running" and row.attempts == 2
    assert row.error_class is None and row.error is None
    assert statuses(bus()) == ["running"]


# --- events (ruling 5) ---------------------------------------------------------------------


def test_redis_down_does_not_fail_step(db_session, monkeypatch):
    s = db_session
    _, step = queued_check_pdf(s)
    dead = events.make_client("redis://127.0.0.1:1/0")  # nothing listens on port 1
    monkeypatch.setattr(events, "get_redis", lambda: dead)
    register(StepKind.CHECK_PDF, lambda view, session: {"pages": 1})

    run_step(str(step.id), 0)
    assert reload(s, step.id).status == "done"


def test_redis_client_error_does_not_fail_step(db_session, monkeypatch):
    s = db_session
    _, step = queued_check_pdf(s)

    def broken():
        raise RuntimeError("no redis configured")

    monkeypatch.setattr(events, "get_redis", broken)
    register(StepKind.CHECK_PDF, lambda view, session: {"pages": 1})

    run_step(str(step.id), 0)
    assert reload(s, step.id).status == "done"


def test_image_job_step_publishes_on_image_channel(db_session, bus):
    s = db_session
    job, step = make_image_job(s)
    step.status = "queued"
    s.commit()
    register(StepKind.OCSR, lambda view, session: dict(OCSR_RESULT))

    run_step(str(step.id), 0)

    assert reload(s, step.id).status == "done"
    assert s.get(ImageJob, job.id).status == "done"
    assert s.execute(select(Prediction.smiles)).scalar_one() == "CCO"
    evts = bus()
    assert [c for c, _ in evts] == [f"marcus:image:{job.id}"] * 2
    assert statuses(evts) == ["running", "done"]
    assert evts[0][1]["kind"] == "ocsr"


def test_publish_event_shape(monkeypatch):
    sent = []

    class Rec:
        def publish(self, channel, data):
            sent.append((channel, json.loads(data)))

    monkeypatch.setattr(events, "get_redis", Rec)
    pid = uuid.uuid4()
    events.publish_event(pid, {"type": "step", "step_id": uuid.uuid4(), "status": "done"})
    assert sent[0][0] == f"marcus:paper:{pid}" == events.paper_channel(pid)
    assert sent[0][1]["status"] == "done" and isinstance(sent[0][1]["step_id"], str)


# --- attempt token (amended ruling 1) ------------------------------------------------------


def test_stale_duplicate_message_never_touches_newer_attempt(db_session, bus):
    """Reviewer scenario: the watchdog re-queued a lost queued step (attempts 0 -> 1) and the
    dispatcher sent a second message (sent=1). The first message (sent=0) turns up late."""
    s = db_session
    _, step = queued_check_pdf(s)
    s.execute(update(Step).where(Step.id == step.id).values(attempts=1))
    s.commit()
    seen = {}

    def handler(view, session):
        # The stale first message arrives while attempt 2 runs: dropped, no worker_lost.
        run_step(str(view.id), 0)
        with sync_session() as other:
            row = other.get(Step, view.id)
            seen["during"] = (row.status, row.attempts, row.error_class)
        return {"pages": 1}

    register(StepKind.CHECK_PDF, handler)
    run_step(str(step.id), 1)

    assert seen["during"] == ("running", 2, None)
    row = reload(s, step.id)
    assert row.status == "done" and row.attempts == 2 and row.error_class is None
    assert statuses(bus()) == ["running", "done"]


def test_stale_message_for_requeued_step_is_dropped(db_session, bus):
    """The stale message arrives first: the step is queued with attempts 1, sent was 0."""
    s = db_session
    _, step = queued_check_pdf(s)
    s.execute(update(Step).where(Step.id == step.id).values(attempts=1))
    s.commit()
    calls = []
    register(StepKind.CHECK_PDF, lambda view, session: calls.append(1) or {"pages": 1})

    run_step(str(step.id), 0)

    assert calls == []
    row = reload(s, step.id)
    assert row.status == "queued" and row.attempts == 1 and row.worker_name is None
    assert bus() == []


def test_redelivery_of_other_attempt_is_dropped(db_session, bus):
    """running with attempts != sent + 1 is not this message's attempt: ack and drop."""
    s = db_session
    _, step = queued_check_pdf(s)
    s.execute(update(Step).where(Step.id == step.id).values(status="running", attempts=2))
    s.commit()

    run_step(str(step.id), 0)

    row = reload(s, step.id)
    assert row.status == "running" and row.attempts == 2 and row.error_class is None
    assert bus() == []


def test_soft_timeout_inside_publish_propagates(monkeypatch):
    class Slow:
        def publish(self, channel, data):
            raise SoftTimeLimitExceeded()

    monkeypatch.setattr(events, "get_redis", Slow)
    with pytest.raises(SoftTimeLimitExceeded):
        events.publish_event(uuid.uuid4(), {"type": "step"})
