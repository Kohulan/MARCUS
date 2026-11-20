"""Fair dispatcher core: choose the next step per queue, hand it to Celery, rescue stuck steps.

Every function takes a sync SQLAlchemy Session. Unlike the planner, these functions own
their transactions and commit: a step is marked `queued` and committed before it is sent,
so a fast worker never sees it still `pending`.

Lock order. The planner locks the paper (or image job) row, then the step row.
- pick_next locks ONLY the step row (FOR UPDATE OF s SKIP LOCKED), never the paper, so it
  can never wait in a cycle with the planner; a step the planner holds is simply skipped.
- watchdog locks the parent row, then the step row, the same order as the planner.
"""

import logging
import uuid
from collections.abc import Callable

from sqlalchemy import case, func, select, text, update
from sqlalchemy.orm import Session

from marcus.core.enums import WAITING_STEPS, ErrorClass, StepKind, StepStatus
from marcus.core.models import Paper, Step
from marcus.core.pipeline import fail_step, lock_parent, parent_gone
from marcus.core.queues import (
    DOCLING_FIXED_S,
    DOCLING_HARD_EXTRA_S,
    DOCLING_MIN_SOFT_S,
    DOCLING_PER_PAGE_S,
    ENGINE_TIME_LIMITS,
    QUEUE_WAIT_S,
    SLOTS,
    TIME_LIMITS,
    docling_slots,
    queue_for,
)
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

GRACE_S = 30  # watchdog: a step may run for its hard limit plus this

# send(queue, step_id, kind, attempts, pages, engine): `attempts` is the step's attempts value
# read in the transaction that set it queued; the runtime uses it to drop stale duplicate
# messages. `pages` is the paper's page count for docling steps (it scales the time limits),
# else None. `engine` is the step's OCSR engine (it may have its own time limits), else None.
Send = Callable[[str, uuid.UUID, StepKind, int, int | None, str | None], None]

# live_queues(): names of the queues at least one live worker consumes, or None when that
# cannot be told (broker down, broadcast hung). Asked by the watchdog only for a step stuck in
# `queued`, at most once per run.
LiveQueues = Callable[[], "set[str] | frozenset[str] | None"]

_BUSY = (StepStatus.QUEUED.value, StepStatus.RUNNING.value)

# Order: priority class, then owner usage on this queue in the fair window (steps busy now
# or finished in the window, cancelled ones excluded: spec §8 counts running or done), then
# the oldest paper / image job, then step order. One statement; the chosen row is locked, rows another
# dispatcher (or the planner) holds are skipped. `docling_ok` false leaves docling steps out (the
# docling cap, queues.docling_slots, is reached).
_PICK_SQL = text(
    """
    WITH usage AS (
      SELECT COALESCE(p.owner_id, j.owner_id) AS owner_id, count(*) AS n
      FROM steps s LEFT JOIN papers p ON p.id = s.paper_id
                   LEFT JOIN image_jobs j ON j.id = s.image_job_id
      WHERE s.queue = :q AND (s.status IN ('queued','running')
            OR (s.finished_at > now() - make_interval(secs => :window)
                AND s.status <> 'cancelled'))
      GROUP BY 1)
    SELECT s.* FROM steps s
      LEFT JOIN papers p ON p.id = s.paper_id LEFT JOIN image_jobs j ON j.id = s.image_job_id
      JOIN owners o ON o.id = COALESCE(p.owner_id, j.owner_id)
      LEFT JOIN usage u ON u.owner_id = o.id
    WHERE s.queue = :q AND s.status = 'pending' AND (s.kind <> 'docling' OR :docling_ok)
    ORDER BY o.priority_class, COALESCE(u.n, 0), COALESCE(p.created_at, j.created_at),
             s.seq, s.created_at
    LIMIT 1 FOR UPDATE OF s SKIP LOCKED
    """
)


def slot_usage(session: Session) -> tuple[dict[str, int], int]:
    """(free slots per queue, docling steps queued or running), one statement: SLOTS[queue] minus
    the steps of that queue that are queued or running."""
    rows = session.execute(
        select(Step.queue, func.count(), func.count().filter(Step.kind == StepKind.DOCLING.value))
        .where(Step.status.in_(_BUSY))
        .group_by(Step.queue)
    ).all()
    busy = {queue: n for queue, n, _ in rows}
    return {q: slots - busy.get(q, 0) for q, slots in SLOTS.items()}, sum(d for *_, d in rows)


def pick_next(session: Session, queue: str, allow_docling: bool = True) -> Step | None:
    """Lock and return the next pending step of `queue` in fair order, or None.

    `allow_docling=False` skips docling steps. The row stays locked until the caller ends the
    transaction.
    """
    stmt = select(Step).from_statement(_PICK_SQL).execution_options(populate_existing=True)
    params = {
        "q": queue,
        "window": float(get_settings().fair_window_s),
        "docling_ok": allow_docling,
    }
    return session.execute(stmt, params).scalars().first()


def _put_back(session: Session, step_id: uuid.UUID) -> None:
    """A queued step back to pending (no attempt counted), only if nobody moved it on since.
    Does not commit."""
    session.execute(
        update(Step)
        .where(Step.id == step_id, Step.status == StepStatus.QUEUED.value)
        .values(status=StepStatus.PENDING.value, queued_at=None)
        .execution_options(synchronize_session=False)
    )


def dispatch_once(session: Session, send: Send) -> int:
    """Fill every free slot of every queue. Returns the number of steps sent.

    Per step: mark it `queued` (+ queued_at), commit, then send. If send raises, the step
    goes back to `pending` in a new transaction and the dispatcher moves to the next queue.
    Docling (on q.cpu) never takes more than queues.docling_slots() slots.

    The busy steps are counted once per call and then kept locally (one per step sent): only
    this (single) dispatcher makes steps busy, everything else only frees slots, so the local
    count can only be too high, never too low; a slot freed meanwhile is filled on the next
    wake.
    """
    sent = 0
    free, docling = slot_usage(session)
    for queue in SLOTS:  # stable order
        while free[queue] > 0:
            allow_docling = queue != "q.cpu" or docling < docling_slots()
            step = pick_next(session, queue, allow_docling)
            if step is None:
                break
            step_id, kind, attempts = step.id, StepKind(step.kind), step.attempts
            engine = step.engine
            pages = None
            if kind is StepKind.DOCLING and step.paper_id is not None:
                pages = session.execute(
                    select(Paper.pages).where(Paper.id == step.paper_id)
                ).scalar_one_or_none()
            step.status = StepStatus.QUEUED.value
            step.queued_at = func.now()
            session.commit()
            try:
                send(queue, step_id, kind, attempts, pages, engine)
            except Exception:
                log.exception("send failed for step %s on %s; back to pending", step_id, queue)
                session.rollback()
                _put_back(session, step_id)
                session.commit()
                break
            sent += 1
            free[queue] -= 1
            docling += kind is StepKind.DOCLING
        session.rollback()  # end the read-only transaction of the last pick
    return sent


# --- watchdog ------------------------------------------------------------------------------


def _deadline_s():
    """Per-step allowance in seconds: the hard limit of its kind (or of its kind and engine,
    ENGINE_TIME_LIMITS) plus the grace. Docling's hard limit depends on the paper's page count
    (same formulas as queues.time_limits_for)."""
    pages = select(func.coalesce(Paper.pages, 0)).where(Paper.id == Step.paper_id).scalar_subquery()
    docling_hard = (
        func.greatest(DOCLING_MIN_SOFT_S, DOCLING_FIXED_S + DOCLING_PER_PAGE_S * pages)
        + DOCLING_HARD_EXTRA_S
        + GRACE_S
    )
    return case(
        (Step.kind == StepKind.DOCLING.value, docling_hard),
        *(
            ((Step.kind == kind.value) & (Step.engine == engine.value), hard + GRACE_S)
            for (kind, engine), (_, hard) in ENGINE_TIME_LIMITS.items()
        ),
        *(
            (Step.kind == kind.value, hard + GRACE_S)
            for kind, (_, hard) in TIME_LIMITS.items()
            if kind is not StepKind.DOCLING
        ),
        else_=max(hard for _, hard in [*TIME_LIMITS.values(), *ENGINE_TIME_LIMITS.values()])
        + GRACE_S,
    )


def _queue_wait_s():
    """Allowance in seconds for a step in `queued`: QUEUE_WAIT_S of its queue (independent of
    its run limit; covers a worker restart with model preload)."""
    return case(
        *((Step.queue == queue, wait) for queue, wait in QUEUE_WAIT_S.items()),
        else_=max(QUEUE_WAIT_S.values()),
    )


def _stuck():
    """SQL condition: queued for longer than its queue's wait allowance, or running for longer
    than the step's run deadline (hard limit + grace).

    A running step without started_at (should not happen) falls back to queued_at, so it
    can never escape the watchdog.
    """

    def ago(seconds):
        return func.now() - func.make_interval(0, 0, 0, 0, 0, 0, seconds)

    since = func.coalesce(Step.started_at, Step.queued_at)
    return ((Step.status == StepStatus.QUEUED.value) & (Step.queued_at < ago(_queue_wait_s()))) | (
        (Step.status == StepStatus.RUNNING.value) & (since < ago(_deadline_s()))
    )


def _lock_status(session: Session, step_id: uuid.UUID, *still) -> str | None:
    """Lock the step's parent, then the step if it still matches `still` (the planner's lock
    order); its status, or None when it no longer matches or the step or its parent is gone
    (nothing is locked then but the parent)."""
    ids = session.execute(
        select(Step.paper_id, Step.image_job_id).where(Step.id == step_id)
    ).one_or_none()
    if ids is None or parent_gone(lock_parent(session, ids.paper_id, ids.image_job_id)):
        return None
    return session.execute(
        select(Step.status).where(Step.id == step_id, *still).with_for_update()
    ).scalar_one_or_none()


def fail_if_stuck(session: Session, step_id: uuid.UUID, served: bool = True) -> bool:
    """In the current transaction, lock the step's parent then the step and, if the step is
    still stuck, fail it as worker_lost (retryable). A step stuck in `queued` never started,
    so its lost delivery is counted as an attempt here (the runtime counted a `running` one).
    `served=False` (its queue has no live consumer, or that is unknown): a step stuck in
    `queued` goes back to `pending` with no attempt and no error, because nothing could have
    run it; it is sent again (a fresh message: the old one expires, see celery_send) and runs
    when a worker comes back. A running step is always failed (a worker took it).
    A missing or deleted parent is left alone (no attempt added): fail_step would ignore it.
    Does not commit. Returns True if the step was failed or put back.
    """
    status = _lock_status(session, step_id, _stuck())
    if status is None:
        return False
    if status == StepStatus.QUEUED.value and not served:
        _put_back(session, step_id)  # locked and still queued: the guard holds
        return True
    if status == StepStatus.QUEUED.value:
        # Never started, so the runtime never counted it: a lost delivery is an attempt,
        # otherwise a broker that keeps losing it would re-queue it forever.
        session.execute(
            update(Step)
            .where(Step.id == step_id)
            .values(attempts=Step.attempts + 1)
            .execution_options(synchronize_session=False)
        )
    fail_step(session, step_id, ErrorClass.WORKER_LOST, "watchdog: no progress", retryable=True)
    return True


ANNOTATE_QUEUE = queue_for(StepKind.ANNOTATE, None)
NO_ANNOTATOR = "no annotation worker"


def _unserved_annotations(session: Session) -> list[uuid.UUID]:
    """Annotate steps still waiting (pending/queued) for longer than annotate_max_wait_s."""
    wait = get_settings().annotate_max_wait_s
    old = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, wait)
    return list(
        session.execute(
            select(Step.id).where(
                Step.kind == StepKind.ANNOTATE.value,
                Step.status.in_(WAITING_STEPS),
                Step.created_at < old,
            )
        ).scalars()
    )


def fail_unserved_annotation(session: Session, step_id: uuid.UUID) -> bool:
    """In the current transaction, lock the step's parent then the step and, if it is still
    waiting, fail it for good as engine_error: the model service is not running, so the paper
    goes back to done. Does not commit. True if failed."""
    if _lock_status(session, step_id, Step.status.in_(WAITING_STEPS)) is None:
        return False
    fail_step(session, step_id, ErrorClass.ENGINE_ERROR, NO_ANNOTATOR, retryable=False)
    return True


def watchdog_once(session: Session, live_queues: LiveQueues | None = None) -> int:
    """Fail (retry once, then final) steps stuck in queued/running. Returns the count.

    With `live_queues`, a step stuck in `queued` on a queue that no live worker consumes is put
    back to `pending` without costing an attempt (a dead queue must not turn its steps into
    final failures, one per wait allowance). Without it every queue counts as served.
    The scan takes no locks; each step is re-checked and failed in its own transaction.
    """
    rows = session.execute(select(Step.id, Step.status, Step.queue).where(_stuck())).all()
    waiting_annotations = _unserved_annotations(session) if live_queues is not None else []
    session.rollback()
    live: set[str] | frozenset[str] | None = None
    needs_live = any(r.status == StepStatus.QUEUED.value for r in rows) or waiting_annotations
    if live_queues is not None and needs_live:
        try:
            live = live_queues()
        except Exception:
            log.exception("watchdog: consumer check failed")
            live = None
    done = 0
    for step_id, status, queue in rows:
        served = live_queues is None or (live is not None and queue in live)
        try:
            if fail_if_stuck(session, step_id, served=served):
                session.commit()
                done += 1
                if served or status != StepStatus.QUEUED.value:
                    log.warning("watchdog: step %s stuck, marked worker_lost", step_id)
                else:
                    log.warning(
                        "watchdog: step %s queued on %s with no live consumer%s; back to "
                        "pending, no attempt counted",
                        step_id,
                        queue,
                        "" if live is not None else " (unknown)",
                    )
            else:
                session.rollback()
        except Exception:
            log.exception("watchdog: could not fail step %s", step_id)
            session.rollback()
    # Annotation depends on an optional service (llama-server): with no live q.llm consumer
    # (known, not just unknown) an old waiting annotate step fails, so its paper is done again.
    if live is not None and ANNOTATE_QUEUE not in live:
        for step_id in waiting_annotations:
            try:
                if fail_unserved_annotation(session, step_id):
                    session.commit()
                    done += 1
                    log.warning("watchdog: annotate step %s failed: no live q.llm consumer",
                                step_id)  # fmt: skip
                else:
                    session.rollback()
            except Exception:
                log.exception("watchdog: could not fail annotate step %s", step_id)
                session.rollback()
    return done
