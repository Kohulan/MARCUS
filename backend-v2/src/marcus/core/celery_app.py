"""Celery application shared by the dispatcher (sender) and every worker image.

One task carries pipeline work: `marcus.run_step(step_id)` (marcus.workers.runtime), sent by
the dispatcher to the step's queue with the kind's soft/hard time limits. Each worker image
consumes its own queue(s) and imports only its own handler modules, named on the worker
command line (`celery -A marcus.core.celery_app:celery_app worker --include <modules>`):
marcus.workers.cpu, .segment, .ocsr (each imports marcus.workers.runtime, which defines
run_step) or marcus.workers.tools. Nothing is included here, so the tools image needs no
database stack and no image loads another image's handlers. The result backend is used by
the synchronous tools queue only; run_step ignores results.

Beat: one scheduled task, the daily retention purge `marcus.retention.purge_expired`
(marcus.workers.retention, imported by marcus.workers.cpu) at 03:00 UTC on q.cpu. It is not a
pipeline step (no Step row). The scheduler runs inside worker-cpu (`celery worker -B`, schedule
file on its /tmp tmpfs); worker-cpu is the only service started with -B, and it runs one
replica, so exactly one beat exists. The schedule file is lost on a restart: a run missed while
worker-cpu was down at 03:00 is not caught up; the next day's run purges everything due.
"""

import logging
import os
import sys

from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init, setup_logging
from kombu import Queue

from marcus.core.logging import configure_logging
from marcus.core.queues import SLOTS, TOOLS_QUEUE
from marcus.core.settings import get_settings

_redis_url = get_settings().redis_url

RETENTION_QUEUE = "q.cpu"  # the purge runs on the cpu worker, beside check_pdf / render_page

celery_app = Celery(
    "marcus",
    broker=_redis_url,
    backend=_redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=600,  # tools results only; run_step stores none
    worker_prefetch_multiplier=1,  # one step at a time per worker process
    task_acks_late=True,  # ack after the step finished, so a lost worker means redelivery
    task_reject_on_worker_lost=True,  # requeue when the worker process dies
    broker_connection_retry_on_startup=True,
    # A pool process must report "up" within this time or the parent kills it. Its start may
    # warm up (tools: JVM ~3.5 s; worker-segment loads its model there and sets ~300 s).
    worker_proc_alive_timeout=float(os.environ.get("MARCUS_WORKER_PROC_ALIVE_TIMEOUT", "30")),
    task_queues=tuple(Queue(name, routing_key=name) for name in [*SLOTS, TOOLS_QUEUE]),
    task_default_queue="q.cpu",
    task_routes={
        "marcus.tools.*": {"queue": TOOLS_QUEUE},
        "marcus.retention.*": {"queue": RETENTION_QUEUE},
    },
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "retention-purge-daily": {
            "task": "marcus.retention.purge_expired",
            "schedule": crontab(hour=3, minute=0),
            "options": {"queue": RETENTION_QUEUE},
        },
    },
)


def live_queue_names(timeout: float) -> set[str]:
    """Names of the queues that at least one live worker consumes (a blocking broker broadcast;
    `timeout` bounds only the reply collection, callers bound the whole call)."""
    replies = celery_app.control.inspect(timeout=timeout).active_queues() or {}
    return {q["name"] for queues in replies.values() for q in (queues or []) if q.get("name")}


@beat_init.connect
def _log_beat_schedule(sender=None, **_) -> None:
    """Name every scheduled task when beat starts, so the logs show that (and where) beat runs."""
    for name, entry in sorted(celery_app.conf.beat_schedule.items()):
        logging.getLogger(__name__).info(
            "beat schedule: %s -> %s %s (UTC) %s",
            name, entry["task"], entry["schedule"], entry.get("options", {}),
        )


def _log_service() -> str:
    """Service name for log lines: MARCUS_SERVICE, else `worker-<name>` from `-n name@host`."""
    if os.environ.get("MARCUS_SERVICE"):
        return os.environ["MARCUS_SERVICE"]
    argv = sys.argv
    for i, arg in enumerate(argv[:-1]):
        if arg == "-n":
            return "worker-" + argv[i + 1].split("@")[0]
    return "worker"


@setup_logging.connect
def _json_logs(**_) -> None:
    """Connecting here stops Celery from installing its own log handlers (worker and beat)."""
    configure_logging(_log_service())
