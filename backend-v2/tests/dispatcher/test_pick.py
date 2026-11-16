import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from marcus.core.db import get_sync_sessionmaker
from marcus.core.enums import OwnerKind, StepKind
from marcus.core.models import Paper, Step
from marcus.core.queues import SLOTS
from marcus.dispatcher.pick import dispatch_once, free_slots, pick_next
from tests.factories import make_image_job, make_owner, make_paper

Q = "q.decimer"


def add_steps(s, paper, n, status="pending", seq0=0, finished_ago=None, **kw) -> list[Step]:
    finished_at = datetime.now(UTC) - timedelta(seconds=finished_ago) if finished_ago else None
    new = [
        Step(
            paper_id=paper.id,
            kind=StepKind.OCSR.value,
            queue=Q,
            engine="decimer",
            seq=seq0 + i,
            status=status,
            finished_at=finished_at,
            **kw,
        )
        for i in range(n)
    ]
    s.add_all(new)
    s.flush()
    return new


def paper_at(s, owner, minutes_ago: int) -> Paper:
    """A paper whose created_at is `minutes_ago` in the past (one transaction shares now())."""
    paper = make_paper(s, owner)
    paper.created_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    s.flush()
    return paper


class Sent:
    def __init__(self, fail_on: set | None = None):
        self.calls: list[tuple[str, uuid.UUID, StepKind, int]] = []
        self.pages: list[int | None] = []
        self.engines: list[str | None] = []
        self.fail_on = fail_on or set()

    def __call__(self, queue, step_id, kind, attempts, pages=None, engine=None):
        if queue in self.fail_on:
            raise ConnectionError("broker down")
        self.calls.append((queue, step_id, kind, attempts))
        self.pages.append(pages)
        self.engines.append(engine)

    def ids(self, queue=Q):
        return [sid for q, sid, _, _ in self.calls if q == queue]


@pytest.fixture
def one_slot(monkeypatch):
    monkeypatch.setitem(SLOTS, Q, 1)


def test_small_paper_jumps_big_paper_backlog(db_session, one_slot):
    s = db_session
    a, b = make_owner(s), make_owner(s)
    big = paper_at(s, a, minutes_ago=10)
    add_steps(s, big, 5, status="done", seq0=0, finished_ago=60)
    add_steps(s, big, 190, seq0=5)
    small = paper_at(s, b, minutes_ago=1)  # uploaded later
    small_steps = add_steps(s, small, 15)

    picked = pick_next(s, Q)
    assert picked is not None
    assert picked.paper_id == small.id
    assert picked.id == small_steps[0].id  # lowest seq of the small paper


def test_usage_outside_window_is_ignored(db_session, one_slot):
    s = db_session
    a, b = make_owner(s), make_owner(s)
    big = paper_at(s, a, minutes_ago=30)
    add_steps(s, big, 5, status="done", finished_ago=600)  # older than the 300 s window
    first = add_steps(s, big, 3, seq0=5)
    small = paper_at(s, b, minutes_ago=1)
    add_steps(s, small, 3)

    assert pick_next(s, Q).id == first[0].id  # equal usage: oldest paper wins


def test_browser_before_api_key(db_session, one_slot):
    s = db_session
    api = make_owner(s, OwnerKind.API_KEY)
    browser = make_owner(s, OwnerKind.BROWSER)
    api_paper = paper_at(s, api, minutes_ago=30)
    add_steps(s, api_paper, 3)
    browser_paper = paper_at(s, browser, minutes_ago=1)
    add_steps(s, browser_paper, 3, status="done", seq0=0, finished_ago=30)  # browser busier
    wanted = add_steps(s, browser_paper, 3, seq0=3)

    assert pick_next(s, Q).id == wanted[0].id


def test_oldest_paper_first_within_one_owner(db_session, one_slot):
    s = db_session
    owner = make_owner(s)
    newer = paper_at(s, owner, minutes_ago=1)
    add_steps(s, newer, 3, seq0=0)  # lower seq, but newer paper
    older = paper_at(s, owner, minutes_ago=20)
    older_steps = add_steps(s, older, 3, seq0=7)

    assert pick_next(s, Q).id == older_steps[0].id


def test_image_job_steps_are_picked(db_session, one_slot):
    s = db_session
    job, step = make_image_job(s)
    assert pick_next(s, Q).id == step.id


def test_pick_ignores_other_queues_and_statuses(db_session, one_slot):
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    add_steps(s, paper, 1, status="running")
    add_steps(s, paper, 1, status="failed", seq0=1)
    assert pick_next(s, Q) is None


def test_free_slots_counts_queued_and_running(db_session, monkeypatch):
    monkeypatch.setitem(SLOTS, Q, 3)
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    add_steps(s, paper, 1, status="queued")
    add_steps(s, paper, 1, status="running", seq0=1)
    add_steps(s, paper, 2, status="pending", seq0=2)
    add_steps(s, paper, 1, status="done", seq0=4, finished_ago=5)
    assert free_slots(s, Q) == 1


def test_free_slots_respected(db_session, one_slot):
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    (busy,) = add_steps(s, paper, 1, status="running")
    waiting = add_steps(s, paper, 2, seq0=1)
    s.commit()

    sent = Sent()
    dispatch_once(s, sent)
    assert sent.ids() == []
    s.expire_all()
    assert {s.get(Step, st.id).status for st in waiting} == {"pending"}

    busy = s.get(Step, busy.id)
    busy.status = "done"
    busy.finished_at = datetime.now(UTC)
    s.commit()
    dispatch_once(s, sent)
    assert sent.ids() == [waiting[0].id]


def test_dispatch_marks_queued_and_sends_kind(db_session, monkeypatch):
    monkeypatch.setitem(SLOTS, Q, 2)
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    pending = add_steps(s, paper, 3)
    s.commit()

    sent = Sent()
    n = dispatch_once(s, sent)
    # 2 decimer slots, plus the paper's check_pdf step on q.cpu
    assert n == 3
    assert sent.ids() == [pending[0].id, pending[1].id]
    assert all(kind == StepKind.OCSR for q, _, kind, _ in sent.calls if q == Q)
    assert [kind for q, _, kind, _ in sent.calls if q == "q.cpu"] == [StepKind.CHECK_PDF]
    s.expire_all()
    for st in pending[:2]:
        row = s.get(Step, st.id)
        assert row.status == "queued" and row.queued_at is not None
    assert s.get(Step, pending[2].id).status == "pending"


def test_dispatch_commits_before_send(db_session, one_slot):
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    (step,) = add_steps(s, paper, 1)
    s.commit()
    seen: list[str] = []

    def send(queue, step_id, kind, attempts, pages=None, engine=None):
        if queue != Q:
            return
        with get_sync_sessionmaker()() as other:  # a worker reading the row
            seen.append(other.execute(select(Step.status).where(Step.id == step_id)).scalar_one())

    dispatch_once(s, send)
    assert seen == ["queued"]


def test_send_failure_puts_step_back_to_pending(db_session, one_slot):
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    (step,) = add_steps(s, paper, 1)
    s.commit()

    sent = Sent(fail_on={Q})
    n = dispatch_once(s, sent)
    assert n == 1  # only the q.cpu check_pdf step went out
    s.expire_all()
    row = s.get(Step, step.id)
    assert row.status == "pending" and row.queued_at is None


@pytest.mark.parametrize("pending", [1, 3])
def test_two_dispatchers_never_send_same_step(db_session, one_slot, pending):
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    add_steps(s, paper, pending)
    s.commit()

    start = threading.Barrier(2, timeout=10)
    both_picked = threading.Barrier(2, timeout=10)
    picked: list[uuid.UUID | None] = []
    errors: list[BaseException] = []

    def dispatcher():
        try:
            with get_sync_sessionmaker()() as ds:
                start.wait()
                step = pick_next(ds, Q)
                picked.append(step.id if step else None)
                # Hold this transaction (and its row lock) open until the other one has picked.
                both_picked.wait()
                ds.rollback()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=dispatcher) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    assert len(picked) == 2
    got = [p for p in picked if p is not None]
    assert len(got) == len(set(got)) == min(pending, 2)


def test_main_module_imports_without_celery():
    import marcus.dispatcher.__main__ as main_mod

    assert callable(main_mod.main)
    assert (
        main_mod.psycopg_conninfo("postgresql+asyncpg://u:p@h:5432/db")
        == "postgresql://u:p@h:5432/db"
    )


def test_cancelled_steps_do_not_count_as_usage(db_session, one_slot):
    """Spec §8 counts steps running or done; a cancelled step used no slot time."""
    s = db_session
    a, b = make_owner(s), make_owner(s)
    a_paper = paper_at(s, a, minutes_ago=10)
    add_steps(s, a_paper, 5, status="cancelled", seq0=0, finished_ago=60)
    a_pending = add_steps(s, a_paper, 3, seq0=5)
    b_paper = paper_at(s, b, minutes_ago=5)
    add_steps(s, b_paper, 1, status="done", seq0=0, finished_ago=60)
    add_steps(s, b_paper, 3, seq0=1)

    picked = pick_next(s, Q)
    assert picked is not None and picked.id == a_pending[0].id


def test_dispatch_sends_attempts_token(db_session, one_slot):
    """The message carries the step's attempts at queue time (the runtime's fence token)."""
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    (step,) = add_steps(s, paper, 1, attempts=1)  # retry after one failed attempt
    s.commit()

    sent = Sent()
    dispatch_once(s, sent)
    assert [(sid, a) for q, sid, _, a in sent.calls if q == Q] == [(step.id, 1)]
    assert [a for q, _, _, a in sent.calls if q == "q.cpu"] == [0]


def test_dispatch_sends_docling_pages_and_scaled_limits(db_session):
    from marcus.core.queues import time_limits_for

    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    paper.pages = 100
    s.add(
        Step(
            paper_id=paper.id, kind="docling", queue="q.cpu", seq=100_000, status="pending",
        )
    )
    s.commit()
    sent = Sent()
    dispatch_once(s, sent)
    docling = [(c, p) for c, p in zip(sent.calls, sent.pages) if c[2] == StepKind.DOCLING]
    assert [p for _, p in docling] == [100]
    assert time_limits_for(StepKind.DOCLING, 100) == (1260, 1320)


def test_celery_send_uses_scaled_limits(monkeypatch):
    from marcus.core import celery_app as ca
    from marcus.dispatcher.__main__ import celery_send

    seen = {}
    monkeypatch.setattr(
        ca.celery_app, "send_task", lambda name, **kw: seen.update(kw)
    )
    celery_send()("q.cpu", uuid.uuid4(), StepKind.DOCLING, 0, 100)
    assert (seen["soft_time_limit"], seen["time_limit"]) == (1260, 1320)
    celery_send()("q.cpu", uuid.uuid4(), StepKind.CHECK_PDF, 0, None)
    assert (seen["soft_time_limit"], seen["time_limit"]) == (20, 30)


def test_dispatch_sends_the_ocsr_engine(db_session, one_slot):
    s = db_session
    paper = paper_at(s, make_owner(s), minutes_ago=1)
    (step,) = add_steps(s, paper, 1)
    step.engine = "decimer-hand"
    s.commit()
    sent = Sent()
    dispatch_once(s, sent)
    assert [e for c, e in zip(sent.calls, sent.engines) if c[0] == Q] == ["decimer-hand"]
    assert [e for c, e in zip(sent.calls, sent.engines) if c[0] == "q.cpu"] == [None]


def test_celery_send_uses_decimer_hand_limits(monkeypatch):
    from marcus.core import celery_app as ca
    from marcus.dispatcher.__main__ import celery_send

    seen = {}
    monkeypatch.setattr(ca.celery_app, "send_task", lambda name, **kw: seen.update(kw))
    celery_send()("q.decimer", uuid.uuid4(), StepKind.OCSR, 0, None, "decimer-hand")
    assert (seen["soft_time_limit"], seen["time_limit"]) == (180, 210)
    celery_send()("q.decimer", uuid.uuid4(), StepKind.OCSR, 0, None, "decimer")
    assert (seen["soft_time_limit"], seen["time_limit"]) == (30, 45)
