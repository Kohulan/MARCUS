"""Dispatcher liveness: the dispatcher writes unix time to a Redis key every loop iteration.

Readers (GET /api/v2/ready, the dispatcher container's healthcheck, the metrics service) treat
a missing key, an unparseable value or a value older than MAX_AGE_S as "dispatcher down". The
key's TTL (TTL_S) removes it after a crash, so a dead dispatcher turns into "absent" too.
"""

import logging
import time

log = logging.getLogger(__name__)

KEY = "marcus:dispatcher:heartbeat"
TTL_S = 60
MAX_AGE_S = 30.0


def beat(client, now: float | None = None) -> None:
    """Write the heartbeat. Never raises: a Redis blip must not stop the dispatcher."""
    try:
        client.set(KEY, repr(time.time() if now is None else now), ex=TTL_S)
    except Exception as exc:  # noqa: BLE001
        log.warning("heartbeat write failed: %s", type(exc).__name__)


def parse_age(value, now: float | None = None) -> float | None:
    """Seconds since the heartbeat in `value` (bytes/str from Redis), None if absent/garbage."""
    if value is None:
        return None
    try:
        written = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (time.time() if now is None else now) - written)


def age(client, now: float | None = None) -> float | None:
    return parse_age(client.get(KEY), now)


def is_alive(age_s: float | None) -> bool:
    return age_s is not None and age_s <= MAX_AGE_S
