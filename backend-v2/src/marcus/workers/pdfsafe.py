"""Run untrusted-PDF work in a throw-away child process.

PyMuPDF (C code), docling and pdf2doi all parse user-supplied files, so a crafted PDF can hang
or eat memory. Every call here runs `python -I -m marcus.workers.pdfsafe_child OP` as a
subprocess (a plain subprocess, not multiprocessing: Celery prefork workers are daemonic and
may not start multiprocessing children) in its own session with RLIMIT_AS and RLIMIT_CPU, a
minimal environment, JSON over stdin/stdout and a capped reply. On timeout the whole process
group gets TERM, then KILL. Nothing is pickled.

Top-level imports are standard library only; `marcus.workers.runtime` is imported lazily.
"""

import json
import logging
import os
import selectors
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_MEM_MB = 2048
DOCLING_THREADS = 4  # defined once; passed to the child as an op argument
CPU_HEADROOM_THREADS = 2  # RLIMIT_CPU = (threads + 2) x (timeout + 5): stray pools never trip it
# docling imports torch, which maps ~24 GiB of address space (thread stacks, CUDA libs): measured
# segfault at 8 GiB, "resource unavailable" at 16 GiB, success at 24 GiB. RLIMIT_AS is a
# virtual limit, so 32 GiB still caps a runaway parse.
DOCLING_MEM_MB = 32768
MAX_REPLY_BYTES = 1024 * 1024
_ENV_KEEP = ("PATH", "HOME", "LANG", "PYTHONHASHSEED", "HF_HOME", "TORCH_HOME",
             "XDG_CACHE_HOME", "DOCLING_ARTIFACTS_PATH", "OMP_NUM_THREADS")


class ChildTimeout(Exception):
    """The child did not answer within the timeout and was killed."""


class ChildFailed(Exception):
    """The child raised or died. Only a short message travels back."""


def _child_env(threads: int | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.setdefault("PYTHONHASHSEED", "0")
    if threads:
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            env[name] = str(threads)
        env["TOKENIZERS_PARALLELISM"] = "false"
    return env


def _kill_group(proc: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 1.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        try:
            proc.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # stragglers in the group
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log.error("pdf child %s did not exit after SIGKILL", proc.pid)


def run_op(
    op: str,
    args: list,
    timeout_s: float,
    mem_mb: int | None = DEFAULT_MEM_MB,
    threads: int | None = None,
) -> Any:
    """Run a child op with JSON-able args; return its JSON result. Raises ChildTimeout or
    ChildFailed. The child applies RLIMIT_AS (mem_mb) and RLIMIT_CPU itself before touching the
    input. RLIMIT_CPU counts CPU seconds over all threads, so a multi-threaded op passes
    `threads`: the thread env vars are pinned to it and the CPU limit is (threads+2) x (timeout+5)."""
    cpu_s = (threads + CPU_HEADROOM_THREADS if threads else 1) * (int(timeout_s) + 5)
    proc = subprocess.Popen(
        [
            sys.executable, "-I", "-m", "marcus.workers.pdfsafe_child", op,
            str(mem_mb or 0), str(cpu_s), str(os.getpid()),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_child_env(threads),
        start_new_session=True,
    )
    try:
        try:
            proc.stdin.write(json.dumps({"args": args}).encode())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        data = _read_capped(proc, time.monotonic() + timeout_s)
        try:
            proc.wait(timeout=5)  # the reply is complete; a slow exit is cleaned up below
        except subprocess.TimeoutExpired:
            pass
    except ChildTimeout:
        raise ChildTimeout() from None
    finally:
        _kill_group(proc)
    try:
        reply = json.loads(data)
    except ValueError:
        raise ChildFailed(f"child exited with code {proc.returncode}") from None
    if reply.get("ok"):
        return reply.get("result")
    raise ChildFailed(str(reply.get("error", "child failed"))[:200])


def _read_capped(proc: subprocess.Popen, deadline: float) -> bytes:
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    chunks: list[bytes] = []
    size = 0
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ChildTimeout()
            if not sel.select(left):
                raise ChildTimeout()
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                return b"".join(chunks)
            size += len(chunk)
            if size > MAX_REPLY_BYTES:
                raise ChildFailed("reply too large")
            chunks.append(chunk)
    finally:
        sel.close()


def _run_pdf(
    op: str, args: list, timeout_s: float, mem_mb: int | None, threads: int | None = None
):
    """run_op for a step: a wall-time kill is a retryable timeout (StepTimeout); a child that
    failed (parse error, RLIMIT_AS / RLIMIT_CPU kill, bad reply) is final bad input."""
    from marcus.workers.runtime import BadInput, StepTimeout

    try:
        return run_op(op, args, timeout_s, mem_mb, threads)
    except ChildTimeout:
        raise StepTimeout("timeout") from None
    except ChildFailed as exc:
        raise BadInput(str(exc)[:200]) from None


def page_count(path: Path, timeout_s: int, mem_mb: int = DEFAULT_MEM_MB) -> int:
    from marcus.core.settings import get_settings

    return _run_pdf("count", [str(path), get_settings().max_pages], timeout_s, mem_mb)


def render_page_png(
    path: Path, page: int, out: Path, timeout_s: int, mem_mb: int = DEFAULT_MEM_MB
) -> None:
    """Render one page at 300 DPI to `out`; a killed render never leaves a half PNG."""
    from marcus.core.settings import get_settings

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex}.tmp.png")
    try:
        _run_pdf(
            "render", [str(path), page, str(tmp), get_settings().max_pages], timeout_s, mem_mb
        )
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def run_docling(path: Path, out_dir: Path, timeout_s: int, mem_mb: int = DOCLING_MEM_MB) -> None:
    """Convert in a child; it writes out_dir/text.json (temp + replace)."""
    _run_pdf("docling", [str(path), str(out_dir), DOCLING_THREADS], timeout_s, mem_mb, DOCLING_THREADS
    )
