"""`POST /tools/{depict,smiles-to-molfile,mcs,compare}`: short synchronous jobs on q.tools.

Each call sends a Celery task to the tools queue and waits for its result (hard limit 10 s).
Timeout -> 504; the task's ToolInputError -> 422; any other task error -> generic 500.
"""

from typing import Annotated, Literal

from celery.exceptions import TimeoutError as CeleryTimeout
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StringConstraints

from marcus.api.deps import current_owner
from marcus.core.celery_app import TOOLS_QUEUE, celery_app
from marcus.core.models import Owner
from marcus.workers.tools import ToolInputError

router = APIRouter(prefix="/tools", tags=["tools"])

WAIT_S = 10
MAX_SMILES = 2000
MAX_MOLFILES = 20
MAX_MOLFILE_BYTES = 200_000

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


class CompareIn(BaseModel):
    smiles_a: Smiles
    smiles_b: Smiles


def _send_and_wait(name: str, kwargs: dict, timeout: float):
    result = celery_app.send_task(name, kwargs=kwargs, queue=TOOLS_QUEUE)
    return result.get(timeout=timeout)


def run_tool(name: str, kwargs: dict, timeout: float = WAIT_S):
    """Blocking: run a tools-queue task and map failures to HTTP errors."""
    try:
        return _send_and_wait(name, kwargs, timeout)
    except CeleryTimeout:
        raise HTTPException(status_code=504, detail="tool timed out") from None
    except ToolInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=500, detail="tool failed") from None


@router.post("/depict")
async def depict(body: DepictIn, _owner: Owner = Depends(current_owner)):
    kwargs = {
        "smiles": body.smiles,
        "fmt": body.format,
        "width": body.width,
        "height": body.height,
        "highlight": body.highlight,
    }
    data = await run_in_threadpool(run_tool, "marcus.tools.depict", kwargs, WAIT_S)
    return {"format": body.format, "data": data}


@router.post("/smiles-to-molfile")
async def smiles_to_molfile(body: SmilesIn, _owner: Owner = Depends(current_owner)):
    data = await run_in_threadpool(
        run_tool, "marcus.tools.smiles_to_molfile", {"smiles": body.smiles}, WAIT_S
    )
    return {"molfile": data}


@router.post("/mcs")
async def mcs(body: McsIn, _owner: Owner = Depends(current_owner)):
    return await run_in_threadpool(
        run_tool, "marcus.tools.mcs", {"molfiles": body.molfiles}, WAIT_S
    )


@router.post("/compare")
async def compare(body: CompareIn, _owner: Owner = Depends(current_owner)):
    kwargs = {"smiles_a": body.smiles_a, "smiles_b": body.smiles_b}
    return await run_in_threadpool(run_tool, "marcus.tools.compare", kwargs, WAIT_S)
