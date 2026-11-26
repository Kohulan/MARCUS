"""`POST /tools/{depict,smiles-to-molfile,mcs,compare}`: short synchronous jobs on q.tools.

The calls go through marcus.api.tooling (wait limit, error mapping, task expiry and the tools'
own thread budget; see its docstring).
"""

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from redis.exceptions import RedisError

from marcus.api import highlight
from marcus.api.chempool import CHEM
from marcus.api.deps import current_owner
from marcus.api.security import tools_limit
from marcus.api.tooling import MAX_SMILES, call_tool, tools_busy
from marcus.core.models import Owner

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(tools_limit)])

MAX_MOLFILES = 20
MAX_MOLFILE_BYTES = 200_000
MAX_MCS_TOTAL = 1_000_000
MAX_HIGHLIGHT_ATOMS = 128  # = marcus.workers.tools.MAX_HIGHLIGHT_ATOMS, which checks it again
# One SMARTS atom: a bracket atom, or an organic-subset / any-atom symbol outside brackets.
_SMARTS_ATOM = re.compile(r"\[[^\]]*\]|Cl|Br|[BCNOPSFIbcnops*Aa]")

MAX_MARKS = 250  # = marcus.workers.tools.MAX_MARKS, which checks the atoms again
Smiles = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SMILES)]
# an atom index: a SMILES of MAX_SMILES characters has fewer atoms than that
Mark = Annotated[int, Field(strict=True, ge=0, lt=MAX_SMILES)]
Molfile = Annotated[str, StringConstraints(min_length=1, max_length=MAX_MOLFILE_BYTES)]


class DepictIn(BaseModel):
    smiles: Smiles
    format: Literal["svg", "png"] = "svg"
    width: int = Field(512, ge=50, le=2000)
    height: int = Field(512, ge=50, le=2000)
    highlight: str = Field("", max_length=MAX_SMILES)
    # Required with a highlight: the token /tools/mcs issued with that SMARTS (F5)
    highlight_token: str | None = Field(None, max_length=8192)
    # An OCSR molfile with the image's atom positions: the drawing follows the paper's
    # orientation where the worker can use it (marcus.workers.orient), else it is the normal one.
    # Bounded like an MCS molfile; the worker's alignment has its own time and atom caps.
    template: str | None = Field(None, max_length=MAX_MOLFILE_BYTES)
    # Atoms of the SMILES (its atom order) drawn with an orange glow: where this answer differs
    # from the others (marcus.workers.tools MAX_MARKS). No search: plain indices.
    marks: list[Mark] = Field(default_factory=list, max_length=MAX_MARKS)

    @field_validator("marks")
    @classmethod
    def _distinct_marks(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("marks must be distinct")
        return value

    @field_validator("highlight")
    @classmethod
    def _highlight_caps(cls, value: str) -> str:
        """No recursive SMARTS (a search per atom), at most MAX_HIGHLIGHT_ATOMS atoms."""
        if "$" in value:
            raise ValueError("recursive SMARTS are not allowed")
        if len(_SMARTS_ATOM.findall(value)) > MAX_HIGHLIGHT_ATOMS:
            raise ValueError(f"at most {MAX_HIGHLIGHT_ATOMS} atoms")
        return value


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


async def _signing_key(request: Request) -> bytes:
    try:
        return await highlight.signing_key(request.app.state.rate_limiter.redis)
    except (RedisError, OSError):
        raise tools_busy() from None


async def _check_highlight(request: Request, body: DepictIn) -> None:
    """422 unless the highlight comes with a token /tools/mcs issued for this SMARTS and a
    molecule the drawn SMILES is (marcus.api.highlight): no search with any other pattern."""
    if not body.highlight_token:
        raise HTTPException(status_code=422, detail=highlight.INVALID)
    key = await _signing_key(request)
    drawn = await CHEM.run(highlight.binding_key_of_smiles, body.smiles)
    if not highlight.verify(key, body.highlight_token, body.highlight, drawn):
        raise HTTPException(status_code=422, detail=highlight.INVALID)


@router.post("/depict")
async def depict(request: Request, body: DepictIn, _owner: Owner = Depends(current_owner)):
    if body.highlight:
        await _check_highlight(request, body)
    kwargs = {
        "smiles": body.smiles,
        "fmt": body.format,
        "width": body.width,
        "height": body.height,
        "highlight": body.highlight,
    }
    if body.template:
        kwargs["template"] = body.template
    if body.marks:  # only then: a tools worker from before the marks still draws the rest
        kwargs["marks"] = body.marks
    data = await call_tool("marcus.tools.depict", kwargs)
    return {"format": body.format, "data": data}


@router.post("/smiles-to-molfile")
async def smiles_to_molfile(body: SmilesIn, _owner: Owner = Depends(current_owner)):
    data = await call_tool("marcus.tools.smiles_to_molfile", {"smiles": body.smiles})
    return {"molfile": data}


@router.post("/mcs")
async def mcs(request: Request, body: McsIn, _owner: Owner = Depends(current_owner)):
    """The MCS, plus `highlight_token` (null without a common part): what /tools/depict needs
    to draw `mcs_smarts` highlighted in one of these molecules (marcus.api.highlight)."""
    result = await call_tool("marcus.tools.mcs", {"molfiles": body.molfiles})
    smarts = result.get("mcs_smarts") if isinstance(result, dict) else None
    token = None
    if smarts and result.get("atom_count"):
        keys = await CHEM.run(highlight.binding_keys_of_molfiles, body.molfiles)
        token = highlight.sign(await _signing_key(request), smarts, keys)
    return {**result, "highlight_token": token}


@router.post("/compare")
async def compare(body: CompareIn, _owner: Owner = Depends(current_owner)):
    kwargs = {"smiles_a": body.smiles_a, "smiles_b": body.smiles_b}
    return await call_tool("marcus.tools.compare", kwargs)
