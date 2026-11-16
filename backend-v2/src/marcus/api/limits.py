"""Active-work limits shared by every route that starts a pipeline (papers, image jobs)."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import _parse_ip
from marcus.core.enums import OwnerKind, PaperStatus
from marcus.core.models import ImageJob, Owner, Paper
from marcus.core.settings import get_settings

ACTIVE_PAPER = [PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value]
ACTIVE_IMAGE = ["queued", "processing"]


async def _count_active(db: AsyncSession, *filters_paper, ip: str | None = None) -> int:
    papers = select(func.count()).select_from(Paper).where(Paper.status.in_(ACTIVE_PAPER))
    images = select(func.count()).select_from(ImageJob).where(ImageJob.status.in_(ACTIVE_IMAGE))
    if ip is None:
        owner_id = filters_paper[0]
        papers = papers.where(Paper.owner_id == owner_id)
        images = images.where(ImageJob.owner_id == owner_id)
    else:
        papers = papers.join(Owner, Owner.id == Paper.owner_id)
        images = images.join(Owner, Owner.id == ImageJob.owner_id)
        cond = (Owner.kind == OwnerKind.BROWSER.value, Owner.created_ip == func.cast(ip, INET))
        papers = papers.where(*cond)
        images = images.where(*cond)
    total = 0
    for q in (papers, images):
        total += (await db.execute(q)).scalar_one()
    return total


async def enforce_active_limits(db: AsyncSession, owner: Owner, ip: str) -> None:
    """429 when the owner (3) or the client address (6) already has too much active work.

    Active = papers checking|processing plus image jobs queued|processing.
    """
    settings = get_settings()
    # Locks live until the upload commits (or rolls back). Order: owner, then IP.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"owner:{owner.id}"))))
    if owner.kind != OwnerKind.BROWSER.value:
        return  # API keys get a daily page quota instead
    valid_ip = _parse_ip(ip) is not None
    if valid_ip:
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"ip:{ip}"))))
    if await _count_active(db, owner.id) >= settings.browser_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers")
    if not valid_ip:
        return
    if await _count_active(db, ip=ip) >= settings.ip_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers from this address")
