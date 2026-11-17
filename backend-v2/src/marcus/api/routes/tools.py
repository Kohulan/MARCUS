"""`POST /tools/{depict,smiles-to-molfile,mcs,compare}`: short synchronous jobs on q.tools.

Each call sends a Celery task to the tools queue and waits for its result (hard limit 10 s).
Timeout -> 504; envelope {ok: false, error} (bad input) -> 422; any other task error -> 500.
The task expires with the wait, so a call the API gave up on never runs later. Waits use their
own thread budget (MAX_TOOL_WAITS per API process, not the default pool that file responses and
exports use); when it is full the call gets 503 at once.
"""

import contextlib
from typing import Annotated, Literal

import anyio
from celery.exceptions import TimeoutError as CeleryTimeout
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator

from marcus.api.deps import current_owner
from marcus.api.security import tools_limit
from marcus.core.celery_app import TOOLS_QUEUE, celery_app
from marcus.core.models import Owner

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(tools_limit)])

WAIT_S = 10
MAX_SMILES = 2000
MAX_MOLFILES = 20
MAX_MOLFILE_BYTES = 200_000
MAX_MCS_TOTAL = 1_000_000
MAX_TOOL_WAITS = 16  # tool calls waiting at once per API process (2 tool processes serve them)

_tool_waits: anyio.CapacityLimiter | None = None


def _waits() -> anyio.CapacityLimiter:
    global _tool_waits
    if _tool_waits is None:
        _tool_waits = anyio.CapacityLimiter(MAX_TOOL_WAITS)
    return _tool_waits


Smiles = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SMILES)]
Molfile = Annotated[str, StringConstraints(min_length=1, max_length=MAX_MOLFILE_BYTES)]


class DepictIn(BaseModel):
    smiles: Smiles
    format: Literal["svg", "png"] = "svg"
    width: int = Field(512, ge=50, le=2000)
    height: int = Field(512, ge=50, le=2000)
    highlight: str = Field("", max_length=MAX_SMILES)


class SmilesIn(BaseModel):
    smiles: Smiles


class McsIn(BaseModel):
    molfiles: list[Molfile] = Field(min_length=2, max_length=MAX_MOLFILES)

    @model_validator(mode="after")
    def _total_size(self):
        if sum(len(m) for m in self.molfiles) > MAX_MCS_TOTAL:
            raise ValueError("molfiles too large in total")
        return self


class CompareIn(BaseModel):
    smiles_a: Smiles
    smiles_b: Smiles


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


async def call_tool(name: str, kwargs: dict):
    """run_tool in a thread of the tools' own budget; 503 at once when it is used up."""
    limiter = _waits()
    if limiter.available_tokens < 1:
        raise HTTPException(status_code=503, detail="tools busy, try again")
    return await anyio.to_thread.run_sync(run_tool, name, kwargs, WAIT_S, limiter=limiter)


@router.post("/depict")
async def depict(body: DepictIn, _owner: Owner = Depends(current_owner)):
    kwargs = {
        "smiles": body.smiles,
        "fmt": body.format,
        "width": body.width,
        "height": body.height,
        "highlight": body.highlight,
    }
    data = await call_tool("marcus.tools.depict", kwargs)
    return {"format": body.format, "data": data}


@router.post("/smiles-to-molfile")
async def smiles_to_molfile(body: SmilesIn, _owner: Owner = Depends(current_owner)):
    data = await call_tool("marcus.tools.smiles_to_molfile", {"smiles": body.smiles})
    return {"molfile": data}


@router.post("/mcs")
async def mcs(body: McsIn, _owner: Owner = Depends(current_owner)):
    return await call_tool("marcus.tools.mcs", {"molfiles": body.molfiles})


@router.post("/compare")
async def compare(body: CompareIn, _owner: Owner = Depends(current_owner)):
    kwargs = {"smiles_a": body.smiles_a, "smiles_b": body.smiles_b}
    return await call_tool("marcus.tools.compare", kwargs)
