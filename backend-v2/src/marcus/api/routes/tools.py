"""`POST /tools/{depict,smiles-to-molfile,mcs,compare}`: short synchronous jobs on q.tools.

The calls go through marcus.api.tooling (wait limit, error mapping, task expiry and the tools'
own thread budget; see its docstring).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints, model_validator

from marcus.api.deps import current_owner
from marcus.api.security import tools_limit
from marcus.api.tooling import MAX_SMILES, call_tool
from marcus.core.models import Owner

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(tools_limit)])

MAX_MOLFILES = 20
MAX_MOLFILE_BYTES = 200_000
MAX_MCS_TOTAL = 1_000_000

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
