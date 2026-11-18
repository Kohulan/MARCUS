import asyncio
import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import (
    client_ip,
    current_owner,
    get_owned_image_job,
    not_found,
    require_engine_enabled,
    visible,
)
from marcus.api.limits import enforce_active_limits
from marcus.api.read import IMAGE_HEADERS, waiting_ocsr_step
from marcus.api.schemas import (
    ImageJobList,
    ImageJobOut,
    ImageJobSummary,
    ImagePrediction,
    ImageStepOut,
    PredictionOut,
    PredictionRequest,
    StepAccepted,
)
from marcus.api.security import upload_limit
from marcus.api.uploads import normalize_to_png, read_limited, sanitize_display_name, sniff_image
from marcus.core import storage
from marcus.core.db import get_db
from marcus.core.enums import Engine, StepKind
from marcus.core.models import ImageJob, Owner, Prediction, Step
from marcus.core.pipeline import new_image_job, request_image_ocsr, store_image
from marcus.core.settings import get_settings

router = APIRouter()


async def decode_image(slots: asyncio.Semaphore, data: bytes) -> bytes:
    """Sniff and re-encode as PNG in the threadpool; at most `slots` decodes at once, so a
    burst of uploads cannot fill the threadpool with CPU-bound Pillow work."""

    def _prepare() -> bytes:
        sniff_image(data)
        return normalize_to_png(data)

    async with slots:
        return await run_in_threadpool(_prepare)


@router.post("/images", status_code=202, dependencies=[Depends(upload_limit)])
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    engine: Engine = Form(Engine.DECIMER),
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    require_engine_enabled(engine)
    await enforce_active_limits(db, owner, client_ip(request))

    data = await read_limited(file, settings.max_upload_bytes)
    png = await decode_image(request.app.state.decode_slots, data)
    name = sanitize_display_name(file.filename)
    sha = await run_in_threadpool(lambda: hashlib.sha256(png).hexdigest())  # off the event loop
    job = await db.run_sync(lambda s: new_image_job(s, owner, sha, name, engine))
    await run_in_threadpool(store_image, job.id, png)  # before the commit, as start_image_job
    await db.commit()
    return {"image_job_id": str(job.id), "status": job.status}


@router.get("/images", response_model=ImageJobList)
async def list_image_jobs(
    owner: Owner = Depends(current_owner), db: AsyncSession = Depends(get_db)
) -> ImageJobList:
    rows = (
        await db.execute(
            select(ImageJob)
            .where(ImageJob.owner_id == owner.id, *visible(ImageJob))
            .order_by(ImageJob.created_at.desc(), ImageJob.id)
        )
    ).scalars()
    return ImageJobList(jobs=[ImageJobSummary.model_validate(j) for j in rows])


@router.get("/images/{job_id}/image")
async def image_job_image(
    job_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    job = await get_owned_image_job(db, owner, job_id)
    path = storage.image_job_path(job.id)
    if not path.is_file():
        raise not_found()
    return FileResponse(path, media_type="image/png", headers=IMAGE_HEADERS)


@router.post("/images/{job_id}/predictions", status_code=202, response_model=StepAccepted)
async def run_image_prediction(
    job_id: uuid.UUID,
    body: PredictionRequest,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> StepAccepted:
    job = await get_owned_image_job(db, owner, job_id)
    require_engine_enabled(body.engine)
    # Repeat clicks must not flood the queue.
    waiting = await waiting_ocsr_step(db, Step.image_job_id == job.id, body.engine)
    if waiting is not None:
        return StepAccepted(step_id=waiting)
    try:
        step = await db.run_sync(lambda s: request_image_ocsr(s, job.id, body.engine))
    except ValueError:
        await db.rollback()
        raise not_found() from None  # deleted meanwhile
    step_id = step.id
    await db.commit()
    return StepAccepted(step_id=step_id)


@router.get("/images/{job_id}", response_model=ImageJobOut)
async def get_image_job(
    job_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> ImageJobOut:
    job = await get_owned_image_job(db, owner, job_id)
    preds = list(
        (
            await db.execute(
                select(Prediction)
                .where(Prediction.image_job_id == job.id)
                .order_by(Prediction.created_at.desc(), Prediction.id)
            )
        ).scalars()
    )
    steps = list(
        (
            await db.execute(
                select(Step)
                .where(Step.image_job_id == job.id, Step.kind == StepKind.OCSR.value)
                .order_by(Step.created_at.desc(), Step.seq.desc(), Step.id)
            )
        ).scalars()
    )
    failed = next((s for s in steps if s.status == "failed"), None)
    return ImageJobOut(
        id=job.id,
        status=job.status,
        engine=job.engine,
        display_name=job.display_name,
        created_at=job.created_at,
        expires_at=job.expires_at,
        prediction=ImagePrediction.model_validate(preds[0]) if preds else None,
        predictions=[PredictionOut.model_validate(p) for p in preds],
        error_class=failed.error_class if failed else None,
        steps=[
            ImageStepOut(engine=s.engine or job.engine, status=s.status, error_class=s.error_class)
            for s in steps
        ],
        error=job.error,
    )
