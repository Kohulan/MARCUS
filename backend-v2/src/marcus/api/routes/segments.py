import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.chem import check_curation
from marcus.api.chempool import CHEM
from marcus.api.depiction import draw_or_read, orientation_template, shown_structure
from marcus.api.deps import (
    current_owner,
    get_owned_segment,
    not_found,
    require_engine_enabled,
    work_ip,
)
from marcus.api.read import IMAGE_HEADERS, named_on, structure_out, waiting_ocsr_step
from marcus.api.schemas import CurationIn, CurationOut, PredictionRequest, StepAccepted
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine
from marcus.core.models import Curation, Owner, Prediction, Step
from marcus.core.pipeline import request_ocsr

router = APIRouter()

DEPICTION_HEADERS = {
    "Cache-Control": "private, max-age=86400",  # the client's URL carries v=<structure key>
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
}


@router.get("/segments/{segment_id}/image")
async def segment_image(
    segment_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    segment, paper = await get_owned_segment(db, owner, segment_id)
    path = storage.segment_crop_path(paper.id, segment.image_sha256)
    if not path.is_file():
        raise not_found()
    return FileResponse(path, media_type="image/png", headers=IMAGE_HEADERS)


@router.get("/segments/{segment_id}/depiction")
async def segment_depiction(
    segment_id: uuid.UUID,
    request: Request,
    engine: Engine | None = None,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """SVG of the structure the UI shows for this segment (`engine`: that engine's newest valid
    prediction instead), in the paper's orientation when the segment has a template (MolNexTR's,
    else MolScribe's molfile). Drawn once per distinct SMILES (and template) and stored
    (marcus.api.depiction). The client's `v` query parameter only busts its cache; it is
    ignored here."""
    segment, paper = await get_owned_segment(db, owner, segment_id)
    curation = await db.get(Curation, segment.id)
    predictions = list(
        (
            await db.execute(
                select(Prediction)
                .where(Prediction.segment_id == segment.id)
                .order_by(Prediction.created_at.desc(), Prediction.id)
            )
        ).scalars()
    )
    shown = await shown_structure(paper, segment, curation, predictions, engine)
    template = orientation_template(segment, predictions)
    # End the read-only transaction (and free its connection): a miss may wait up to WAIT_S
    # on the tools worker. commit, not rollback: a rollback would expire `owner`.
    await db.commit()
    if shown is None:
        raise not_found()
    smiles, source = shown
    data = await draw_or_read(request, owner, smiles, source, template)
    return Response(data, media_type="image/svg+xml", headers=DEPICTION_HEADERS)


@router.post("/segments/{segment_id}/predictions", status_code=202, response_model=StepAccepted)
async def run_prediction(
    request: Request,
    segment_id: uuid.UUID,
    body: PredictionRequest,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StepAccepted:
    segment, _ = await get_owned_segment(db, owner, segment_id)
    require_engine_enabled(body.engine)
    # Repeat clicks must not flood the queue.
    waiting = await waiting_ocsr_step(db, Step.segment_id == segment.id, body.engine)
    if waiting is not None:
        return StepAccepted(step_id=waiting)
    try:
        ip = work_ip(request)
        step = await db.run_sync(lambda s: request_ocsr(s, segment.id, body.engine, started_ip=ip))
    except ValueError:
        await db.rollback()
        raise not_found() from None  # the paper was deleted meanwhile
    await db.commit()
    return StepAccepted(step_id=step.id)


@router.put("/segments/{segment_id}/curation", response_model=CurationOut)
async def put_curation(
    segment_id: uuid.UUID,
    body: CurationIn,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> CurationOut:
    segment, paper = await get_owned_segment(db, owner, segment_id, with_labels=True)
    named = named_on(paper.rgroup_text_labels, segment.page)
    rgroups: list[str] | None = None  # no structure of its own: nothing to label
    if body.smiles is not None or body.molfile is not None:
        error, rgroups = await CHEM.run(check_curation, body.smiles, body.molfile)
        if error is not None:
            field, msg = error
            raise HTTPException(
                status_code=422,
                detail=[{"type": "value_error", "loc": ["body", field], "msg": msg}],
            )
    curation = await db.get(Curation, segment.id)
    if curation is None:
        curation = Curation(segment_id=segment.id)
        db.add(curation)
    curation.status = body.status
    curation.smiles = body.smiles
    curation.molfile = body.molfile
    curation.note = body.note
    curation.rgroups = rgroups
    curation.updated_at = datetime.now(UTC)
    await db.commit()
    return structure_out(CurationOut, curation, named)
