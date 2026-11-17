"""Prometheus metrics, served on the internal port 9100 by their own small process.

`python -m marcus.api.metrics` (compose service `metrics`, same image as the api, not
published, never behind nginx) runs a tiny ASGI app with `GET /metrics` and `GET /health`.
The public API has no metrics route (`/api/v2/metrics` is a 404).

The collector reads Postgres on a scrape: ONE read-only transaction with a 2 s statement
timeout, all queries inside it. The result is cached for CACHE_S seconds, so a fast scraper (or
several) cannot load the database. If the read fails (down, or a query over the timeout) the
DB series are left out and `marcus_scrape_db_ok` is 0; the Redis/disk gauges still answer.

Series (histograms and failure counts come from the `steps` table; histograms cover the last
hour; every known queue / error class has a series, 0 when idle):

    marcus_queue_pending{queue}            steps pending or queued (waiting for a worker)
    marcus_queue_running{queue}            steps running
    marcus_step_seconds{kind,engine}       finished_at - started_at of steps done in the last hour
    marcus_wait_seconds{queue}             queued_at - created_at of steps queued in the last hour
    marcus_first_smiles_seconds            first prediction - paper upload, papers of the last hour
    marcus_step_failures_total{error_class}  failed steps still stored (resets when retention
                                           purges old steps: use increase(), not the raw value)
    marcus_disk_free_bytes{path="/data"}
    marcus_dispatcher_heartbeat_age_seconds  +Inf when the heartbeat key is absent
    marcus_scrape_db_ok                    1 if the database read worked
"""

import logging
import math
import shutil
import threading
import time

import anyio
import redis
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
)
from sqlalchemy import create_engine, func, literal_column, select, text
from sqlalchemy.engine import Connection
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import Receive, Scope, Send

from marcus.core import heartbeat
from marcus.core.db import sync_db_url
from marcus.core.enums import ErrorClass, StepStatus
from marcus.core.models import Paper, Prediction, Segment, Step
from marcus.core.queues import SLOTS, TOOLS_QUEUE
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

PORT = 9100
CACHE_S = 10.0
STATEMENT_TIMEOUT_MS = 2000
WINDOW = "1 hour"
BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
WAITING = (StepStatus.PENDING.value, StepStatus.QUEUED.value)
DISK_PATH_LABEL = "/data"


def _monotonic() -> float:
    return time.monotonic()


def _histogram_columns(seconds):
    """count(*) FILTER (seconds <= b) per bucket, then count and sum."""
    cols = [func.count().filter(seconds <= b) for b in BUCKETS]
    return [*cols, func.count(), func.coalesce(func.sum(seconds), 0.0)]


def _add_histogram(family: HistogramMetricFamily, labels: list[str], row) -> None:
    *counts, total, summed = row
    buckets = [(repr(b), float(c)) for b, c in zip(BUCKETS, counts, strict=True)]
    buckets.append(("+Inf", float(total)))
    family.add_metric(labels, buckets, float(summed))


class MarcusCollector:
    """A prometheus_client custom collector (register it on a registry)."""

    def __init__(self, cache_s: float = CACHE_S) -> None:
        self.cache_s = cache_s
        self._lock = threading.Lock()
        self._at: float | None = None
        self._families: list = []
        self._engine = None

    # -- sources ------------------------------------------------------------------------------

    def _db(self):
        if self._engine is None:
            self._engine = create_engine(
                sync_db_url(get_settings().database_url),
                pool_size=1,
                max_overflow=0,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 3},
            )
        return self._engine

    def _heartbeat_age(self) -> float:
        try:
            client = redis.Redis.from_url(
                get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1
            )
            try:
                age = heartbeat.age(client)
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("metrics: redis read failed: %s", type(exc).__name__)
            return math.inf
        return math.inf if age is None else age

    def _snapshot(self, conn: Connection) -> list:
        """All database series, read inside the caller's one read-only transaction."""
        fams = []
        pending = GaugeMetricFamily("marcus_queue_pending", "Steps waiting.", labels=["queue"])
        running = GaugeMetricFamily("marcus_queue_running", "Steps running.", labels=["queue"])
        counts = {
            (q, status): n
            for q, status, n in conn.execute(
                select(Step.queue, Step.status, func.count())
                .where(Step.status.in_([*WAITING, StepStatus.RUNNING.value]))
                .group_by(Step.queue, Step.status)
            )
        }
        queues = sorted({*SLOTS, TOOLS_QUEUE} | {q for q, _ in counts})
        for q in queues:
            pending.add_metric([q], sum(counts.get((q, s), 0) for s in WAITING))
            running.add_metric([q], counts.get((q, StepStatus.RUNNING.value), 0))
        fams += [pending, running]

        since = text(f"now() - interval '{WINDOW}'")
        run_s = func.extract("epoch", Step.finished_at - Step.started_at)
        step_h = HistogramMetricFamily(
            "marcus_step_seconds", "Step run time, last hour.", labels=["kind", "engine"]
        )
        engine_col = literal_column("coalesce(steps.engine, '')").label("engine")
        for kind, engine, *rest in conn.execute(
            select(Step.kind, engine_col, *_histogram_columns(run_s))
            .where(
                Step.status == StepStatus.DONE.value,
                Step.started_at.is_not(None),
                Step.finished_at >= since,
            )
            .group_by(Step.kind, literal_column("coalesce(steps.engine, '')"))
            .order_by(Step.kind)
        ):
            _add_histogram(step_h, [kind, engine], rest)
        fams.append(step_h)

        wait_s = func.extract("epoch", Step.queued_at - Step.created_at)
        wait_h = HistogramMetricFamily(
            "marcus_wait_seconds", "Queue wait (queued_at - created_at), last hour.",
            labels=["queue"],
        )  # fmt: skip
        for queue, *rest in conn.execute(
            select(Step.queue, *_histogram_columns(wait_s))
            .where(Step.queued_at.is_not(None), Step.queued_at >= since)
            .group_by(Step.queue)
            .order_by(Step.queue)
        ):
            _add_histogram(wait_h, [queue], rest)
        fams.append(wait_h)

        first = (
            select(
                func.extract("epoch", func.min(Prediction.created_at) - Paper.created_at).label(
                    "secs"
                )
            )
            .select_from(Prediction)
            .join(Segment, Segment.id == Prediction.segment_id)
            .join(Paper, Paper.id == Segment.paper_id)
            .where(Paper.created_at >= since)
            .group_by(Paper.id, Paper.created_at)
            .subquery()
        )
        secs = literal_column("secs")
        first_row = conn.execute(select(*_histogram_columns(secs)).select_from(first)).one()
        first_h = HistogramMetricFamily(
            "marcus_first_smiles_seconds", "Upload to first SMILES per paper, last hour."
        )
        _add_histogram(first_h, [], first_row)
        fams.append(first_h)

        failures = CounterMetricFamily(
            "marcus_step_failures", "Failed steps by error class.", labels=["error_class"]
        )
        by_class = dict(
            conn.execute(
                select(Step.error_class, func.count())
                .where(Step.status == StepStatus.FAILED.value)
                .group_by(Step.error_class)
            ).all()
        )
        for cls in [e.value for e in ErrorClass]:
            failures.add_metric([cls], by_class.pop(cls, 0))
        for cls, n in by_class.items():  # failed without a class (should not happen)
            failures.add_metric([cls or "unknown"], n)
        fams.append(failures)
        return fams

    def _read_db(self) -> list | None:
        try:
            with self._db().connect() as conn:
                # One transaction, read-only, bounded: nothing here can write or run long.
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
                fams = self._snapshot(conn)
                conn.rollback()
                return fams
        except Exception as exc:  # noqa: BLE001
            log.warning("metrics: database read failed: %s", type(exc).__name__)
            return None

    # -- collector protocol ---------------------------------------------------------------------

    def _build(self) -> list:
        db = self._read_db()
        ok = GaugeMetricFamily("marcus_scrape_db_ok", "1 if the database read worked.")
        ok.add_metric([], 1.0 if db is not None else 0.0)
        disk = GaugeMetricFamily(
            "marcus_disk_free_bytes", "Free bytes on the data volume.", labels=["path"]
        )
        try:
            disk.add_metric([DISK_PATH_LABEL], float(shutil.disk_usage(get_settings().data_root).free))
        except OSError as exc:
            log.warning("metrics: disk_usage failed: %s", type(exc).__name__)
        beat = GaugeMetricFamily(
            "marcus_dispatcher_heartbeat_age_seconds",
            "Seconds since the dispatcher's last heartbeat (+Inf when absent).",
        )
        beat.add_metric([], self._heartbeat_age())
        return [*(db or []), disk, beat, ok]

    def collect(self):
        with self._lock:  # one scrape reads the DB; concurrent ones wait for its result
            if self._at is None or _monotonic() - self._at >= self.cache_s:
                self._families = self._build()
                self._at = _monotonic()
            return list(self._families)


# --- the internal HTTP app -----------------------------------------------------------------------


def build_app(collector: MarcusCollector | None = None):
    registry = CollectorRegistry()
    registry.register(collector or MarcusCollector())

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return  # lifespan is handled by uvicorn when the app ignores it
        path, method = scope["path"], scope["method"]
        response: Response
        if path == "/metrics":
            if method != "GET":
                response = PlainTextResponse("method not allowed", status_code=405)
            else:
                body = await anyio.to_thread.run_sync(generate_latest, registry)
                response = Response(body, media_type=CONTENT_TYPE_LATEST)
        elif path == "/health" and method == "GET":
            response = JSONResponse({"status": "ok"})
        else:
            response = PlainTextResponse("not found", status_code=404)
        await response(scope, receive, send)

    return app


def main() -> None:
    import uvicorn

    from marcus.core.logging import configure_logging

    configure_logging("metrics")
    uvicorn.run(build_app(), host="0.0.0.0", port=PORT, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
