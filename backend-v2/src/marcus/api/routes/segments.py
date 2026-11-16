import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import current_owner, get_owned_segment, not_found
from marcus.api.routes.papers import IMAGE_HEADERS
from marcus.api.schemas import CurationIn, CurationOut, PredictionRequest, StepAccepted
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine, StepKind
from marcus.core.models import Curation, Owner, Step
from marcus.core.pipeline import ACTIVE, request_ocsr
from marcus.core.settings import get_settings

router = APIRouter()


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


@router.post("/segments/{segment_id}/predictions", status_code=202, response_model=StepAccepted)
async def run_prediction(
    segment_id: uuid.UUID,
    body: PredictionRequest,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StepAccepted:
    segment, _ = await get_owned_segment(db, owner, segment_id)
    if body.engine == Engine.FAKE and not get_settings().enable_fake_engines:
        raise HTTPException(status_code=422, detail="Engine not available")
    # A request for a segment and engine that is still waiting returns that step instead of
    # queueing another one (repeat clicks must not flood the queue).
    waiting = await db.scalar(
        select(Step.id)
        .where(
            Step.segment_id == segment.id,
            Step.kind == StepKind.OCSR.value,
            Step.engine == body.engine.value,
            Step.status.in_(ACTIVE),
        )
        .limit(1)
    )
    if waiting is not None:
        return StepAccepted(step_id=waiting)
    try:
        step = await db.run_sync(lambda s: request_ocsr(s, segment.id, body.engine))
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
    segment, _ = await get_owned_segment(db, owner, segment_id)
    curation = await db.get(Curation, segment.id)
    if curation is None:
        curation = Curation(segment_id=segment.id)
        db.add(curation)
    curation.status = body.status
    curation.smiles = body.smiles
    curation.molfile = body.molfile
    curation.note = body.note
    curation.updated_at = datetime.now(UTC)
    await db.commit()
    return CurationOut.model_validate(curation)
