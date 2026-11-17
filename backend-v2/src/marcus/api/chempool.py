"""RDKit work for requests, in a separate process (one per API process).

RDKit holds the GIL while it parses (measured: a 0.65 s SMILES parse in a thread let the event
loop run once), so neither the event loop nor a thread pool may run it: a slow molecule would
stall every request, upload and SSE stream of that API process. CHEM.run(fn, *args) runs a
picklable module-level function in a spawned worker process and waits without blocking the
loop. Bounds: at most MAX_WAITING calls wait per API process (more get 503), each waits at most
TIMEOUT_S (then 503, and the worker is killed and replaced on the next call).
"""

import asyncio
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from fastapi import HTTPException

log = logging.getLogger(__name__)

WORKERS = 1
MAX_WAITING = 8
TIMEOUT_S = 15.0


class ChemPool:
    def __init__(self) -> None:
        self._pool: ProcessPoolExecutor | None = None
        self._waiting = 0

    def _executor(self) -> ProcessPoolExecutor:
        if self._pool is None:
            # spawn: never fork a process that runs an event loop, threads and DB connections
            ctx = multiprocessing.get_context("spawn")
            self._pool = ProcessPoolExecutor(max_workers=WORKERS, mp_context=ctx)
        return self._pool

    def reset(self) -> None:
        """Kill the worker process(es) and start fresh on the next call."""
        pool, self._pool = self._pool, None
        if pool is None:
            return
        for proc in list((getattr(pool, "_processes", None) or {}).values()):
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        pool.shutdown(wait=False, cancel_futures=True)

    async def run(self, fn, *args):
        if self._waiting >= MAX_WAITING:
            raise HTTPException(status_code=503, detail="busy, try again")
        self._waiting += 1
        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(self._executor(), fn, *args)
            return await asyncio.wait_for(future, TIMEOUT_S)
        except (TimeoutError, BrokenProcessPool) as exc:
            log.warning("chem worker %s; replacing it", type(exc).__name__)
            self.reset()
            raise HTTPException(status_code=503, detail="busy, try again") from None
        finally:
            self._waiting -= 1


CHEM = ChemPool()
