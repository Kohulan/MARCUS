"""Container healthcheck: `python -m marcus.dispatcher.health` exits 0 if the heartbeat is fresh."""

import sys

import redis

from marcus.core import heartbeat
from marcus.core.settings import get_settings


def _client() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
    )


def main() -> int:
    try:
        return 0 if heartbeat.is_alive(heartbeat.age(_client())) else 1
    except Exception:  # noqa: BLE001  Redis down: the dispatcher cannot work either
        return 1


if __name__ == "__main__":
    sys.exit(main())
