"""marcus.api.chempool: RDKit work in a separate process, bounded in waiting and time."""

import asyncio
import time

import pytest
from fastapi import HTTPException

from marcus.api import chempool


async def test_runs_in_another_process_and_replaces_a_stuck_worker(monkeypatch):
    import os

    pool = chempool.ChemPool()
    try:
        assert await pool.run(os.getpid) != os.getpid()
        monkeypatch.setattr(chempool, "TIMEOUT_S", 0.5)
        with pytest.raises(HTTPException) as info:
            await pool.run(time.sleep, 5)
        assert info.value.status_code == 503
        assert await pool.run(abs, -3) == 3  # a fresh worker
    finally:
        pool.reset()


async def test_too_many_waiting_calls_get_503(monkeypatch):
    monkeypatch.setattr(chempool, "MAX_WAITING", 2)
    pool = chempool.ChemPool()
    try:
        first = [asyncio.ensure_future(pool.run(time.sleep, 0.5)) for _ in range(2)]
        await asyncio.sleep(0)
        with pytest.raises(HTTPException) as info:
            await pool.run(abs, 1)
        assert info.value.status_code == 503
        await asyncio.gather(*first)
        assert await pool.run(abs, -1) == 1
    finally:
        pool.reset()
