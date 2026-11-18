"""Stored structure depictions: the CDK drawing of a segment's shown structure, made once.

The GPU OCSR images have no Java; CDK lives only in the tools image. So a depiction is drawn
lazily, on its first request, by `marcus.tools.depict` on q.tools (the same drawing as
`POST /tools/depict`) and stored under `data_root/depictions`, keyed by sha256 of the SMILES.
Later requests, for any segment with that SMILES, read the file.

Bounds on the write path: the SMILES always comes from the owner's own stored rows, never from
the request. A miss for a prediction is free (OCSR workers make predictions, and the upload
limits bound those); a miss for a curated SMILES (client-chosen through `PUT curation`) counts
one hit against the owner's `tools` bucket, as a `/tools/*` call would. A hit is free. SMILES
longer than MAX_SMILES are never drawn; a SMILES CDK cannot read gets an empty `.nodraw` marker
and is never tried again. Retention removes old files and keeps the directory under its cap.
"""

import hashlib
import logging
from typing import Literal

import anyio
from fastapi import HTTPException, Request

from marcus.api.chem import smiles_from_molfile
from marcus.api.chempool import CHEM
from marcus.api.deps import not_found
from marcus.api.security import tools_limit
from marcus.api.tooling import (
    MAX_SMILES,
    RETRY_AFTER_S,
    WAIT_S,
    depiction_slot,
    in_tool_budget,
    run_tool,
)
from marcus.core import storage
from marcus.core.enums import Engine
from marcus.core.models import Curation, Owner, Paper, Prediction, Segment

log = logging.getLogger(__name__)

DEPICTION_MAX_BYTES = 512 * 1024
DEPICT_TASK = "marcus.tools.depict"
DEPICT_OPTIONS = {"fmt": "svg", "width": 512, "height": 512, "highlight": ""}
Source = Literal["curated", "predicted"]


async def shown_structure(
    paper: Paper,
    segment: Segment,
    curation: Curation | None,
    predictions: list[Prediction],
    engine: Engine | None,
) -> tuple[str, Source] | None:
    """The SMILES the UI shows for `segment` and where it comes from.

    `predictions`: the segment's, newest first. With `engine`: the newest valid prediction of
    that engine. Without: the curated SMILES (or the one derived from a curated molfile), else
    the newest valid prediction of the paper's engine, else of any engine. The curation status
    is ignored: a rejected structure still has a drawing (unlike `export.choose`).
    """
    valid = [p for p in predictions if p.valid and p.segment_id == segment.id and p.smiles]
    if engine is not None:
        pick = next((p for p in valid if p.engine == engine.value), None)
        return (pick.smiles, "predicted") if pick is not None else None
    if curation is not None and curation.smiles:
        return curation.smiles, "curated"
    if curation is not None and curation.molfile:
        # RDKit holds the GIL: never on the event loop (marcus.api.chempool)
        try:
            smiles = await CHEM.run(smiles_from_molfile, curation.molfile)
        except HTTPException as exc:
            if exc.status_code == 503:  # chem pool busy: the route's 503 with Retry-After
                raise _unavailable() from None
            raise
        return (smiles, "curated") if smiles else None  # never a prediction instead
    pick = next((p for p in valid if p.engine == paper.engine), None) or next(iter(valid), None)
    return (pick.smiles, "predicted") if pick is not None else None


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="depiction unavailable, try again",
        headers={"Retry-After": str(RETRY_AFTER_S)},
    )


_UNDRAWABLE = object()


def _lookup(path, marker):
    """The stored bytes, _UNDRAWABLE when a `.nodraw` marker exists, else None (one thread hop
    per request)."""
    if marker.exists():
        return _UNDRAWABLE
    try:
        return path.read_bytes()
    except FileNotFoundError:  # not drawn yet, or removed by retention meanwhile
        return None


def _store(path, data: bytes) -> None:
    """Best effort: a drawing that cannot be stored is still returned (and drawn again later)."""
    if storage.disk_is_full():
        return
    try:
        storage.write_atomic(path, data)
    except OSError as exc:
        log.warning("depiction not stored (%s)", type(exc).__name__)


def _mark_undrawable(marker) -> None:
    if storage.disk_is_full():
        return
    try:
        storage.write_atomic(marker, b"")
    except OSError as exc:
        log.warning("depiction marker not stored (%s)", type(exc).__name__)


async def draw_or_read(request: Request, owner: Owner, smiles: str, source: Source) -> bytes:
    """The stored SVG of `smiles`, drawing (and storing) it on a miss. 404 (`not_found()`)
    for a SMILES that is never drawn; 429 for a curated miss over the tools limit; 503 with
    Retry-After when the depictions' share of the tools budget is held, or the tools worker is
    busy, slow or failing (nothing stored)."""
    if len(smiles) > MAX_SMILES:
        raise not_found()
    sha = hashlib.sha256(smiles.encode()).hexdigest()
    path = storage.depiction_path(sha)
    marker = storage.depiction_marker_path(sha)
    found = await anyio.to_thread.run_sync(_lookup, path, marker)
    if found is _UNDRAWABLE:
        raise not_found()
    if found is not None:
        return found

    # The depictions' own share of the tools budget (marcus.api.tooling): 503 + Retry-After at
    # once when it is held, before the owner's tools bucket is charged.
    with depiction_slot():
        if source == "curated":
            await tools_limit(request, owner)
        svg = await _draw(smiles, marker)
    data = svg.encode()
    if len(data) <= DEPICTION_MAX_BYTES:
        await anyio.to_thread.run_sync(_store, path, data)
    return data


async def _draw(smiles: str, marker) -> str:
    kwargs = {"smiles": smiles, **DEPICT_OPTIONS}
    try:
        svg = await in_tool_budget(run_tool, DEPICT_TASK, kwargs, WAIT_S)
    except HTTPException as exc:
        if exc.status_code == 422:  # CDK cannot read this SMILES: never try it again
            await anyio.to_thread.run_sync(_mark_undrawable, marker)
            raise not_found() from None
        raise _unavailable() from None  # 504 timeout, 500 tool error, 503 budget full
    if not isinstance(svg, str):
        raise _unavailable()
    return svg
