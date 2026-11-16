from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import _parse_ip, client_ip, current_owner
from marcus.api.uploads import read_limited, sanitize_display_name, sniff_pdf
from marcus.core.db import get_db
from marcus.core.enums import Engine, OwnerKind, PaperStatus
from marcus.core.models import Owner, Paper
from marcus.core.pipeline import start_paper
from marcus.core.settings import get_settings

router = APIRouter()

ACTIVE = [PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value]


async def _enforce_active_limits(db: AsyncSession, owner: Owner, ip: str) -> None:
    settings = get_settings()
    if owner.kind != OwnerKind.BROWSER.value:
        return  # API keys get a daily page quota instead
    own = (
        await db.execute(
            select(func.count())
            .select_from(Paper)
            .where(Paper.owner_id == owner.id, Paper.status.in_(ACTIVE))
        )
    ).scalar_one()
    if own >= settings.browser_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers")
    if _parse_ip(ip) is None:
        return
    per_ip = (
        await db.execute(
            select(func.count())
            .select_from(Paper)
            .join(Owner, Owner.id == Paper.owner_id)
            .where(
                Owner.kind == OwnerKind.BROWSER.value,
                Owner.created_ip == func.cast(ip, INET),
                Paper.status.in_(ACTIVE),
            )
        )
    ).scalar_one()
    if per_ip >= settings.ip_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers from this address")


@router.post("/papers", status_code=202)
async def upload_paper(
    request: Request,
    file: UploadFile = File(...),
    engine: Engine = Form(Engine.DECIMER),
    ocsr: Literal["auto", "off"] = Form("auto"),
    owner: Owner = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if engine == Engine.FAKE and not settings.enable_fake_engines:
        raise HTTPException(status_code=422, detail="Engine not available")
    await _enforce_active_limits(db, owner, client_ip(request))

    data = await read_limited(file, settings.max_upload_bytes)
    sniff_pdf(data)
    name = sanitize_display_name(file.filename)

    paper = await db.run_sync(lambda s: start_paper(s, owner, data, name, engine, ocsr))
    await db.commit()
    return {"paper_id": str(paper.id), "status": PaperStatus.CHECKING.value}
