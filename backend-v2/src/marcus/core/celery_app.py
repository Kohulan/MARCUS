"""Celery application shared by the dispatcher (sender) and every worker image.

One task carries pipeline work: `marcus.run_step(step_id)` (marcus.workers.runtime), sent by
the dispatcher to the step's queue with the kind's soft/hard time limits. Each worker image
consumes its own queue(s) and imports only its own handler modules, named on the worker
command line (`celery -A marcus.core.celery_app:celery_app worker --include <modules>`):
marcus.workers.cpu, .segment, .ocsr (each imports marcus.workers.runtime, which defines
run_step) or marcus.workers.tools. Nothing is included here, so the tools image needs no
database stack and no image loads another image's handlers. The result backend is used by
the synchronous tools queue only; run_step ignores results.
"""

from celery import Celery
from kombu import Queue

from marcus.core.queues import SLOTS, TOOLS_QUEUE
from marcus.core.settings import get_settings

_redis_url = get_settings().redis_url

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
    worker_proc_alive_timeout=30,  # pool process start may warm up (tools: JVM ~3.5 s)
    task_queues=tuple(Queue(name, routing_key=name) for name in [*SLOTS, TOOLS_QUEUE]),
    task_default_queue="q.cpu",
    task_routes={"marcus.tools.*": {"queue": TOOLS_QUEUE}},
)
