"""Safety guard for load tests against the JARVIS copy (shares the V100 with production).

Before a scenario and every 30 s during it the guard checks, read-only over SSH:

  1. production health:  docker inspect -f '{{.State.Health.Status}}' marcus-backend   == healthy
  2. free GPU memory:    nvidia-smi --query-gpu=memory.free ...                         >= 3 GiB

If either fails (or the check itself cannot run: fail closed) the guard trips at once: it sets
``guard.abort`` (an Event the scenarios and client_v1/client_v2.run_paper watch), closes every open HTTP client
of client_v1 and client_v2, deletes every live v2 paper as its owner (client_v2.cancel_papers: on v2 the pipeline
runs on the server), runs the scenario's ``on_trip`` hooks (v2: abandon image jobs) and writes the reason to ``load/results/guard_events.jsonl``. Scenarios must stop sending
work and record ``guard.tripped`` in their result.

Production-stopped mode (``prod_expected="stopped"``, scenarios.py ``--prod-stopped``) is ONLY for the owner's GPU test
window, when ``marcus-backend`` was stopped on purpose (Task D4): check 1 becomes
``docker inspect -f '{{.State.Status}}' marcus-backend`` in (exited, created), i.e. production must stay stopped, so
nothing of ours shares the GPU with it; a production that runs again trips the guard. Check 2 and the ledger are the
same in both modes.

It also keeps a ledger of GPU test time (``load/results/gpu_time_ledger.json``); a new guard on jarvis
refuses to start when the ledger is over the budget (default 45 min, env JUDGE_GPU_BUDGET_S).

The guard never starts, stops, restarts or changes a container. Only the commands whitelisted in
``common/remote.py`` can be sent. For a non-jarvis target the guard is a no-op that still provides
``abort`` and an events list, so scenario code is the same for both targets.

CLI:  uv run python load/guard_jarvis.py --check [--prod-stopped]   # one check against jarvis, prints JSON
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import client_v1, client_v2, remote  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
MIN_FREE_MIB = 3 * 1024
INTERVAL_S = 30.0
PROD = remote.PROD_CONTAINER
BUDGET_S = float(os.environ.get("JUDGE_GPU_BUDGET_S", 45 * 60))


class GuardTripped(RuntimeError):
    pass


def is_jarvis_url(url: str) -> bool:
    import httpx

    return httpx.URL(url).port == 29000


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


PROD_MODES = ("running", "stopped")
PROD_STOPPED_STATES = ("exited", "created")


def real_check(prod_expected: str = "running") -> dict:
    """One production + GPU check over SSH (read-only). Raises on ssh errors."""
    if prod_expected == "stopped":
        status = remote.ssh_ro(f"docker inspect -f '{{{{.State.Status}}}}' {PROD}").strip()
        return {"prod_status": status, **remote.gpu_stats(remote=True)}
    health = remote.ssh_ro(f"docker inspect -f '{{{{.State.Health.Status}}}}' {PROD}").strip()
    return {"prod_health": health, **remote.gpu_stats(remote=True)}


def evaluate(sample: dict, min_free_mib: int = MIN_FREE_MIB, prod_expected: str = "running") -> str | None:
    """Return a human reason if the sample violates the rules, else None."""
    if prod_expected == "stopped":
        if sample.get("prod_status") not in PROD_STOPPED_STATES:
            return (f"production container marcus-backend is {sample.get('prod_status')!r}; the GPU window mode "
                    f"(--prod-stopped) needs it stopped ({'/'.join(PROD_STOPPED_STATES)})")
    elif sample.get("prod_health") != "healthy":
        return f"production container marcus-backend health is {sample.get('prod_health')!r}, not 'healthy'"
    if sample.get("gpu_free_mib", 0) < min_free_mib:
        return f"free GPU memory {sample.get('gpu_free_mib')} MiB is below {min_free_mib} MiB"
    return None


class Guard:
    """Context manager. ``with Guard(base_url, "S2") as g:`` ... use ``g.abort`` and ``g.events``."""

    def __init__(self, base_url: str, scenario: str, *, interval_s: float = INTERVAL_S,
                 min_free_mib: int = MIN_FREE_MIB, checker=None, enabled: bool | None = None,
                 use_ledger: bool = True, prod_expected: str = "running", on_trip=None):
        if prod_expected not in PROD_MODES:
            raise ValueError(f"prod_expected must be one of {PROD_MODES}, not {prod_expected!r}")
        self.prod_expected = prod_expected
        self.on_trip = list(on_trip or [])  # extra stop actions (v2: abandon image jobs), run after the papers
        self.cancelled: dict | None = None
        self.base_url = base_url
        self.scenario = scenario
        self.interval_s = interval_s
        self.min_free_mib = min_free_mib
        self.enabled = is_jarvis_url(base_url) if enabled is None else enabled
        self.checker = checker or (lambda: real_check(prod_expected))  # injectable for tests
        self.use_ledger = use_ledger and self.enabled
        self.abort = threading.Event()
        self.events: list[dict] = []
        self.tripped_reason: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t_start = 0.0

    # ------------------------------------------------------------------ checks
    def check(self, when: str) -> bool:
        """Run one check. Returns True if ok. On failure trips the guard."""
        if not self.enabled:
            return True
        sample, err = None, None
        for attempt in (1, 2):  # one quick retry for an ssh hiccup; still fail closed afterwards
            try:
                sample = self.checker()
                err = None
                break
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                time.sleep(2.0)
        ev = {"t": _utc(), "scenario": self.scenario, "when": when}
        if sample is None:
            ev.update(ok=False, reason=f"guard check could not run: {err}")
        else:
            reason = evaluate(sample, self.min_free_mib, self.prod_expected)
            ev.update(sample)
            ev.update(ok=reason is None, reason=reason)
        self.events.append(ev)
        if not ev["ok"]:
            self._trip(ev["reason"])
            return False
        return True

    def _trip(self, reason: str):
        if self.tripped_reason is not None:
            return
        self.tripped_reason = reason
        self.abort.set()
        closed = client_v1.abort_all() + client_v2.abort_all()  # both builds' paper clients
        # v2 runs the pipeline on the server: closing clients does not free the GPU, deleting the papers does
        cancelled = {"papers": [], "hooks": []}
        try:
            cancelled["papers"] = client_v2.cancel_papers()
        except Exception as e:
            cancelled["papers_error"] = f"{type(e).__name__}: {e}"
        for hook in self.on_trip:
            try:
                cancelled["hooks"].append(hook())
            except Exception as e:
                cancelled["hooks"].append({"error": f"{type(e).__name__}: {e}"})
        self.cancelled = cancelled
        RESULTS.mkdir(exist_ok=True)
        with open(RESULTS / "guard_events.jsonl", "a") as f:
            f.write(json.dumps({"t": _utc(), "scenario": self.scenario, "event": "TRIPPED", "reason": reason,
                                "http_clients_closed": closed, "cancelled": cancelled}) + "\n")
        print(f"[guard] TRIPPED during {self.scenario}: {reason} (closed {closed} http clients)", file=sys.stderr, flush=True)

    @property
    def tripped(self) -> bool:
        return self.tripped_reason is not None

    # ------------------------------------------------------------------ context manager
    def _loop(self):
        while not self._stop.wait(self.interval_s):
            if not self.check("during"):
                return

    def __enter__(self) -> "Guard":
        if self.use_ledger:
            used = ledger_total()
            if used >= BUDGET_S:
                raise GuardTripped(f"GPU test-time budget used up ({used:.0f} s >= {BUDGET_S:.0f} s); "
                                   "raise JUDGE_GPU_BUDGET_S only with the owner's agreement")
        if not self.check("before"):
            raise GuardTripped(self.tripped_reason)
        self._t_start = time.time()
        if self.enabled:
            self._thread = threading.Thread(target=self._loop, name=f"guard-{self.scenario}", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=60)
        if self.enabled:
            self.check("after")
        if self.use_ledger:
            ledger_add(self.scenario, time.time() - self._t_start)
        return False

    def summary(self) -> dict:
        free = [e["gpu_free_mib"] for e in self.events if "gpu_free_mib" in e]
        return {
            "enabled": self.enabled, "prod_expected": self.prod_expected, "checks": len(self.events),
            "cancelled": self.cancelled, "tripped": self.tripped,
            "trip_reason": self.tripped_reason, "min_gpu_free_mib": min(free) if free else None,
            "max_gpu_used_mib": max((e["gpu_used_mib"] for e in self.events if "gpu_used_mib" in e), default=None),
            "events": self.events,
        }


# ---------------------------------------------------------------------- GPU time ledger
_LEDGER = RESULTS / "gpu_time_ledger.json"
_ledger_lock = threading.Lock()


def ledger_total() -> float:
    try:
        return float(json.loads(_LEDGER.read_text()).get("total_s", 0.0))
    except Exception:
        return 0.0


def ledger_add(name: str, seconds: float):
    with _ledger_lock:
        RESULTS.mkdir(exist_ok=True)
        try:
            d = json.loads(_LEDGER.read_text())
        except Exception:
            d = {"total_s": 0.0, "entries": []}
        d["total_s"] = round(d["total_s"] + seconds, 1)
        d["entries"].append({"t": _utc(), "scenario": name, "seconds": round(seconds, 1)})
        _LEDGER.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="run one check against jarvis and print it")
    ap.add_argument("--prod-stopped", action="store_true", help="GPU window mode: production must be stopped")
    a = ap.parse_args()
    if a.check:
        mode = "stopped" if a.prod_stopped else "running"
        s = real_check(mode)
        s["violation"] = evaluate(s, prod_expected=mode)
        s["gpu_time_used_s"] = ledger_total()
        print(json.dumps(s, indent=1))
    else:
        ap.print_help()
