"""Progress events on Redis pub/sub.

Workers publish one JSON message per step state change, after the change is committed:
paper steps on `marcus:paper:{paper_id}`, image-job steps on `marcus:image:{job_id}`.
Events are a hint for live UIs; the database stays the source of truth. Publishing never
raises (except a Celery soft time limit, which is re-raised): a Redis outage is logged
and the step carries on.
"""

import json
import logging
import uuid
from functools import lru_cache

import redis
from celery.exceptions import SoftTimeLimitExceeded
from redis.backoff import NoBackoff
from redis.retry import Retry

from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

PAPER_CHANNEL = "marcus:paper:{}"
IMAGE_CHANNEL = "marcus:image:{}"


def paper_channel(paper_id: uuid.UUID) -> str:
    return PAPER_CHANNEL.format(paper_id)


def image_channel(job_id: uuid.UUID) -> str:
    return IMAGE_CHANNEL.format(job_id)


def make_client(url: str) -> redis.Redis:
    """Short timeouts and one immediate retry: a Redis outage must not eat a step's time."""
    return redis.Redis.from_url(
        url, socket_connect_timeout=2, socket_timeout=2, retry=Retry(NoBackoff(), 1)
    )


@lru_cache
def get_redis() -> redis.Redis:
    """Process-wide client, created on first use."""
    return make_client(get_settings().redis_url)


def _publish(channel: str, event: dict) -> None:
    try:
        get_redis().publish(channel, json.dumps(event, default=str))
    except SoftTimeLimitExceeded:
        raise  # the step's time is up; the runtime must see it
    except Exception:
        log.warning("could not publish event on %s", channel, exc_info=True)


def publish_event(paper_id: uuid.UUID, event: dict) -> None:
    _publish(paper_channel(paper_id), event)


def publish_image_event(job_id: uuid.UUID, event: dict) -> None:
    _publish(image_channel(job_id), event)
