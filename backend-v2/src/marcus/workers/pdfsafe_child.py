"""Child-process entry for untrusted-PDF work: `python -I -m marcus.workers.pdfsafe_child OP`.

Reads one JSON request ({"args": [...]}) on stdin, writes one JSON reply on stdout:
{"ok": true, "result": ...} or {"ok": false, "error": "short message"}. Stray library output is
redirected to stderr so it can never corrupt the reply. Standard library only at import time;
heavy packages (pymupdf, docling, pdf2doi) are imported inside the ops.
"""

import json
import os
import sys
import uuid
from pathlib import Path


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


def op_count(path: str, max_pages: int) -> int:
    doc = _open_checked(path, max_pages)
    try:
        return doc.page_count
    finally:
        doc.close()


def op_render(path: str, page: int, out: str, max_pages: int) -> None:
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


def op_docling(path: str, out_dir: str, threads: int) -> dict:
    """Same call chain as v1: convert, then export_to_dict(); write text.json atomically.
    Every thread pool is pinned to `threads` (the parent scales RLIMIT_CPU by it)."""
    import torch

    torch.set_num_interop_threads(1)  # must run before any torch work
    torch.set_num_threads(threads)
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(num_threads=threads, device="cpu")
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    doc = converter.convert(path).document.export_to_dict()
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / f".text.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        os.replace(tmp, target / "text.json")
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True}


def op_doi(path: str, call_timeout_s: float) -> str | None:
    """pdf2doi online lookup. pdf2doi calls requests with no timeout, so every requests call
    gets one here; the socket default covers urllib. Web search is off: PDF text is never
    sent to a search engine."""
    import socket

    import requests

    socket.setdefaulttimeout(call_timeout_s)
    original = requests.sessions.Session.request

    def request_with_timeout(self, method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = call_timeout_s
        return original(self, method, url, **kwargs)

    requests.sessions.Session.request = request_with_timeout

    import pdf2doi

    pdf2doi.config.set("verbose", False)
    pdf2doi.config.set("save_identifier_metadata", False)  # never write into the user's PDF
    pdf2doi.config.set("websearch", False)
    result = pdf2doi.pdf2doi(path)
    if isinstance(result, dict):
        return result.get("identifier")
    return None


def op_sleep(*args) -> None:  # diagnostic: lets tests exercise the timeout kill
    import time

    time.sleep(60)


def op_spin(*args) -> None:  # diagnostic
    while True:
        pass


def op_alloc(mb: int) -> int:  # diagnostic: lets tests exercise RLIMIT_AS
    return len(bytearray(mb * 2**20))


def op_fail(*args) -> None:  # diagnostic
    raise RuntimeError("boom")


def op_sigkill(*args) -> None:  # diagnostic: what the container's OOM killer does
    import signal

    os.kill(os.getpid(), signal.SIGKILL)


OPS = {
    "count": op_count,
    "render": op_render,
    "docling": op_docling,
    "doi": op_doi,
    "_sleep": op_sleep,
    "_alloc": op_alloc,
    "_spin": op_spin,
    "_fail": op_fail,
    "_sigkill": op_sigkill,
}


def _harden(mem_mb: int, cpu_s: int, parent_pid: int) -> None:
    """First thing in the child: die with the parent, then apply the resource limits."""
    if sys.platform == "linux":
        import ctypes
        import signal

        if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL) != 0:  # PR_SET_PDEATHSIG
            raise OSError("prctl(PR_SET_PDEATHSIG) failed")
        if os.getppid() != parent_pid:  # the parent died before the prctl took effect
            os._exit(1)
    import resource

    if mem_mb:
        limit = mem_mb * 2**20
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 2))


def main(argv: list[str]) -> int:
    """argv: [prog, OP, MEM_MB, CPU_S, PARENT_PID]. Limits are applied before anything is read or parsed."""
    reply_fd = os.dup(1)
    os.dup2(2, 1)  # stray prints go to stderr
    try:
        _harden(int(argv[2]), int(argv[3]), int(argv[4]))
        op = OPS[argv[1]]
        args = json.loads(sys.stdin.read())["args"]
        reply = {"ok": True, "result": op(*args)}
    except MemoryError:
        reply = {"ok": False, "error": "out of memory"}
    except BaseException as exc:  # noqa: BLE001 - everything becomes a short message
        reply = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    with os.fdopen(reply_fd, "w") as out:
        out.write(json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
