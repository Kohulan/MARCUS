"""Retention: the daily purge (RETENTION_DAYS = 30).

`purge_expired(session, now)` removes, in this order:

1. papers with `expires_at < now`: a paper with an active step is first cancelled through
   `pipeline.cancel_paper` (its queued/running steps become `cancelled`, so no step of a gone
   paper keeps holding a queue slot, and the status change NOTIFYs the dispatcher), then the
   rows are deleted (segments, steps, predictions, curation and the annotation cascade) and the paper
   directory is removed;
2. image jobs with `expires_at < now`: active steps cancelled, row deleted (steps and the
   prediction cascade), image file removed;
3. `seg_cache` rows older than `retention_days`, and rows of another segmenter version than
   the configured `MARCUS_SEG_VERSION` (skipped when that is unset: an unconfigured worker
   must not wipe the cache);
4. `ocsr_cache` rows older than `retention_days`, and rows of an engine whose current version
   is known in this process but differs (`current_ocsr_versions`). The cpu worker has no OCSR
   engine package installed, so there this part is age-based only;
5. orphans: entries under `data_root/papers` and `data_root/images` with a server-made name
   (a uuid) whose paper / image job has no row, or a `deleted` one, and whose mtime is older
   than one day (younger ones may belong to an upload that is still committing). This also
   retries files that `cancel_paper` or step 1/2 could not remove;
6. owner IPs: the address recorded when a browser first got its key (`owners.created_ip`) is
   set to NULL `owner_ip_retention_days` (default 30) after it was recorded (`created_at`).
   The owner row stays; the per-address new-key limit only counts owners of the last hour.
   Backstop for the address kept on active work (`papers.started_ip`,
   `image_jobs.started_ip`, cleared by the planner when the work ends): set to NULL on work
   that is no longer active, or whose address was set (`started_ip_at`: creation or reopen)
   more than that many days ago;
7. depictions (`data_root/depictions/<owner id>/<xx>/`, the API's stored structure drawings
   and `.nodraw` markers): files older than DEPICTION_MAX_DAYS (mtime), then, while the
   directory holds more than DEPICTIONS_MAX_BYTES, the oldest files first. A removed drawing
   is drawn again on its next request. Directories empty for over a day are removed.

Rows go in batches of `batch_size`, one transaction each, locked with SKIP LOCKED (a row a
worker holds right now is left for the next run), so a run never holds a long transaction.
Unlike the planner functions this one commits: the caller passes a fresh session. Files are
removed after the batch committed; a file error is logged and counted, never raised.

The Celery task `marcus.retention.purge_expired` runs it daily at 03:00 UTC on q.cpu (beat
schedule in marcus.core.celery_app; beat runs inside worker-cpu, `-B`). It is not a pipeline
step: no Step row, not seen by the dispatcher.
"""

import logging
import os
import shutil
import stat
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import and_, delete, func, or_, select, tuple_, update
from sqlalchemy.orm import Session

from marcus.core import storage
from marcus.core.celery_app import celery_app
from marcus.core.enums import (
    ACTIVE_IMAGE_STATUSES,
    ACTIVE_PAPER_STATUSES,
    Engine,
    ImageJobStatus,
    PaperStatus,
    StepStatus,
)
from marcus.core.models import ImageJob, OcsrCache, Owner, Paper, SegCache, Step
from marcus.core.pipeline import ACTIVE, cancel_paper, seg_cache_key
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)

TASK_NAME = "marcus.retention.purge_expired"
SOFT_LIMIT_S = 1800
HARD_LIMIT_S = 1900
BATCH_SIZE = 200
ORPHAN_MIN_AGE = timedelta(days=1)
LOOKUP_CHUNK = 500  # ids per "which of these still exist" query in the orphan sweep
DEPICTION_MAX_DAYS = 30
DEPICTIONS_MAX_BYTES = 2 * 1024**3

# Distribution that carries each engine's version (the cpu worker image has none of them).
_ENGINE_DISTS = {
    Engine.DECIMER: "decimer",
    Engine.DECIMER_HAND: "decimer",
    Engine.MOLNEXTR: "MolNexTR",
    Engine.MOLSCRIBE: "MolScribe",
}


@dataclass
class PurgeReport:
    papers: int = 0
    papers_cancelled: int = 0  # of `papers`: had an active step, went through cancel_paper
    image_jobs: int = 0
    seg_cache: int = 0
    ocsr_cache: int = 0
    orphan_paper_dirs: int = 0
    orphan_image_files: int = 0
    owner_ips: int = 0  # owners whose recorded IP was deleted
    work_ips: int = 0  # papers and image jobs whose address was deleted (backstop)
    depictions: int = 0  # files removed under data_root/depictions (age, then size cap)
    file_errors: int = 0
    errors: list[str] = field(default_factory=list)  # phases that failed (logged with traceback)


# --- engine versions -------------------------------------------------------------------------


def _static_version(engine: Engine) -> str:
    """The engine's version as its worker computes it. Constructing an engine never loads a
    model (marcus.workers.ocsr.base.OcsrEngine); the engine modules are imported only here,
    and only when the engine's package is installed."""
    if engine in (Engine.DECIMER, Engine.DECIMER_HAND):
        from marcus.workers.ocsr.decimer import DecimerEngine

        return DecimerEngine(hand_drawn=engine is Engine.DECIMER_HAND).version
    if engine is Engine.MOLNEXTR:
        from marcus.workers.ocsr.molnextr import MolnextrEngine

        return MolnextrEngine().version
    from marcus.workers.ocsr.molscribe import MolscribeEngine

    return MolscribeEngine().version


def current_ocsr_versions() -> dict[str, str]:
    """engine -> current version, for the engines whose package is installed here. Engines
    without it (all of them in the cpu worker) are left out: their cache rows are purged by
    age only. `fake` never writes the cache."""
    versions: dict[str, str] = {}
    for engine, dist in _ENGINE_DISTS.items():
        try:
            distribution(dist)
        except PackageNotFoundError:
            continue
        try:
            versions[engine.value] = _static_version(engine)
        except Exception as exc:  # noqa: BLE001 - unknown version: age-based purge only
            log.warning("retention: version of %s unknown (%s); age-based purge only",
                        engine.value, exc)  # fmt: skip
    return versions


# --- files -----------------------------------------------------------------------------------


def _remove(path: Path, report: PurgeReport) -> bool:
    """Remove a file, symlink or directory tree. False when it was not there or could not be
    removed (logged and counted)."""
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        report.file_errors += 1
        log.warning("retention: could not remove %s (%s: %s)", path, type(exc).__name__, exc)
        return False


def _image_files(job_id: uuid.UUID) -> list[Path]:
    path = storage.image_job_path(job_id)
    return [path, path.with_name(path.name + ".tmp")]  # .tmp: an interrupted atomic write


# --- rows ------------------------------------------------------------------------------------


def _purge_papers(session: Session, now: datetime, batch: int, report: PurgeReport) -> None:
    while True:
        ids = list(
            session.execute(
                select(Paper.id)
                .where(Paper.expires_at < now)
                .order_by(Paper.expires_at, Paper.id)
                .limit(batch)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not ids:
            return
        busy = sorted(
            session.execute(
                select(Step.paper_id)
                .where(Step.paper_id.in_(ids), Step.status.in_(ACTIVE))
                .distinct()
            ).scalars()
        )
        for paper_id in busy:
            cancel_paper(session, paper_id)
        session.execute(
            delete(Paper).where(Paper.id.in_(ids)).execution_options(synchronize_session=False)
        )
        session.commit()
        session.expunge_all()
        report.papers += len(ids)
        report.papers_cancelled += len(busy)
        for paper_id in ids:
            _remove(storage.paper_dir(paper_id), report)


def _purge_image_jobs(session: Session, now: datetime, batch: int, report: PurgeReport) -> None:
    while True:
        ids = list(
            session.execute(
                select(ImageJob.id)
                .where(ImageJob.expires_at < now)
                .order_by(ImageJob.expires_at, ImageJob.id)
                .limit(batch)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not ids:
            return
        # Lock order as in the planner: parent row (above), then its steps.
        session.execute(
            update(Step)
            .where(Step.image_job_id.in_(ids), Step.status.in_(ACTIVE))
            .values(status=StepStatus.CANCELLED.value, finished_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        session.execute(
            delete(ImageJob)
            .where(ImageJob.id.in_(ids))
            .execution_options(synchronize_session=False)
        )
        session.commit()
        session.expunge_all()
        report.image_jobs += len(ids)
        for job_id in ids:
            for path in _image_files(job_id):
                _remove(path, report)


def _delete_in_batches(session: Session, model, keys: list, condition, batch: int) -> int:
    """Delete the rows of `model` matching `condition`, `batch` rows per transaction."""
    total = 0
    while True:
        rows = session.execute(
            select(*keys).where(condition).limit(batch).with_for_update(skip_locked=True)
        ).all()
        if not rows:
            return total
        session.execute(
            delete(model)
            .where(tuple_(*keys).in_([tuple(r) for r in rows]))
            .execution_options(synchronize_session=False)
        )
        session.commit()
        total += len(rows)


def _purge_seg_cache(session: Session, cutoff: datetime, batch: int, report: PurgeReport) -> None:
    conditions = [SegCache.created_at < cutoff]
    version = get_settings().seg_version
    if version:
        conditions.append(SegCache.seg_version != seg_cache_key(version))
    else:
        log.info("retention: MARCUS_SEG_VERSION unset; seg_cache purged by age only")
    report.seg_cache += _delete_in_batches(
        session,
        SegCache,
        [SegCache.owner_id, SegCache.pdf_sha256, SegCache.seg_version],
        or_(*conditions),
        batch,
    )


def _purge_ocsr_cache(
    session: Session,
    cutoff: datetime,
    versions: dict[str, str],
    batch: int,
    report: PurgeReport,
) -> None:
    conditions = [OcsrCache.created_at < cutoff]
    conditions += [
        and_(OcsrCache.engine == engine, OcsrCache.engine_version != version)
        for engine, version in sorted(versions.items())
    ]
    keys = [OcsrCache.owner_id, OcsrCache.image_sha256, OcsrCache.engine, OcsrCache.engine_version]
    report.ocsr_cache += _delete_in_batches(session, OcsrCache, keys, or_(*conditions), batch)


def _purge_owner_ips(session: Session, now: datetime, batch: int, report: PurgeReport) -> None:
    cutoff = now - timedelta(days=get_settings().owner_ip_retention_days)
    while True:
        ids = list(
            session.execute(
                select(Owner.id)
                .where(Owner.created_ip.is_not(None), Owner.created_at < cutoff)
                .limit(batch)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not ids:
            return
        session.execute(
            update(Owner)
            .where(Owner.id.in_(ids))
            .values(created_ip=None)
            .execution_options(synchronize_session=False)
        )
        session.commit()
        report.owner_ips += len(ids)


def _purge_work_ips(session: Session, now: datetime, batch: int, report: PurgeReport) -> None:
    cutoff = now - timedelta(days=get_settings().owner_ip_retention_days)
    for model, active in ((Paper, ACTIVE_PAPER_STATUSES), (ImageJob, ACTIVE_IMAGE_STATUSES)):
        while True:
            ids = list(
                session.execute(
                    select(model.id)
                    .where(
                        model.started_ip.is_not(None),
                        or_(
                            model.status.not_in(active),
                            func.coalesce(model.started_ip_at, model.created_at) < cutoff,
                        ),
                    )
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                ).scalars()
            )
            if not ids:
                break
            session.execute(
                update(model)
                .where(model.id.in_(ids))
                .values(started_ip=None, started_ip_at=None)
                .execution_options(synchronize_session=False)
            )
            session.commit()
            report.work_ips += len(ids)


# --- orphans ---------------------------------------------------------------------------------


def _server_uuid(name: str, suffixes: tuple[str, ...]) -> uuid.UUID | None:
    """The uuid of a server-made entry name `<uuid><suffix>`, else None (left alone)."""
    for suffix in suffixes:
        if suffix and not name.endswith(suffix):
            continue
        stem = name[: len(name) - len(suffix)] if suffix else name
        try:
            value = uuid.UUID(stem)
        except ValueError:
            continue
        if str(value) == stem:
            return value
    return None


def _old_entries(root: Path, cutoff_ts: float, suffixes: tuple[str, ...]):
    """(uuid, path) of server-made entries in `root` last modified before `cutoff_ts`."""
    try:
        entries = list(root.iterdir())
    except FileNotFoundError:
        return []
    found = []
    for path in entries:
        entry_id = _server_uuid(path.name, suffixes)
        if entry_id is None:
            continue
        try:
            if path.lstat().st_mtime >= cutoff_ts:
                continue
        except FileNotFoundError:
            continue
        found.append((entry_id, path))
    return found


def _live_ids(session: Session, model, deleted_status: str, ids: list[uuid.UUID]) -> set:
    live: set[uuid.UUID] = set()
    for start in range(0, len(ids), LOOKUP_CHUNK):
        chunk = ids[start : start + LOOKUP_CHUNK]
        live.update(
            session.execute(
                select(model.id).where(model.id.in_(chunk), model.status != deleted_status)
            ).scalars()
        )
    session.rollback()  # end the read transaction before touching files
    return live


def _sweep(session: Session, root: Path, suffixes, model, deleted_status, cutoff_ts, report):
    entries = _old_entries(root, cutoff_ts, suffixes)
    if not entries:
        return 0
    live = _live_ids(session, model, deleted_status, sorted({i for i, _ in entries}))
    return sum(_remove(path, report) for entry_id, path in entries if entry_id not in live)


def _sweep_orphans(session: Session, now: datetime, report: PurgeReport) -> None:
    root = get_settings().data_root
    cutoff_ts = (now - ORPHAN_MIN_AGE).timestamp()
    report.orphan_paper_dirs += _sweep(
        session, root / "papers", ("",), Paper, PaperStatus.DELETED.value, cutoff_ts, report
    )
    report.orphan_image_files += _sweep(
        session,
        root / "images",
        (".png", ".png.tmp"),
        ImageJob,
        ImageJobStatus.DELETED.value,
        cutoff_ts,
        report,
    )


# --- depictions -----------------------------------------------------------------------------


def _depiction_files(root: Path) -> tuple[list[tuple[float, int, Path]], list[Path]]:
    """(mtime, size, path) of the regular files anywhere under `root` (per owner:
    `<owner id>/<xx>/`), and the directories below `root`, deepest first. Symlinks are never
    followed."""
    found, dirs = [], []
    for top, subdirs, names in os.walk(root, followlinks=False):
        top_path = Path(top)
        dirs.extend(top_path / d for d in subdirs)
        for name in names:
            path = top_path / name
            try:
                st = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode):
                found.append((st.st_mtime, st.st_size, path))
    dirs.sort(key=lambda d: len(d.parts), reverse=True)
    return found, dirs


def _remove_empty_dirs(dirs: list[Path], cutoff_ts: float) -> None:
    """Remove the directories (deepest first) that are empty and unchanged since `cutoff_ts`:
    a younger one may be about to get its first drawing."""
    for path in dirs:
        try:
            if path.is_symlink() or path.lstat().st_mtime >= cutoff_ts:
                continue
            path.rmdir()
        except OSError:  # not empty, gone, or not removable: left for a later run
            continue


def _purge_depictions(now: datetime, report: PurgeReport) -> None:
    found, dirs = _depiction_files(storage.depictions_dir())
    files = sorted(found)  # oldest first
    cutoff_ts = (now - timedelta(days=DEPICTION_MAX_DAYS)).timestamp()
    total = sum(size for _, size, _ in files)
    for mtime, size, path in files:
        if mtime >= cutoff_ts and total <= DEPICTIONS_MAX_BYTES:
            break  # the rest are younger and the directory is within its cap
        if _remove(path, report):
            report.depictions += 1
            total -= size
        elif not os.path.lexists(path):
            total -= size  # gone meanwhile; one that could not be removed still counts
    _remove_empty_dirs(dirs, (now - ORPHAN_MIN_AGE).timestamp())


# --- entry points ----------------------------------------------------------------------------


def purge_expired(
    session: Session,
    now: datetime,
    *,
    batch_size: int = BATCH_SIZE,
    ocsr_versions: dict[str, str] | None = None,
    report: PurgeReport | None = None,
) -> PurgeReport:
    """Purge expired papers and image jobs, stale cache rows, orphan files, old owner IPs and
    old depictions (module doc).

    Commits once per batch. Each phase runs on its own: a phase that raises is rolled back,
    logged and named in `report.errors`, and the next phase still runs (a soft time limit
    stops them all). `ocsr_versions` (engine -> current version) defaults to
    `current_ocsr_versions()`. `report` is filled as batches commit, so a caller interrupted
    by a time limit still knows what was done.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    report = report if report is not None else PurgeReport()
    versions = current_ocsr_versions() if ocsr_versions is None else ocsr_versions
    cache_cutoff = now - timedelta(days=get_settings().retention_days)

    phases = [
        ("papers", lambda: _purge_papers(session, now, batch_size, report)),
        ("image_jobs", lambda: _purge_image_jobs(session, now, batch_size, report)),
        ("seg_cache", lambda: _purge_seg_cache(session, cache_cutoff, batch_size, report)),
        (
            "ocsr_cache",
            lambda: _purge_ocsr_cache(session, cache_cutoff, versions, batch_size, report),
        ),
        ("orphans", lambda: _sweep_orphans(session, now, report)),
        ("owner_ips", lambda: _purge_owner_ips(session, now, batch_size, report)),
        ("work_ips", lambda: _purge_work_ips(session, now, batch_size, report)),
        ("depictions", lambda: _purge_depictions(now, report)),
    ]
    for name, run in phases:
        try:
            run()
        except SoftTimeLimitExceeded:
            raise  # the task's time is up: stop every phase
        except Exception:
            # One broken phase must not cost the others their run: roll back its open batch
            # (committed batches stay), log, record, go on.
            session.rollback()
            report.errors.append(name)
            log.exception("retention purge phase %s failed", name)
    log.info("retention purge done: %s", report)
    return report


@celery_app.task(
    name=TASK_NAME,
    ignore_result=True,
    soft_time_limit=SOFT_LIMIT_S,
    time_limit=HARD_LIMIT_S,
)
def purge_expired_task() -> None:
    """Daily beat task (q.cpu). Committed batches stay purged if the soft limit stops it."""
    from marcus.core.db import get_sync_sessionmaker

    report = PurgeReport()
    with get_sync_sessionmaker()() as session:
        try:
            purge_expired(session, datetime.now(UTC), report=report)
        except SoftTimeLimitExceeded:
            session.rollback()
            log.warning("retention purge stopped at its time limit; done so far: %s", report)
        except Exception:
            session.rollback()
            log.exception("retention purge failed; done so far: %s", report)
            raise
