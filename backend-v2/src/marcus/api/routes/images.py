import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import client_ip, current_owner, get_owned_image_job
from marcus.api.limits import enforce_active_limits
from marcus.api.security import upload_limit
from marcus.api.uploads import normalize_to_png, read_limited, sanitize_display_name, sniff_image
from marcus.core.db import get_db
from marcus.core.enums import Engine
from marcus.core.models import Owner, Prediction
from marcus.core.pipeline import start_image_job
from marcus.core.settings import get_settings

router = APIRouter()


class ImagePrediction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    smiles: str
    molfile: str | None
    valid: bool
    engine: str
    engine_version: str
    ms: int


class ImageJobOut(BaseModel):
    id: uuid.UUID
    status: str
    engine: str
    display_name: str
    created_at: datetime
    expires_at: datetime
    prediction: ImagePrediction | None
    error: str | None


@router.post("/images", status_code=202, dependencies=[Depends(upload_limit)])
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    engine: Engine = Form(Engine.DECIMER),
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if engine == Engine.FAKE and not settings.enable_fake_engines:
        raise HTTPException(status_code=422, detail="Engine not available")
    await enforce_active_limits(db, owner, client_ip(request))

    data = await read_limited(file, settings.max_upload_bytes)

    def _prepare() -> bytes:  # Pillow decoding is CPU-bound and sync
        sniff_image(data)
        return normalize_to_png(data)

    png = await run_in_threadpool(_prepare)
    name = sanitize_display_name(file.filename)
    job = await db.run_sync(lambda s: start_image_job(s, owner, png, name, engine))
    await db.commit()
    return {"image_job_id": str(job.id), "status": job.status}


@router.get("/images/{job_id}", response_model=ImageJobOut)
async def get_image_job(
    job_id: uuid.UUID,
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> ImageJobOut:
    job = await get_owned_image_job(db, owner, job_id)
    pred = (
        await db.execute(
            select(Prediction)
            .where(Prediction.image_job_id == job.id)
            .order_by(Prediction.created_at.desc(), Prediction.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return ImageJobOut(
        id=job.id,
        status=job.status,
        engine=job.engine,
        display_name=job.display_name,
        created_at=job.created_at,
        expires_at=job.expires_at,
        prediction=ImagePrediction.model_validate(pred) if pred else None,
        error=job.error,
    )
