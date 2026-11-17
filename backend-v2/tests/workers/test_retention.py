"""Retention purge (marcus.workers.retention): expired rows and files, caches, orphans."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url

from marcus.core import pipeline, storage
from marcus.core.models import (
    Curation,
    ImageJob,
    OcsrCache,
    Owner,
    Paper,
    Prediction,
    SegCache,
    Segment,
    Step,
)
from marcus.core.pipeline import seg_cache_key
from marcus.core.settings import get_settings
from marcus.workers import retention
from marcus.workers.retention import PurgeReport, purge_expired
from tests.factories import make_image_job, make_owner, make_paper

NOW = datetime(2026, 11, 17, 3, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def count(s, model) -> int:
    return s.execute(select(func.count()).select_from(model)).scalar_one()


def expire(s, row, when=NOW - DAY) -> None:
    row.expires_at = when
    s.commit()


def finish_all_steps(s, paper_id) -> None:
    s.execute(update(Step).where(Step.paper_id == paper_id).values(status="done"))
    s.commit()


def age(path, seconds_ago: float) -> None:
    t = NOW.timestamp() - seconds_ago
    os.utime(path, (t, t))


def purge(s, **kw) -> PurgeReport:
    kw.setdefault("ocsr_versions", {})
    return purge_expired(s, NOW, **kw)


# --- papers -------------------------------------------------------------------------------


def test_expired_paper_rows_and_files_removed(db_session):
    s = db_session
    paper = make_paper(s)
    seg = Segment(paper_id=paper.id, page=0, idx=0, bbox=[0, 0, 1, 1], image_sha256="0" * 64)
    s.add(seg)
    s.flush()
    s.add(Curation(segment_id=seg.id, status="unchecked"))
    s.add(Prediction(segment_id=seg.id, engine="decimer", engine_version="v", smiles="C",
                     valid=True, ms=1))  # fmt: skip
    page = storage.page_image_path(paper.id, 0)
    page.parent.mkdir(parents=True)
    page.write_bytes(b"png")
    s.commit()
    finish_all_steps(s, paper.id)
    expire(s, paper)
    paper_id = paper.id

    report = purge(s)

    assert report.papers == 1 and report.papers_cancelled == 0
    assert s.get(Paper, paper_id) is None
    for model in (Step, Segment, Curation, Prediction):
        assert count(s, model) == 0, model
    assert not storage.paper_dir(paper_id).exists()
    assert count(s, Owner) == 1  # owners are not purged here


def test_fresh_paper_kept(db_session):
    s = db_session
    paper = make_paper(s)
    s.commit()
    expire(s, paper, NOW + timedelta(seconds=1))

    report = purge(s)

    assert report.papers == 0
    assert s.get(Paper, paper.id) is not None
    assert storage.pdf_path(paper.id).is_file()
    assert count(s, Step) == 1  # check_pdf only, untouched
    assert s.execute(select(Step.status)).scalar_one() == "pending"


def test_expired_paper_with_running_step_is_cancelled_then_purged(db_session, monkeypatch):
    s = db_session
    busy = make_paper(s)
    idle = make_paper(s, s.get(Owner, busy.owner_id))
    s.execute(update(Step).where(Step.paper_id == busy.id).values(status="running"))
    s.commit()
    finish_all_steps(s, idle.id)
    expire(s, busy)
    expire(s, idle)

    seen = []
    real_cancel = pipeline.cancel_paper

    def spy(session, paper_id):
        real_cancel(session, paper_id)
        session.flush()
        statuses = session.execute(select(Step.status).where(Step.paper_id == paper_id)).scalars()
        seen.append((paper_id, sorted(statuses)))

    monkeypatch.setattr(retention, "cancel_paper", spy)
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as listener:
        listener.execute("LISTEN marcus_steps")
        report = purge(s)
        notes = list(listener.notifies(timeout=2, stop_after=1))

    assert seen == [(busy.id, ["cancelled"])]  # only the paper with an active step
    assert [n.payload for n in notes] == ["q.cpu"]  # the dispatcher learns the slot is free
    assert report.papers == 2 and report.papers_cancelled == 1
    assert count(s, Paper) == 0 and count(s, Step) == 0
    assert not storage.paper_dir(busy.id).exists()
    assert not storage.paper_dir(idle.id).exists()


def test_papers_purged_in_batches(db_session, monkeypatch):
    s = db_session
    owner = make_owner(s)
    papers = [make_paper(s, owner) for _ in range(5)]
    s.commit()
    for p in papers:
        finish_all_steps(s, p.id)
        expire(s, p)
    commits = []
    real_commit = s.commit
    monkeypatch.setattr(s, "commit", lambda: (commits.append(1), real_commit())[1])

    report = purge(s, batch_size=2)

    assert report.papers == 5
    assert count(s, Paper) == 0
    assert len(commits) >= 3  # 2 + 2 + 1: never one transaction for everything
    assert all(not storage.paper_dir(p.id).exists() for p in papers)


def test_locked_paper_is_skipped_not_waited_for(db_session):
    from marcus.core.db import get_sync_sessionmaker

    s = db_session
    owner = make_owner(s)
    locked, free = make_paper(s, owner), make_paper(s, owner)
    s.commit()
    for p in (locked, free):
        finish_all_steps(s, p.id)
        expire(s, p)
    with get_sync_sessionmaker()() as other:
        other.execute(select(Paper).where(Paper.id == locked.id).with_for_update())
        report = purge(s)
        other.rollback()

    assert report.papers == 1
    assert s.get(Paper, free.id) is None
    s.expire_all()
    assert s.get(Paper, locked.id) is not None  # next run gets it


# --- image jobs -------------------------------------------------------------------------


def test_expired_image_job_cancelled_and_purged(db_session):
    s = db_session
    job, step = make_image_job(s)
    path = storage.image_job_path(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")
    path.with_name(path.name + ".tmp").write_bytes(b"half")
    step.status = "queued"
    fresh, _ = make_image_job(s)
    fresh_path = storage.image_job_path(fresh.id)
    fresh_path.write_bytes(b"png")
    s.commit()
    expire(s, job)
    job_id, queue = job.id, step.queue

    url = make_url(get_settings().database_url).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as listener:
        listener.execute("LISTEN marcus_steps")
        report = purge(s)
        notes = list(listener.notifies(timeout=2, stop_after=1))

    assert [n.payload for n in notes] == [queue]  # cancelled before the row went away
    assert report.image_jobs == 1
    assert s.get(ImageJob, job_id) is None
    assert s.execute(select(Step.image_job_id)).scalars().all() == [fresh.id]
    assert not path.exists() and not path.with_name(path.name + ".tmp").exists()
    assert fresh_path.is_file()


# --- caches -----------------------------------------------------------------------------


def _seg(s, sha: str, version_key: str, created: datetime) -> None:
    s.add(SegCache(pdf_sha256=sha * 64, seg_version=version_key, payload={}, created_at=created))


def _ocsr(s, sha: str, engine: str, version: str, created: datetime) -> None:
    s.add(OcsrCache(image_sha256=sha * 64, engine=engine, engine_version=version, smiles="C",
                    created_at=created))  # fmt: skip


def test_seg_cache_purged_by_age_and_version(db_session, monkeypatch):
    monkeypatch.setenv("MARCUS_SEG_VERSION", "segv-2")
    get_settings.cache_clear()
    s = db_session
    current, old_version = seg_cache_key("segv-2"), seg_cache_key("segv-1")
    _seg(s, "a", current, NOW - timedelta(days=31))  # too old
    _seg(s, "b", current, NOW - timedelta(days=29))  # kept
    _seg(s, "c", old_version, NOW - DAY)  # other segmenter version
    s.commit()

    report = purge(s)

    assert report.seg_cache == 2
    assert s.execute(select(SegCache.pdf_sha256)).scalars().all() == ["b" * 64]


def test_seg_cache_version_purge_skipped_without_configured_version(db_session):
    s = db_session
    _seg(s, "a", seg_cache_key("segv-1"), NOW - DAY)
    _seg(s, "b", seg_cache_key("segv-1"), NOW - timedelta(days=31))
    s.commit()

    report = purge(s)

    assert report.seg_cache == 1  # age only: an unset version must not wipe the cache
    assert s.execute(select(SegCache.pdf_sha256)).scalars().all() == ["a" * 64]


def test_ocsr_cache_purged_by_age_and_known_engine_version(db_session):
    s = db_session
    _ocsr(s, "a", "decimer", "2.7", NOW - timedelta(days=31))  # too old
    _ocsr(s, "b", "decimer", "2.7", NOW - DAY)  # current: kept
    _ocsr(s, "c", "decimer", "2.6", NOW - DAY)  # old engine version
    _ocsr(s, "d", "molnextr", "abc1234", NOW - DAY)  # version unknown here: kept
    _ocsr(s, "e", "molnextr", "abc1234", NOW - timedelta(days=40))  # too old
    s.commit()

    report = purge(s, ocsr_versions={"decimer": "2.7"}, batch_size=1)

    assert report.ocsr_cache == 3
    left = s.execute(select(OcsrCache.image_sha256).order_by(OcsrCache.image_sha256))
    assert left.scalars().all() == ["b" * 64, "d" * 64]


def test_current_ocsr_versions_only_for_installed_engines(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    installed = {"decimer"}

    def fake_distribution(name):
        if name not in installed:
            raise PackageNotFoundError(name)
        return object()

    monkeypatch.setattr(retention, "distribution", fake_distribution)
    monkeypatch.setattr(
        retention,
        "_static_version",
        lambda engine: {"decimer": "2.7", "decimer-hand": "2.7-hand"}[engine.value],
    )
    assert retention.current_ocsr_versions() == {"decimer": "2.7", "decimer-hand": "2.7-hand"}

    installed.clear()  # the cpu worker image: no engine package at all
    assert retention.current_ocsr_versions() == {}


def test_current_ocsr_versions_skips_engine_whose_version_fails(monkeypatch):
    monkeypatch.setattr(retention, "distribution", lambda name: object())

    def boom(engine):
        if engine.value == "molscribe":
            raise RuntimeError("not from a pinned commit")
        return "v-" + engine.value

    monkeypatch.setattr(retention, "_static_version", boom)
    assert retention.current_ocsr_versions() == {
        "decimer": "v-decimer", "decimer-hand": "v-decimer-hand", "molnextr": "v-molnextr",
    }  # fmt: skip


# --- orphans ----------------------------------------------------------------------------


def test_orphan_dir_removed(db_session):
    s = db_session
    live = make_paper(s)
    deleted = make_paper(s, s.get(Owner, live.owner_id))
    s.commit()
    deleted_dir = storage.paper_dir(deleted.id)
    deleted.status = "deleted"  # e.g. cancel_paper could not remove the files
    s.commit()
    papers_root = get_settings().data_root / "papers"
    orphan = papers_root / str(uuid.uuid4())
    (orphan / "pages").mkdir(parents=True)
    (orphan / "pages" / "0000.png").write_bytes(b"png")
    young_orphan = papers_root / str(uuid.uuid4())
    young_orphan.mkdir()
    stranger = papers_root / "not-a-uuid"
    stranger.mkdir()
    for path in (orphan, storage.paper_dir(live.id), deleted_dir, stranger):
        age(path, 2 * 86400)
    age(young_orphan, 3600)

    report = purge(s)

    assert report.orphan_paper_dirs == 2
    assert not orphan.exists() and not deleted_dir.exists()
    assert storage.pdf_path(live.id).is_file()
    assert young_orphan.is_dir()  # an upload may still be committing
    assert stranger.is_dir()  # never a server-made name: left alone
    assert s.get(Paper, deleted.id) is not None  # not expired: the row stays


def test_orphan_image_files_removed(db_session):
    s = db_session
    job, _ = make_image_job(s)
    s.commit()
    images = get_settings().data_root / "images"
    images.mkdir(parents=True, exist_ok=True)
    live = storage.image_job_path(job.id)
    live.write_bytes(b"png")
    orphan = storage.image_job_path(uuid.uuid4())
    orphan.write_bytes(b"png")
    orphan_tmp = images / f"{uuid.uuid4()}.png.tmp"
    orphan_tmp.write_bytes(b"half")
    young = storage.image_job_path(uuid.uuid4())
    young.write_bytes(b"png")
    for path in (live, orphan, orphan_tmp):
        age(path, 2 * 86400)

    report = purge(s)

    assert report.orphan_image_files == 2
    assert live.is_file() and young.is_file()
    assert not orphan.exists() and not orphan_tmp.exists()


def test_purge_with_no_data_root_dirs(db_session):
    assert purge(db_session) == PurgeReport()


def test_file_error_is_counted_not_raised(db_session, monkeypatch):
    s = db_session
    paper = make_paper(s)
    s.commit()
    finish_all_steps(s, paper.id)
    expire(s, paper)

    def denied(path, *a, **kw):
        raise PermissionError(13, "denied", str(path))

    monkeypatch.setattr(retention.shutil, "rmtree", denied)
    report = purge(s)

    assert report.papers == 1 and report.file_errors == 1
    assert s.get(Paper, paper.id) is None  # rows go; the orphan sweep retries the files


# --- depictions -----------------------------------------------------------------------


def _depiction(sha: str, days_old: float, size: int = 10, suffix: str = ".svg"):
    path = storage.depiction_path(sha)
    path = path.with_suffix(suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    age(path, days_old * 86400)
    return path


def test_retention_purges_old_depictions(db_session):
    old = _depiction("a" * 64, 31)
    old_marker = _depiction("b" * 64, 40, size=0, suffix=".nodraw")
    old_tmp = _depiction("c" * 64, 31, suffix=".svg.123.abc.tmp")
    young = _depiction("d" * 64, 29)
    young_marker = _depiction("e" * 64, 1, size=0, suffix=".nodraw")

    report = purge(db_session)

    assert report.depictions == 3
    assert not old.exists() and not old_marker.exists() and not old_tmp.exists()
    assert young.is_file() and young_marker.is_file()


def test_retention_depictions_size_cap_oldest_first(db_session, monkeypatch):
    monkeypatch.setattr(retention, "DEPICTIONS_MAX_BYTES", 250)
    files = [_depiction(f"{i:x}" * 64, days_old=10 - i, size=100) for i in range(5)]
    # oldest first: files[0] (10 days) .. files[4] (6 days); 500 bytes, cap 250

    report = purge(db_session)

    assert report.depictions == 3
    assert [f.exists() for f in files] == [False, False, False, True, True]


def test_retention_depictions_symlink_and_strangers_left(db_session, tmp_path):
    root = get_settings().data_root / "depictions"
    root.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    link = root / "ab" / ("ab" + "0" * 62 + ".svg")
    link.parent.mkdir()
    link.symlink_to(outside)
    age(outside, 60 * 86400)

    purge(db_session)

    assert outside.read_bytes() == b"keep"


# --- celery task and beat ---------------------------------------------------------------


def test_purge_task_registered_on_cpu_queue_with_limits():
    from celery.schedules import crontab

    from marcus.core.celery_app import celery_app
    from marcus.workers import cpu  # noqa: F401  (the cpu worker's --include)

    task = celery_app.tasks["marcus.retention.purge_expired"]
    assert (task.soft_time_limit, task.time_limit) == (1800, 1900)
    (entry,) = [
        e for e in celery_app.conf.beat_schedule.values()
        if e["task"] == "marcus.retention.purge_expired"
    ]  # fmt: skip
    assert entry["schedule"] == crontab(hour=3, minute=0)
    assert entry["options"]["queue"] == "q.cpu"
    assert celery_app.conf.timezone == "UTC" and celery_app.conf.enable_utc is True
    assert celery_app.amqp.router.route({}, task.name)["queue"].name == "q.cpu"


def test_purge_task_runs_purge_with_a_fresh_session(db_session, monkeypatch):
    calls = []

    def fake_purge(session, now, **kw):
        calls.append((session, now))
        return PurgeReport(papers=3)

    monkeypatch.setattr(retention, "purge_expired", fake_purge)
    before = datetime.now(UTC)
    retention.purge_expired_task.run()
    ((session, now),) = calls
    assert before <= now <= datetime.now(UTC)
    assert session is not db_session


def test_purge_task_soft_limit_keeps_committed_batches(db_session, monkeypatch, caplog):
    from celery.exceptions import SoftTimeLimitExceeded

    def slow_purge(session, now, *, report, **kw):
        report.papers = 7
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(retention, "purge_expired", slow_purge)
    with caplog.at_level("WARNING", logger="marcus.workers.retention"):
        retention.purge_expired_task.run()
    assert "papers=7" in caplog.text


def test_a_failing_phase_does_not_skip_the_others(db_session, monkeypatch, caplog):
    s = db_session
    paper = make_paper(s)
    s.commit()
    finish_all_steps(s, paper.id)
    expire(s, paper)
    _seg(s, "a", seg_cache_key("segv-1"), NOW - timedelta(days=31))
    s.commit()

    def broken(session, *a, **kw):
        session.execute(select(func.count()).select_from(ImageJob))
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(retention, "_purge_image_jobs", broken)
    with caplog.at_level("ERROR", logger="marcus.workers.retention"):
        report = purge(s)

    assert report.errors == ["image_jobs"]
    assert report.papers == 1 and report.seg_cache == 1  # before and after the broken phase
    assert "image_jobs" in caplog.text and "disk on fire" in caplog.text
    assert count(s, Paper) == 0 and count(s, SegCache) == 0


@pytest.mark.parametrize("bad", [0, -1])
def test_batch_size_must_be_positive(db_session, bad):
    with pytest.raises(ValueError):
        purge(db_session, batch_size=bad)
