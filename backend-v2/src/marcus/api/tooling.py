"""Short synchronous jobs on q.tools, shared by the /tools routes and the depiction route.

Each call sends a Celery task to the tools queue and waits for its result (hard limit WAIT_S).
Timeout -> 504; envelope {ok: false, error} (bad input) -> 422; any other task error -> 500.
The task expires with the wait, so a call the API gave up on never runs later. Waits use their
own thread budget (MAX_TOOL_WAITS per API process, not the default pool that file responses and
exports use); when it is full the call gets 503 at once, with Retry-After.

Stored depictions (marcus.api.depiction) draw on the same budget but only through their own
share of it (`depiction_slot`, MAX_DEPICTION_WAITS per API process): a 200-structure first view
can never hold more than that, so /tools/* keeps MAX_TOOL_WAITS - MAX_DEPICTION_WAITS slots.
The share also bounds how many depict tasks one API process puts ahead of an interactive call
in q.tools (each task expires with its wait, so none pile up behind a refused request).
"""

import contextlib

import anyio
from celery.exceptions import TimeoutError as CeleryTimeout
from fastapi import HTTPException

from marcus.core.celery_app import TOOLS_QUEUE, celery_app

WAIT_S = 10
MAX_SMILES = 2000
MAX_TOOL_WAITS = 16  # tool calls waiting at once per API process (2 tool processes serve them)
MAX_DEPICTION_WAITS = 4  # of those, at most this many stored-depiction draws
TOOLS_BUSY = "tools busy, try again"
RETRY_AFTER_S = 5

_tool_waits: anyio.CapacityLimiter | None = None
_depiction_waits: anyio.CapacityLimiter | None = None


def _waits() -> anyio.CapacityLimiter:
    global _tool_waits
    if _tool_waits is None:
        _tool_waits = anyio.CapacityLimiter(MAX_TOOL_WAITS)
    return _tool_waits


def _depiction_share() -> anyio.CapacityLimiter:
    global _depiction_waits
    if _depiction_waits is None:
        _depiction_waits = anyio.CapacityLimiter(MAX_DEPICTION_WAITS)
    return _depiction_waits


def tools_busy() -> HTTPException:
    return HTTPException(
        status_code=503, detail=TOOLS_BUSY, headers={"Retry-After": str(RETRY_AFTER_S)}
    )


@contextlib.contextmanager
def depiction_slot():
    """Hold one of the depictions' MAX_DEPICTION_WAITS slots for the block; 503 (tools_busy)
    at once when all are held. The tool call inside still needs a slot of the tools budget."""
    share = _depiction_share()
    try:
        share.acquire_nowait()
    except anyio.WouldBlock:
        raise tools_busy() from None
    try:
        yield
    finally:
        share.release()


def _send_and_wait(name: str, kwargs: dict, timeout: float):
    # expires: a task still queued when the caller has given up is dropped, not run late
    result = celery_app.send_task(name, kwargs=kwargs, queue=TOOLS_QUEUE, expires=timeout)
    try:
        return result.get(timeout=timeout)
    finally:  # a 504 must not leave a result subscription behind for the API's lifetime
        _release(result)


def _release(result) -> None:
    """Best effort: drop the stored result and the result consumer's subscription."""
    with contextlib.suppress(Exception):
        result.forget()
    cancel = getattr(getattr(celery_app.backend, "result_consumer", None), "cancel_for", None)
    if cancel is not None:
        with contextlib.suppress(Exception):
            cancel(result.id)


def run_tool(name: str, kwargs: dict, timeout: float = WAIT_S):
    """Blocking: run a tools-queue task and map failures to HTTP errors."""
    try:
        envelope = _send_and_wait(name, kwargs, timeout)
    except CeleryTimeout:
        raise HTTPException(status_code=504, detail="tool timed out") from None
    except Exception:
        raise HTTPException(status_code=500, detail="tool failed") from None
    if not isinstance(envelope, dict) or "ok" not in envelope:
        raise HTTPException(status_code=500, detail="tool failed")
    if not envelope["ok"]:
        raise HTTPException(status_code=422, detail=str(envelope.get("error", "bad input")))
    return envelope["result"]


async def in_tool_budget(fn, *args):
    """`fn(*args)` (a blocking tool wait) in a thread of the tools' own budget; 503 at once when
    the budget is used up."""
    limiter = _waits()
    if limiter.available_tokens < 1:
        raise tools_busy()
    return await anyio.to_thread.run_sync(fn, *args, limiter=limiter)


async def call_tool(name: str, kwargs: dict):
    """run_tool in the tools' thread budget (see in_tool_budget)."""
    return await in_tool_budget(run_tool, name, kwargs, WAIT_S)
