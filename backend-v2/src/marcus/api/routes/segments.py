import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.chem import check_curation
from marcus.api.chempool import CHEM
from marcus.api.decisions import record_decisions
from marcus.api.depiction import draw_or_read, orientation_templates, shown_structure
from marcus.api.deps import (
    current_owner,
    get_owned_segment,
    not_found,
    require_engine_enabled,
    work_ip,
)
from marcus.api.read import IMAGE_HEADERS, named_on, structure_out, waiting_ocsr_step
from marcus.api.schemas import (
    CurationIn,
    CurationOut,
    PredictionRequest,
    ReadAccepted,
    StepAccepted,
)
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine
from marcus.core.models import Curation, InheritedStatus, Owner, Prediction, Step
from marcus.core.pipeline import ModeNotAllowed, read_segment, request_ocsr

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
    prediction instead), in the paper's orientation when the segment has a template (the first
    of MolScribe's and MolNexTR's molfiles with the image's positions). Drawn once per distinct SMILES (and template) and stored
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
    # A structure frozen with an inherited decision is not drawn (api.read: it holds only while
    # the structure is a hidden repeat, whose card is the main one's).
    inherited = await db.get(InheritedStatus, segment.id) is not None
    shown = await shown_structure(paper, segment, curation, predictions, engine, not inherited)
    template = orientation_templates(segment, predictions)
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


@router.post("/segments/{segment_id}/read", status_code=202, response_model=ReadAccepted)
async def read_segment_route(
    request: Request,
    segment_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> ReadAccepted:
    """Pick mode: the user picked this box; it is read by the three engines (again: the steps
    it has). 409 {"detail": "mode"} when its paper is not in pick mode."""
    segment, _ = await get_owned_segment(db, owner, segment_id)
    try:
        ip = work_ip(request)
        steps = await db.run_sync(lambda s: read_segment(s, segment.id, started_ip=ip))
    except ModeNotAllowed:
        await db.rollback()
        raise HTTPException(status_code=409, detail="mode") from None
    except ValueError:
        await db.rollback()
        raise not_found() from None
    await db.commit()
    return ReadAccepted(step_ids=[st.id for st in steps])


@router.put("/segments/{segment_id}/curation", response_model=CurationOut)
async def put_curation(
    segment_id: uuid.UUID,
    body: CurationIn,
    decision: bool = False,
    shown_prediction_id: uuid.UUID | None = None,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> CurationOut:
    segment, paper = await get_owned_segment(db, owner, segment_id, with_labels=True)
    # ?shown_prediction_id=: the prediction the card showed, frozen with a decision on it
    # (marcus.api.decisions); it must be this segment's own.
    if shown_prediction_id is not None and await db.scalar(
        select(Prediction.segment_id).where(Prediction.id == shown_prediction_id)
    ) != segment.id:
        raise HTTPException(
            status_code=422,
            detail=[{"type": "value_error", "loc": ["query", "shown_prediction_id"],
                     "msg": "not a prediction of this segment"}],
        )  # fmt: skip
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
    # A status inherited from a main-figure structure is shown as unchecked while it does not
    # hold: a note or structure edit sends that back, so it keeps the stored status (and its
    # mark). Only a decision on this card replaces it.
    keep = not decision and await db.get(InheritedStatus, segment.id) is not None
    curation = await db.get(Curation, segment.id)
    if curation is None:
        curation = Curation(segment_id=segment.id)
        db.add(curation)
    if not keep or curation.status is None:
        curation.status = body.status
    curation.smiles = body.smiles
    curation.molfile = body.molfile
    if body.smiles is not None or body.molfile is not None:
        # a structure of its own: no prediction stays decided on (marcus.api.decisions), so
        # clearing the structure later brings back the default pick, not an old frozen one
        curation.shown_prediction_id = None
    curation.note = body.note
    curation.rgroups = rgroups
    curation.updated_at = datetime.now(UTC)
    # ?decision=true: the status is a decision made now on this card (not a note or structure
    # edit that keeps it); on a main-figure structure it goes to its repeats.
    if decision:
        try:
            shown = {segment.id: shown_prediction_id} if shown_prediction_id else None
            await record_decisions(db, paper, {segment.id: body.status}, shown)
        except HTTPException:
            await db.rollback()
            raise
    await db.commit()
    out = structure_out(CurationOut, curation, named)
    if keep:
        out.status = body.status  # as the client shows it (api.read masks it the same way)
    return out
