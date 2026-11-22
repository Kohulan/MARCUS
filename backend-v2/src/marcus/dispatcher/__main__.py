"""Dispatcher process: `python -m marcus.dispatcher`.

LISTENs on `marcus_steps` (the steps trigger notifies on insert and status change), wakes
on a notify or every 1 s, fills free slots, and runs the watchdog every 10 s. The watchdog asks
which queues have a live consumer (a Celery broadcast, bounded by INSPECT_BUDGET_S) only when a
step is stuck in `queued`; a step on a queue nobody consumes goes back to pending without
costing an attempt. Every 3 s the auto pass asks for the annotations and R-group rows that run
by themselves (marcus.dispatcher.auto); its consumer check runs in the background.
Stops cleanly on SIGTERM / SIGINT.

Every loop iteration writes the Redis heartbeat (marcus.core.heartbeat), read by /ready and the
container healthcheck (`python -m marcus.dispatcher.health`).

Exactly one dispatcher replica must run: slot accounting (free_slots, then pick) is not
atomic across processes, so two dispatchers could overfill a queue.
"""

import logging
import select
import signal
import threading
import time
import uuid

import psycopg
import redis
from sqlalchemy.engine import make_url

from marcus.core import heartbeat
from marcus.core.db import sync_session
from marcus.core.enums import StepKind
from marcus.core.logging import configure_logging
from marcus.core.queues import QUEUE_WAIT_S, time_limits_for
from marcus.core.settings import get_settings
from marcus.dispatcher.auto import BackgroundLiveQueues, auto_once
from marcus.dispatcher.pick import LiveQueues, Send, dispatch_once, watchdog_once

log = logging.getLogger("marcus.dispatcher")

CHANNEL = "marcus_steps"
WAKE_S = 1.0
WATCHDOG_EVERY_S = 10.0
INSPECT_TIMEOUT_S = 1.0  # reply collection inside the consumer broadcast
INSPECT_BUDGET_S = 2.0  # the watchdog's whole wait for it
AUTO_EVERY_S = 3.0
AUTO_LIVE_TTL_S = 30.0  # the auto pass's consumer answer is kept this long


def psycopg_conninfo(database_url: str) -> str:
    """SQLAlchemy URL (any postgres driver) -> plain libpq URL for psycopg.connect."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def celery_send() -> Send:
    """The real `send`: one Celery task per step, carrying the step id and attempt token.

    The message expires after its queue's wait allowance (QUEUE_WAIT_S): by then the watchdog
    has failed or re-queued the step and sent a fresh message, so a worker that comes back
    after an outage discards the old ones instead of claiming them first."""
    from marcus.core.celery_app import celery_app  # lazy: pick.py stays Celery-free

    def send(
        queue: str,
        step_id: uuid.UUID,
        kind: StepKind,
        attempts: int,
        pages: int | None = None,
        engine: str | None = None,
    ) -> None:
        soft, hard = time_limits_for(kind, pages, engine)
        celery_app.send_task(
            "marcus.run_step",
            args=[str(step_id), attempts],
            queue=queue,
            soft_time_limit=soft,
            time_limit=hard,
            expires=QUEUE_WAIT_S[queue],
        )

    return send


def live_queues_probe() -> LiveQueues:
    """The watchdog's consumer check (core.celery_app.LiveQueuesProbe), waited for at most
    INSPECT_BUDGET_S; None (unknown) when the broadcast overran or failed."""
    from marcus.core.celery_app import LiveQueuesProbe  # lazy: pick.py stays Celery-free

    probe = LiveQueuesProbe(INSPECT_TIMEOUT_S, "watchdog")
    return lambda: probe.get(INSPECT_BUDGET_S)


def _wait_and_drain(conn: psycopg.Connection, timeout: float) -> None:
    """Block until a notify arrives or `timeout` passes, then drain all pending notifies."""
    select.select([conn.fileno()], [], [], timeout)
    for _ in conn.notifies(timeout=0):
        pass


def _dispatch(send: Send) -> None:
    try:
        with sync_session() as session:
            n = dispatch_once(session, send)
        if n:
            log.info("dispatched %d step(s)", n)
    except Exception:
        log.exception("dispatch error")


def _watchdog(live_queues: LiveQueues | None = None) -> None:
    """Own session and error handling: a failing dispatch can never starve the watchdog."""
    try:
        with sync_session() as session:
            w = watchdog_once(session, live_queues=live_queues)
        if w:
            log.warning("watchdog failed or re-queued %d step(s)", w)
    except Exception:
        log.exception("watchdog error")


def _auto(live_queues: LiveQueues) -> None:
    """Own session and error handling: a failing auto pass never stops the dispatcher."""
    try:
        with sync_session() as session:
            auto_once(session, live_queues)
    except Exception:
        log.exception("auto pass error")


def _run(
    stop: threading.Event,
    send: Send,
    beat_client=None,
    live_queues: LiveQueues | None = None,
    auto_live: LiveQueues | None = None,
) -> None:
    conninfo = psycopg_conninfo(get_settings().database_url)
    last_watchdog = 0.0
    last_auto = 0.0
    while not stop.is_set():
        try:
            with psycopg.connect(conninfo, autocommit=True) as conn:
                conn.execute(f"LISTEN {CHANNEL}")
                log.info("listening on %s", CHANNEL)
                while not stop.is_set():
                    _wait_and_drain(conn, WAKE_S)
                    _dispatch(send)
                    if beat_client is not None:
                        heartbeat.beat(beat_client)
                    if time.monotonic() - last_watchdog >= WATCHDOG_EVERY_S:
                        last_watchdog = time.monotonic()
                        _watchdog(live_queues)
                    if auto_live is not None and time.monotonic() - last_auto >= AUTO_EVERY_S:
                        last_auto = time.monotonic()
                        _auto(auto_live)
        except Exception:
            log.exception("dispatcher loop error; reconnecting in %.0f s", WAKE_S)
            stop.wait(WAKE_S)


def main() -> None:
    configure_logging("dispatcher")
    stop = threading.Event()

    def _stop(signum, frame):
        log.info("signal %d: stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    beat_client = redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
    )
    # two probes: a broadcast one of them still waits for never answers "unknown" to the other
    auto_live = BackgroundLiveQueues(live_queues_probe(), AUTO_LIVE_TTL_S)
    _run(stop, celery_send(), beat_client, live_queues_probe(), auto_live)
    log.info("stopped")


if __name__ == "__main__":
    main()
