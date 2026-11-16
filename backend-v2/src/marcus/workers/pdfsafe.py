"""Run untrusted-PDF work in a throw-away child process.

PyMuPDF (MuPDF is C code) parses user-supplied files, so a crafted PDF can hang or eat memory.
Every call here runs in a `spawn`ed child with an address-space limit (RLIMIT_AS) and a wall
clock timeout; on timeout the child is terminated, then killed. Results and errors come back
over a pipe as plain data (never a pickled exception object).

This module imports only the standard library at top level so the child starts fast;
`marcus.workers.runtime` (celery, sqlalchemy) is imported lazily on the parent side.
"""

import multiprocessing
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_MEM_MB = 2048


class ChildTimeout(Exception):
    """The child did not answer within the timeout and was killed."""


class ChildFailed(Exception):
    """The child raised or died. Only a short message travels back, never an exception object."""


def _child_main(conn, fn: Callable, args: tuple, mem_mb: int | None) -> None:
    try:
        if mem_mb:
            import resource

            limit = mem_mb * 2**20
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        conn.send(("ok", fn(*args)))
    except MemoryError:
        conn.send(("err", "out of memory"))
    except BaseException as exc:  # noqa: BLE001 - everything becomes a message
        conn.send(("err", f"{type(exc).__name__}: {str(exc)[:200]}"))
    finally:
        conn.close()


def run_isolated(
    fn: Callable, args: tuple, timeout_s: float, mem_mb: int | None = DEFAULT_MEM_MB
) -> Any:
    """Call `fn(*args)` in a spawned child. `fn` must be a picklable module-level function and
    return picklable plain data. Raises ChildTimeout or ChildFailed."""
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_main, args=(child_conn, fn, args, mem_mb), daemon=True)
    proc.start()
    child_conn.close()
    try:
        if not parent_conn.poll(timeout_s):
            raise ChildTimeout()
        try:
            status, payload = parent_conn.recv()
        except (EOFError, OSError) as exc:
            raise ChildFailed(f"child exited with code {proc.exitcode}") from exc
        if status == "ok":
            return payload
        raise ChildFailed(str(payload))
    finally:
        parent_conn.close()
        if proc.is_alive():
            proc.terminate()
            proc.join(2)
            if proc.is_alive():
                proc.kill()
        proc.join(5)


def _open_checked(path: str, max_pages: int):
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ValueError("not a readable PDF") from exc
    if doc.needs_pass or doc.is_encrypted:
        raise ValueError("encrypted PDF")
    if not doc.is_pdf:
        raise ValueError("not a PDF")
    n = doc.page_count
    if n < 1:
        raise ValueError("PDF has no pages")
    if n > max_pages:
        raise ValueError(f"PDF has more than {max_pages} pages")
    return doc


def _count(path: str, max_pages: int) -> int:
    doc = _open_checked(path, max_pages)
    try:
        return doc.page_count
    finally:
        doc.close()


def _render(path: str, page: int, out: str, max_pages: int) -> None:
    import pymupdf

    doc = _open_checked(path, max_pages)
    try:
        if not 0 <= page < doc.page_count:
            raise ValueError("page out of range")
        zoom = 300 / 72
        pix = doc[page].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pix.save(out)
    finally:
        doc.close()


def _run_pdf(fn: Callable, args: tuple, timeout_s: float, mem_mb: int):
    from marcus.workers.runtime import BadInput

    try:
        return run_isolated(fn, args, timeout_s, mem_mb)
    except ChildTimeout:
        raise BadInput("timeout") from None
    except ChildFailed as exc:
        raise BadInput(str(exc)[:200]) from None


def page_count(path: Path, timeout_s: int, mem_mb: int = DEFAULT_MEM_MB) -> int:
    from marcus.core.settings import get_settings

    return _run_pdf(_count, (str(path), get_settings().max_pages), timeout_s, mem_mb)


def render_page_png(
    path: Path, page: int, out: Path, timeout_s: int, mem_mb: int = DEFAULT_MEM_MB
) -> None:
    """Render one page at 300 DPI to `out`; a killed render never leaves a half PNG."""
    from marcus.core.settings import get_settings

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex}.tmp.png")
    try:
        _run_pdf(_render, (str(path), page, str(tmp), get_settings().max_pages), timeout_s, mem_mb)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
