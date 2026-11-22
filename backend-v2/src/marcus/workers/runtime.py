"""Worker runtime: the `marcus.run_step` Celery task, the handler registry and error mapping.

One delivery of `run_step(step_id, sent_attempts)` goes through three short transactions,
never one held open across the handler's (possibly long) ML work. `sent_attempts` is the
step's `attempts` when the dispatcher queued it: the token that ties a message to one
attempt, so a stale duplicate message can never touch a newer attempt.

1. Claim. One conditional UPDATE moves the step `queued -> running` (only if `attempts`
   still equals the token), adds an attempt and commits. A step found `running` with
   `attempts == sent_attempts + 1` was claimed by this very message, so this is a
   redelivery after a lost worker: it counts as a new attempt (guarded on the attempts
   value seen), or fails as `worker_lost` once MAX_ATTEMPTS is reached. Every other case
   (another attempt's message, or pending, done, failed, cancelled) is acked and dropped.
2. Handler. `handler(step, session)` runs with no transaction open. `step` is a detached
   Step (plain column reads only, no lazy loads). `session` is a fresh Session for short
   reads: a handler that reads must end its read (`session.rollback()`) before long work,
   must never write or commit (its result is the returned dict), and the runtime closes
   the session afterwards. One exception: the ocsr handler stores its cache row
   (`ocsr_cache`, no step or paper state) in its own short transaction.
3. Finish. Under the planner's lock order (parent row, then step row) the runtime checks
   that the step is still `running` with the attempt number this delivery set (attempt
   fence). If not, a newer delivery or the watchdog owns the step and this result or
   failure is dropped. Otherwise complete_step / fail_step runs and commits.

After each commit one event is published (marcus.core.events); publishing never raises.

Error mapping: SoftTimeLimitExceeded and StepTimeout -> timeout (retryable); WorkerLost ->
worker_lost (retryable); BadInput -> bad_input (final);
BadResult from complete_step -> engine_error (final); anything else -> engine_error
(retryable). The message is stored on the step (max 2000 chars) and never sent to clients.
"""

import logging
import os
import signal
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import task_postrun
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from marcus.core import events
from marcus.core.celery_app import celery_app
from marcus.core.db import sync_session
from marcus.core.enums import ErrorClass, StepKind, StepStatus
from marcus.core.logging import log_context
from marcus.core.models import Step
from marcus.core.pipeline import MAX_ATTEMPTS, BadResult, complete_step, fail_step, lock_parent

log = logging.getLogger(__name__)

MAX_ERROR_CHARS = 2000

Handler = Callable[[Step, Session], dict]

HANDLERS: dict[StepKind, Handler] = {}


class BadInput(Exception):
    """The step's input can never work (e.g. not a PDF). Raised by handlers; not retried."""


class StepTimeout(Exception):
    """The step's work ran past its own wall-time limit (e.g. a pdfsafe child was killed).
    Recorded as `timeout` and retried once, like Celery's soft time limit."""


class StorageFull(Exception):
    """The data volume is below its free-space floor; the step wrote nothing. Recorded as
    `engine_error` and retried once (not final bad_input: the input is not at fault)."""


class WorkerLost(Exception):
    """The process doing the step's work was killed from outside (e.g. the OOM killer took a
    pdfsafe child). Recorded as `worker_lost` and retried once."""


class _NoHandler(Exception):
    """This worker image has no handler for the step's kind (final engine_error)."""


def register(kind: StepKind, handler: Handler) -> None:
    """Register the handler for a step kind (each worker image imports only its own)."""
    HANDLERS[StepKind(kind)] = handler


@dataclass(frozen=True)
class Claim:
    """What one delivery owns: the step at the attempt number this delivery set."""

    step_id: uuid.UUID
    attempts: int
    kind: str
    paper_id: uuid.UUID | None
    image_job_id: uuid.UUID | None
    page: int | None
    segment_id: uuid.UUID | None

    @classmethod
    def from_row(cls, step_id: uuid.UUID, row) -> "Claim":
        """From a row with the _RETURNING columns."""
        return cls(step_id, row.attempts, row.kind, row.paper_id, row.image_job_id, row.page,
                   row.segment_id)  # fmt: skip


_RETURNING = (
    Step.attempts, Step.kind, Step.paper_id, Step.image_job_id, Step.page, Step.segment_id,
)  # fmt: skip


def _publish(claim: Claim, status: str) -> None:
    event = {
        "type": "step",
        "step_id": str(claim.step_id),
        "kind": claim.kind,
        "status": status,
        "page": claim.page,
        "segment_id": str(claim.segment_id) if claim.segment_id else None,
    }
    if claim.paper_id is not None:
        events.publish_event(claim.paper_id, event)
    else:
        events.publish_image_event(claim.image_job_id, event)


def _message(exc: BaseException) -> str:
    return (str(exc) or type(exc).__name__)[:MAX_ERROR_CHARS]


# --- 1. claim ------------------------------------------------------------------------------


def _start(session: Session, step_id: uuid.UUID, worker: str, *guard) -> Claim | None:
    """The guarded claim UPDATE: running, attempts + 1, started now. None if no row matched."""
    row = session.execute(
        update(Step)
        .where(Step.id == step_id, *guard)
        .values(
            status=StepStatus.RUNNING.value,
            attempts=Step.attempts + 1,
            started_at=func.now(),
            worker_name=worker,
        )
        .returning(*_RETURNING)
        .execution_options(synchronize_session=False)
    ).one_or_none()
    return None if row is None else Claim.from_row(step_id, row)


def claim(
    step_id: uuid.UUID, sent_attempts: int, worker: str, queue: str | None = None
) -> Claim | None:
    """Claim the step for this message and commit. None means: ack and do nothing.

    `queue`: the queue the message came from, when known. A message from another queue than the
    step's is stale (the step moved, e.g. rgroups from q.llm to q.rgroup in migration 0013, and
    was sent again with the same attempt token): never claimed.

    Does not publish; the caller publishes the `running` event.
    """
    with sync_session() as session:
        queued = (Step.status == StepStatus.QUEUED.value, Step.attempts == sent_attempts)
        if queue is not None:
            queued = (*queued, Step.queue == queue)
        mine = _start(session, step_id, worker, *queued)
        if mine is None:
            row = session.execute(
                select(*_RETURNING, Step.status, Step.queue).where(Step.id == step_id)
            ).one_or_none()
            ours = (
                row is not None
                and row.status == StepStatus.RUNNING.value
                and row.attempts == sent_attempts + 1
                and (queue is None or row.queue == queue)
            )
            if not ours:
                session.rollback()
                log.info("step %s: message for attempt token %d is stale (%s); dropped",
                         step_id, sent_attempts, row.status if row else "unknown")  # fmt: skip
                return None
            seen = Claim.from_row(step_id, row)
            if row.attempts >= MAX_ATTEMPTS:
                session.rollback()
                log.warning("step %s redelivered after %d attempts: worker_lost", step_id,
                            row.attempts)  # fmt: skip
                _fail(seen, ErrorClass.WORKER_LOST, "worker lost", retryable=False)
                return None
            # Redelivery after a lost worker: count it as a new attempt and run it.
            guard = (Step.status == StepStatus.RUNNING.value, Step.attempts == row.attempts)
            mine = _start(session, step_id, worker, *guard)
            if mine is None:
                session.rollback()
                return None  # someone else moved it on meanwhile
        session.commit()
    return mine


# --- 3. finish (fenced) --------------------------------------------------------------------


def _still_mine(session: Session, mine: Claim) -> bool:
    """Lock parent then step (planner order); True if this delivery still owns the step."""
    lock_parent(session, mine.paper_id, mine.image_job_id)
    row = session.execute(
        select(Step.status, Step.attempts).where(Step.id == mine.step_id).with_for_update()
    ).one_or_none()
    ok = row is not None and row.status == StepStatus.RUNNING.value
    return ok and row.attempts == mine.attempts


def _complete(mine: Claim, result: dict) -> None:
    """complete_step under the attempt fence. Raises on any error (closing the session rolls
    back, here and in _fail)."""
    with sync_session() as session:
        if not _still_mine(session, mine):
            log.warning("step %s attempt %d is stale; result dropped", mine.step_id,
                        mine.attempts)  # fmt: skip
            return
        complete_step(session, mine.step_id, result)
        session.commit()
    _publish(mine, StepStatus.DONE.value)


def _fail(mine: Claim, error_class: ErrorClass, error: str, retryable: bool) -> None:
    """fail_step under the attempt fence, then publish the step's new status."""
    with sync_session() as session:
        if not _still_mine(session, mine):
            log.warning("step %s attempt %d is stale; failure dropped", mine.step_id,
                        mine.attempts)  # fmt: skip
            return
        fail_step(session, mine.step_id, error_class, error, retryable)
        status = session.get(Step, mine.step_id).status
        session.commit()
    _publish(mine, status)


def _classify(exc: BaseException) -> tuple[ErrorClass, bool]:
    if isinstance(exc, SoftTimeLimitExceeded | StepTimeout):
        return ErrorClass.TIMEOUT, True
    if isinstance(exc, WorkerLost):
        return ErrorClass.WORKER_LOST, True
    if isinstance(exc, BadInput):
        return ErrorClass.BAD_INPUT, False
    if isinstance(exc, BadResult | _NoHandler):
        return ErrorClass.ENGINE_ERROR, False
    return ErrorClass.ENGINE_ERROR, True


# --- 2. handler, and the whole delivery ----------------------------------------------------


def _load_view(step_id: uuid.UUID) -> Step:
    """The step as a detached object; the read transaction ends before the handler runs."""
    with sync_session() as session:
        step = session.get(Step, step_id)
        session.expunge(step)
        session.rollback()
    return step


def _call(handler: Handler, step_id: uuid.UUID) -> dict:
    view = _load_view(step_id)
    with sync_session() as reads:
        try:
            return handler(view, reads)
        finally:
            reads.rollback()


def execute(step_id: uuid.UUID, sent_attempts: int, worker: str, queue: str | None = None) -> None:
    """One delivery of a step: claim, run the handler, then complete or fail (fenced).

    Everything after the claim, including the `running` event (publish re-raises a soft
    time limit), is inside the error mapping, so the claimed attempt is always settled.
    """
    mine = claim(step_id, sent_attempts, worker, queue)
    if mine is None:
        return
    with log_context(paper_id=mine.paper_id):
        _run_claimed(mine, step_id)


def _run_claimed(mine: Claim, step_id: uuid.UUID) -> None:
    try:
        _publish(mine, StepStatus.RUNNING.value)
        handler = HANDLERS.get(StepKind(mine.kind))
        if handler is None:
            raise _NoHandler(f"no handler for {mine.kind}")
        result = _call(handler, step_id)
        _complete(mine, result)
    except Exception as exc:
        error_class, retryable = _classify(exc)
        log.exception("step %s (%s) attempt %d failed: %s", step_id, mine.kind, mine.attempts,
                      error_class.value)  # fmt: skip
        _fail(mine, error_class, _message(exc), retryable)


def _worker_name() -> str:
    hostname = getattr(run_step.request, "hostname", None)
    return hostname or f"{socket.gethostname()}:{os.getpid()}"


@celery_app.task(name="marcus.run_step", ignore_result=True)
def run_step(step_id: str, sent_attempts: int) -> None:
    """Celery entry point. Always acks: state lives in the database, not in the task result.

    `sent_attempts` is the step's attempts value when it was queued (see module docstring).
    A database error that leaves the step `running` is logged; the watchdog rescues it.
    """
    try:
        sid = uuid.UUID(step_id)
        token = int(sent_attempts)
    except (TypeError, ValueError):
        log.error("run_step: malformed message %r, %r", step_id, sent_attempts)
        return
    queue = (getattr(run_step.request, "delivery_info", None) or {}).get("routing_key")
    try:
        with log_context(step_id=sid):
            execute(sid, token, _worker_name(), queue)
    except Exception:
        log.exception("run_step: step %s could not be recorded; left to the watchdog", sid)


# --- model preload helpers (worker_process_init hooks of the model workers) ----------------


def in_pool_process() -> bool:
    """True in a Celery prefork pool process. worker_process_init can also be sent elsewhere
    (tests send it to exercise other workers' hooks); there the parent is not a Celery worker."""
    from billiard.process import current_process

    return current_process()._name != "MainProcess"


def abort_worker() -> None:
    """Stop the whole worker with a non-zero exit: SIGQUIT to the parent (Celery cold
    shutdown, exit code 1), then leave this pool process. Compose restarts the container and
    /ready reports the queue as unserved; a half-ready worker that keeps taking steps it
    cannot run must not exist."""
    os.kill(os.getppid(), signal.SIGQUIT)
    os._exit(1)


def preload_on_worker_init(load: Callable[[], object], what: str) -> None:
    """The body of a model worker's worker_process_init hook: in a Celery pool process only,
    run `load` (so the first step does not pay the model load against its time limit); any
    failure, SystemExit from a library included, stops the whole worker (abort_worker)."""
    if not in_pool_process():
        return
    try:
        load()
    except (Exception, SystemExit, KeyboardInterrupt):  # any failure, incl. SystemExit from a library
        log.exception("%s failed to load; stopping the worker", what)
        abort_worker()


# --- recycling a pool process after a failure that may leave memory behind ---------------

_recycle_reason: str | None = None


def request_recycle(reason: str) -> None:
    """Replace this pool process once the current task has finished (e.g. a model load was
    interrupted by the soft time limit: TensorFlow keeps the half-built graph's memory)."""
    global _recycle_reason
    _recycle_reason = reason
    log.warning("pool process %d will be replaced after this task: %s", os.getpid(), reason)


@task_postrun.connect
def recycle_if_requested(**_) -> None:
    """After the task returned (run_step has recorded the step's result or failure in the
    database), leave the pool process if a recycle was requested; billiard starts a fresh one
    (worker_process_init preloads again).

    The parent sees the child exit before the task's result and, with acks_late +
    reject_on_worker_lost, requeues the message once. That redelivery carries a spent attempt
    token, so the runtime's attempt fence drops it (claim() returns None)."""
    if _recycle_reason is None or not in_pool_process():
        return
    log.warning("recycling pool process %d: %s", os.getpid(), _recycle_reason)
    os._exit(0)
