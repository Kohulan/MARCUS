"""pdfsafe: subprocess isolation, limits, process-group kill, billiard (Celery prefork) safety."""

import os
import shutil
import time
import uuid
from pathlib import Path

import billiard
import pytest

from marcus.core.storage import pdf_path
from marcus.workers import pdfsafe
from marcus.workers.runtime import BadInput

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pdfs"


def _paper(name="two_page.pdf"):
    pid = uuid.uuid4()
    pdf_path(pid).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / name, pdf_path(pid))
    return pdf_path(pid)


def test_hanging_child_is_killed_on_timeout():
    start = time.monotonic()
    with pytest.raises(pdfsafe.ChildTimeout):
        pdfsafe.run_op("_sleep", [], timeout_s=2)
    assert time.monotonic() - start < 8


def test_timeout_maps_to_bad_input(monkeypatch):
    real = pdfsafe.run_op
    monkeypatch.setattr(pdfsafe, "run_op", lambda op, args, t, m: real("_sleep", [], 2, m))
    with pytest.raises(BadInput, match="timeout"):
        pdfsafe.page_count(_paper(), timeout_s=2)


def test_rlimit_as_is_enforced():
    assert pdfsafe.run_op("_alloc", [10], timeout_s=20, mem_mb=2048) == 10 * 2**20
    with pytest.raises(pdfsafe.ChildFailed):
        pdfsafe.run_op("_alloc", [1500], timeout_s=20, mem_mb=512)


def test_child_errors_come_back_as_short_messages():
    with pytest.raises(pdfsafe.ChildFailed, match="RuntimeError: boom"):
        pdfsafe.run_op("_fail", [], timeout_s=20)


def test_child_environment_is_minimal(monkeypatch):
    monkeypatch.setenv("MARCUS_DATABASE_URL", "postgresql://secret")
    env = pdfsafe._child_env()
    assert not any(k.startswith("MARCUS_") for k in env)
    assert "PATH" in env


def test_timeout_kills_the_whole_process_group():
    proc_pids = []
    real_kill = pdfsafe._kill_group

    def spy(proc):
        proc_pids.append(proc.pid)
        real_kill(proc)

    pdfsafe._kill_group = spy
    try:
        with pytest.raises(pdfsafe.ChildTimeout):
            pdfsafe.run_op("_sleep", [], timeout_s=1)
    finally:
        pdfsafe._kill_group = real_kill
    with pytest.raises(ProcessLookupError):
        os.killpg(proc_pids[0], 0)


def _count_in_worker(path):
    return pdfsafe.page_count(Path(path), timeout_s=20)


def test_page_count_works_inside_celery_prefork_style_daemon_process(tmp_path):
    pool = billiard.Pool(1)  # same pool class Celery prefork uses; its workers are daemonic
    try:
        assert pool.apply(_count_in_worker, (str(_paper()),)) == 2
    finally:
        pool.close()
        pool.join()
