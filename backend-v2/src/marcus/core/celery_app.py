"""Celery application shared by the dispatcher (sender) and every worker image.

One task carries pipeline work: `marcus.run_step(step_id)` (marcus.workers.runtime), sent by
the dispatcher to the step's queue with the kind's soft/hard time limits. Each worker image
consumes its own queue(s) and imports only its own handler modules. The result backend is
used by the synchronous tools queue only; run_step ignores results.
"""

from celery import Celery
from kombu import Queue

from marcus.core.queues import SLOTS
from marcus.core.settings import get_settings

TOOLS_QUEUE = "q.tools"

_redis_url = get_settings().redis_url

celery_app = Celery(
    "marcus",
    broker=_redis_url,
    backend=_redis_url,
    include=["marcus.workers.runtime", "marcus.workers.tools"],
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
    task_queues=tuple(Queue(name, routing_key=name) for name in [*SLOTS, TOOLS_QUEUE]),
    task_default_queue="q.cpu",
    task_routes={"marcus.tools.*": {"queue": TOOLS_QUEUE}},
)
