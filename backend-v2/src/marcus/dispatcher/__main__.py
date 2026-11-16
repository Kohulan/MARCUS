"""Dispatcher process: `python -m marcus.dispatcher`.

LISTENs on `marcus_steps` (the steps trigger notifies on insert and status change), wakes
on a notify or every 1 s, fills free slots, and runs the watchdog every 10 s.
Stops cleanly on SIGTERM / SIGINT.
"""

import logging
import select
import signal
import threading
import time
import uuid

import psycopg
from sqlalchemy.engine import make_url

from marcus.core.db import sync_session
from marcus.core.enums import StepKind
from marcus.core.queues import TIME_LIMITS
from marcus.core.settings import get_settings
from marcus.dispatcher.pick import Send, dispatch_once, watchdog_once

log = logging.getLogger("marcus.dispatcher")

CHANNEL = "marcus_steps"
WAKE_S = 1.0
WATCHDOG_EVERY_S = 10.0


def psycopg_conninfo(database_url: str) -> str:
    """SQLAlchemy URL (any postgres driver) -> plain libpq URL for psycopg.connect."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def celery_send() -> Send:
    """The real `send`: one Celery task per step, carrying only the step id."""
    from marcus.core.celery_app import celery_app  # lazy: pick.py stays Celery-free

    def send(queue: str, step_id: uuid.UUID, kind: StepKind) -> None:
        soft, hard = TIME_LIMITS[kind]
        celery_app.send_task(
            "marcus.run_step",
            args=[str(step_id)],
            queue=queue,
            soft_time_limit=soft,
            time_limit=hard,
        )

    return send


def _wait_and_drain(conn: psycopg.Connection, timeout: float) -> None:
    """Block until a notify arrives or `timeout` passes, then drain all pending notifies."""
    select.select([conn.fileno()], [], [], timeout)
    for _ in conn.notifies(timeout=0):
        pass


def _run(stop: threading.Event, send: Send) -> None:
    conninfo = psycopg_conninfo(get_settings().database_url)
    last_watchdog = 0.0
    while not stop.is_set():
        try:
            with psycopg.connect(conninfo, autocommit=True) as conn:
                conn.execute(f"LISTEN {CHANNEL}")
                log.info("listening on %s", CHANNEL)
                while not stop.is_set():
                    _wait_and_drain(conn, WAKE_S)
                    with sync_session() as session:
                        n = dispatch_once(session, send)
                        if n:
                            log.info("dispatched %d step(s)", n)
                        if time.monotonic() - last_watchdog >= WATCHDOG_EVERY_S:
                            last_watchdog = time.monotonic()
                            w = watchdog_once(session)
                            if w:
                                log.warning("watchdog failed or re-queued %d step(s)", w)
        except Exception:
            log.exception("dispatcher loop error; reconnecting in %.0f s", WAKE_S)
            stop.wait(WAKE_S)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()

    def _stop(signum, frame):
        log.info("signal %d: stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    _run(stop, celery_send())
    log.info("stopped")


if __name__ == "__main__":
    main()
