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
from marcus.workers.runtime import BadInput, StepTimeout

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


def test_timeout_maps_to_a_retryable_step_timeout(monkeypatch):
    """A child past its wall limit is a timeout (retried once), not bad input (D3 F2)."""
    real = pdfsafe.run_op
    monkeypatch.setattr(pdfsafe, "run_op", lambda op, args, t, m, th=None: real("_sleep", [], 2, m))
    with pytest.raises(StepTimeout, match="timeout") as info:
        pdfsafe.page_count(_paper(), timeout_s=2)
    assert not isinstance(info.value, BadInput)


def test_corrupt_pdf_stays_bad_input():
    with pytest.raises(BadInput):
        pdfsafe.page_count(_paper("png_as.pdf"), timeout_s=20)


def test_out_of_memory_child_stays_bad_input(monkeypatch):
    real = pdfsafe.run_op
    monkeypatch.setattr(
        pdfsafe, "run_op", lambda op, args, t, m, th=None: real("_alloc", [1500], 20, 512)
    )
    with pytest.raises(BadInput, match="out of memory"):
        pdfsafe.page_count(_paper(), timeout_s=20)


def test_rlimit_as_is_enforced():
    assert pdfsafe.run_op("_alloc", [10], timeout_s=20, mem_mb=2048) == 10 * 2**20
    with pytest.raises(pdfsafe.ChildFailed, match="out of memory"):
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


def test_docling_threads_are_pinned_and_cpu_limit_scaled():
    env = pdfsafe._child_env(4)
    assert env["TOKENIZERS_PARALLELISM"] == "false"
    assert env["OMP_NUM_THREADS"] == env["MKL_NUM_THREADS"] == env["OPENBLAS_NUM_THREADS"] == "4"
    assert "OMP_NUM_THREADS" not in pdfsafe._child_env()


def _child(op, mem_mb, cpu_s, preexec=None, timeout=60):
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-I", "-m", "marcus.workers.pdfsafe_child", op, str(mem_mb),
         str(cpu_s), str(os.getpid())],
        input=b'{"args": []}', capture_output=True, timeout=timeout, preexec_fn=preexec,
    )  # fmt: skip
    return proc, (json.loads(proc.stdout) if proc.stdout else None)


def test_cpu_limit_kills_a_busy_child_with_sigxcpu():
    import signal

    # Wall timeout (60 s) is far above the 1 s CPU limit, so only RLIMIT_CPU can stop it.
    start = time.monotonic()
    proc, reply = _child("_spin", 2048, 1)
    assert proc.returncode == -signal.SIGXCPU
    assert reply is None
    assert time.monotonic() - start < 20


def test_setrlimit_failure_is_a_child_failure():
    import resource

    def lower_hard_limit():
        resource.setrlimit(resource.RLIMIT_AS, (2**30, 2**30))

    # Hard RLIMIT_AS is 1 GiB, the child asks for 2 GiB: raising it must fail.
    proc, reply = _child("_sleep", 2048, 60, preexec=lower_hard_limit)
    assert reply["ok"] is False
    assert "ValueError" in reply["error"]


def test_child_exits_if_parent_pid_does_not_match():
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-I", "-m", "marcus.workers.pdfsafe_child", "_sleep", "2048", "60", "1"],
        input=b'{"args": []}', capture_output=True, timeout=20,
    )  # fmt: skip
    assert out.returncode == 1 and out.stdout == b""


def test_run_op_cpu_limit_has_headroom_for_threaded_ops(monkeypatch):
    seen = {}

    class Boom(Exception):
        pass

    def fake_popen(argv, **kw):
        seen["argv"] = argv
        raise Boom

    monkeypatch.setattr(pdfsafe.subprocess, "Popen", fake_popen)
    with pytest.raises(Boom):
        pdfsafe.run_op("docling", [], 280, 32768, threads=4)
    assert seen["argv"][-3:-1] == ["32768", str((4 + 2) * 285)]
    with pytest.raises(Boom):
        pdfsafe.run_op("count", [], 15)
    assert seen["argv"][-2] == "20"
