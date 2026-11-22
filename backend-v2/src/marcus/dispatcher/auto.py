"""The dispatcher's auto pass: asks for the annotations and R-group rows that run by themselves
(marcus.core.auto), each in its own transaction, with the planner's own requests.

Only for a feature that is on (annotate_enabled, rgroup_enabled) and a queue a live worker
consumes (q.llm, q.rgroup). Otherwise nothing is asked: the candidates stay as they are, the
user keeps the manual action, and no step is made that nobody would run (the watchdog would
fail it later, and the user would see a failure for a run they never asked for). The consumer
check runs only when there is a candidate, and never holds up the dispatcher
(BackgroundLiveQueues). The steps go to their own queues, so the read's steps never wait for
them; they never touch the paper's status.
"""

import logging
import threading
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from marcus.core import auto
from marcus.core.enums import StepKind
from marcus.core.pipeline import (
    AnnotateNotAllowed,
    RgroupsNotAllowed,
    request_annotation,
    request_rgroups,
)
from marcus.core.queues import queue_for

log = logging.getLogger(__name__)

LiveQueues = Callable[[], "set[str] | frozenset[str] | None"]


class BackgroundLiveQueues:
    """The queues with a live consumer, without waiting: the last answer while it is younger
    than `ttl_s`, else the last answer (None at first: unknown) while a new broadcast runs in a
    daemon thread (one at a time). A broadcast that fails or overruns gives None."""

    def __init__(self, probe: LiveQueues, ttl_s: float) -> None:
        self._probe = probe
        self._ttl_s = ttl_s
        self._lock = threading.Lock()
        self._value: set[str] | frozenset[str] | None = None
        self._at = float("-inf")
        self._running = False

    def _refresh(self) -> None:
        try:
            value = self._probe()
        except Exception as exc:  # noqa: BLE001
            log.warning("auto: consumer check failed: %s", type(exc).__name__)
            value = None
        with self._lock:
            self._value, self._at, self._running = value, time.monotonic(), False

    def __call__(self) -> "set[str] | frozenset[str] | None":
        with self._lock:
            fresh = time.monotonic() - self._at < self._ttl_s
            if not fresh and not self._running:
                self._running = True
                threading.Thread(target=self._refresh, name="auto-inspect", daemon=True).start()
            return self._value


def _ask(session: Session, request, item, refused) -> bool:
    """One request in its own transaction; True when it made a step."""
    try:
        step = request(session, item)
        session.commit()
        return step is not None
    except (ValueError, *refused):  # deleted meanwhile, or no longer asked for
        session.rollback()
        return False
    except Exception:
        log.exception("auto: request for %s failed", item)
        session.rollback()
        return False


def _ids(session: Session, query) -> list:
    return [] if query is None else list(session.execute(query).scalars())


def auto_once(session: Session, live_queues: LiveQueues) -> int:
    """Ask for every candidate whose feature is on and whose queue is served. Returns the
    number of steps made."""
    annotate = _ids(session, auto.candidates_query(StepKind.ANNOTATE))
    rgroups = _ids(session, auto.candidates_query(StepKind.RGROUPS))
    session.rollback()  # end the read; each request below has its own transaction
    if not annotate and not rgroups:
        return 0
    live = live_queues()
    if live is None:
        return 0
    made = 0
    if annotate and queue_for(StepKind.ANNOTATE, None) in live:
        for paper_id in annotate:
            made += _ask(session, request_annotation, paper_id, (AnnotateNotAllowed,))
    if rgroups and queue_for(StepKind.RGROUPS, None) in live:
        for prediction_id in rgroups:
            made += _ask(session, request_rgroups, prediction_id, (RgroupsNotAllowed,))
    if made:
        log.info("auto: asked for %d annotation or R-group step(s)", made)
    return made
