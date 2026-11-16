"""Read-only access to docker logs and nvidia-smi, local or on jarvis over SSH.

Safety rules for jarvis (production runs on the same machine and GPU):
  * only a fixed list of read-only commands can be sent (see ``_ALLOWED``);
  * only containers named ``marcus-judge-*`` or ``marcus-backend`` are named;
  * nothing is ever started, stopped, restarted or changed.

``ssh_ro`` refuses every other command with a ``ValueError``.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field

SSH_HOST = os.environ.get("JUDGE_SSH_HOST", "kohulan@jarvis.ian.uni-jena.de")
LOCAL_CONTAINER = "marcus-judge-backend"
REMOTE_JUDGE_CONTAINER = "marcus-judge-backend"
PROD_CONTAINER = "marcus-backend"  # read-only health / log look only

_C = r"(marcus-backend|marcus-judge-[a-z]+)"
_TS = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(Z|[+-][0-9:]+)?"
_ALLOWED = [
    re.compile(r"^nvidia-smi --query-gpu=[a-z._,]+ --format=csv,noheader(,nounits)?$"),
    re.compile(r"^nvidia-smi --query-compute-apps=[a-z._,]+ --format=csv,noheader(,nounits)?$"),
    re.compile(r"^docker inspect -f '\{\{\.State\.Health\.Status\}\}' " + _C + r"$"),
    re.compile(r"^docker inspect -f '\{\{\.State\.Status\}\}' " + _C + r"$"),
    re.compile(r"^docker logs( (--since " + _TS + r"|--until " + _TS + r"|-t|--tail [0-9]+))* " + _C + r"$"),
]


def _ssh_base() -> list[str]:
    ctl_dir = os.environ.get("JUDGE_SSH_CTL_DIR") or os.path.join(tempfile.gettempdir(), "marcus-judge-ssh")
    os.makedirs(ctl_dir, exist_ok=True)
    return [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "ControlMaster=auto", "-o", f"ControlPath={ctl_dir}/cm-%C", "-o", "ControlPersist=300",
        SSH_HOST,
    ]


def is_allowed(cmd: str) -> bool:
    return any(p.match(cmd) for p in _ALLOWED)


def ssh_ro(cmd: str, timeout: float = 25.0) -> str:
    """Run one whitelisted read-only command on jarvis; return stdout (stderr merged in)."""
    if not is_allowed(cmd):
        raise ValueError(f"command not on the read-only whitelist: {cmd!r}")
    p = subprocess.run(_ssh_base() + [cmd], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"ssh command failed ({p.returncode}): {cmd!r}: {p.stderr.strip()[:300]}")
    return p.stdout + p.stderr


def local_run(argv: list[str], timeout: float = 25.0) -> str:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {argv!r}: {p.stderr.strip()[:300]}")
    return p.stdout + p.stderr


# ---------------------------------------------------------------- docker logs

_TS_RE = re.compile(r"^(?P<ts>" + _TS + r") ?(?P<rest>.*)$")


@dataclass
class DockerLogs:
    """Backend container logs, either local docker or jarvis over SSH (read-only).

    ``mark()`` returns the timestamp of the last log line (the container's own clock, so no
    clock skew with this machine); ``since(mark)`` returns the lines written after it.
    """

    container: str = LOCAL_CONTAINER
    remote: bool = False
    _warned: list = field(default_factory=list)

    def _logs(self, *flags: str) -> str:
        if self.remote:
            return ssh_ro("docker logs " + " ".join(flags + (self.container,)))
        return local_run(["docker", "logs", *flags, self.container])

    def mark(self) -> str | None:
        try:
            out = self._logs("-t", "--tail", "1")
        except Exception as e:  # logs are optional; never break a run because of them
            self._warned.append(str(e))
            return None
        for line in reversed(out.splitlines()):
            m = _TS_RE.match(line)
            if m:
                return m.group("ts")
        return ""  # empty log: everything after is new

    def since(self, mark: str | None) -> list[str] | None:
        if mark is None:
            return None
        try:
            flags = ("-t",) if not mark else ("--since", mark, "-t")
            out = self._logs(*flags)
        except Exception as e:
            self._warned.append(str(e))
            return None
        lines = []
        for line in out.splitlines():
            m = _TS_RE.match(line)
            if m:
                if mark and m.group("ts") <= mark:  # RFC3339 strings of equal precision sort in time order
                    continue
                lines.append(m.group("rest"))
            else:
                lines.append(line)
        return lines


# glibc / JVM / TensorFlow native crash lines seen when the backend process dies or wedges (heap corruption)
CRASH_MARKERS = ("A fatal error has been detected", "SIGSEGV", "corrupted size vs. prev_size", "malloc(): ",
                 "free(): invalid", "munmap_chunk()", "malloc_consolidate()", "double free")
_PAGE_ERR = re.compile(r"^Error processing page (\d+):\s*(.*)$")
_TOOK = re.compile(r"^get_segments_with_bbox took ([0-9.]+) seconds")
_LAYER_TYPE = re.compile(r"\(type (\w+)\)")


def parse_server_log(lines: list[str] | None) -> dict:
    """Pull page errors and segmentation timing out of backend log lines.

    The backend only ``print``s page errors (the API hides them), one block per failed page:
    ``Error processing page <0-based page>: <first line of the exception>`` followed by detail.
    A page that exceeds the 30 s per-page limit prints the same line with an empty message.
    """
    out = {"page_errors": [], "server_segment_s": [], "keyword_counts": {}, "backend_crash": False}
    if lines is None:
        return out
    seen = set()
    for i, line in enumerate(lines):
        m = _PAGE_ERR.match(line)
        if m:
            page, msg = int(m.group(1)), m.group(2).strip()
            # the exception text continues on the next lines; use them to find the layer type
            tail = " ".join(lines[i : i + 4])
            lt = _LAYER_TYPE.search(msg) or _LAYER_TYPE.search(tail)
            err = msg or "(empty message; per-page 30 s timeout)"
            key = (page, err)
            if key in seen:  # the wrapper logs some failures twice (inner + outer handler)
                continue
            seen.add(key)
            out["page_errors"].append({"page": page, "error": err[:300], "layer_type": lt.group(1) if lt else None,
                                       # timeout: the 30 s wait in the main thread expired; the worker still finishes
                                       # and writes its segment files, so the page is NOT lost (CPU-only effect)
                                       "kind": "timeout_30s" if not msg else "exception"})
            continue
        t = _TOOK.match(line)
        if t:
            out["server_segment_s"].append(float(t.group(1)))
    text = "\n".join(lines)
    for kw in ("PyramidROIAlign", "DetectionLayer", "ProposalLayer", "Lambda", "OOM", "out of memory", "Rate limit exceeded",
               *CRASH_MARKERS):
        n = text.count(kw)
        if n:
            out["keyword_counts"][kw] = n
    out["backend_crash"] = any(k in out["keyword_counts"] for k in CRASH_MARKERS)
    return out


# ---------------------------------------------------------------- GPU

def gpu_stats(remote: bool) -> dict:
    """GPU 0: free/used/total MiB and utilisation percent (the GPU is shared with production on jarvis)."""
    q = "nvidia-smi --query-gpu=memory.free,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits"
    out = ssh_ro(q) if remote else local_run(shlex.split(q))
    free, used, total, util = (int(float(x)) for x in out.strip().splitlines()[0].split(","))
    return {"gpu_free_mib": free, "gpu_used_mib": used, "gpu_total_mib": total, "gpu_util_pct": util}


def gpu_free_mib(remote: bool) -> tuple[int, int, int]:
    """(free MiB, used MiB, total MiB) of GPU 0."""
    q = "nvidia-smi --query-gpu=memory.free,memory.used,memory.total --format=csv,noheader,nounits"
    out = ssh_ro(q) if remote else local_run(shlex.split(q))
    first = out.strip().splitlines()[0]
    free, used, total = (int(float(x)) for x in first.split(","))
    return free, used, total
