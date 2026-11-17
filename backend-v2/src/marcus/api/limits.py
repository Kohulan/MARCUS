"""Active-work limits shared by every route that starts a pipeline (papers, image jobs)."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import owners_from_ip, rate_key_for_ip
from marcus.core.enums import OwnerKind, PaperStatus
from marcus.core.models import ImageJob, Owner, Paper
from marcus.core.settings import get_settings

ACTIVE_PAPER = [PaperStatus.CHECKING.value, PaperStatus.PROCESSING.value]
ACTIVE_IMAGE = ["queued", "processing"]


async def _count_active(db: AsyncSession, *filters_paper, ip: str | None = None) -> int:
    # Expired work is gone for the client (404) even before the daily purge removes it, so it
    # holds no active slot either.
    papers = (
        select(func.count())
        .select_from(Paper)
        .where(Paper.status.in_(ACTIVE_PAPER), Paper.expires_at >= func.now())
    )
    images = (
        select(func.count())
        .select_from(ImageJob)
        .where(ImageJob.status.in_(ACTIVE_IMAGE), ImageJob.expires_at >= func.now())
    )
    if ip is None:
        owner_id = filters_paper[0]
        papers = papers.where(Paper.owner_id == owner_id)
        images = images.where(ImageJob.owner_id == owner_id)
    else:
        papers = papers.join(Owner, Owner.id == Paper.owner_id).where(owners_from_ip(ip))
        images = images.join(Owner, Owner.id == ImageJob.owner_id).where(owners_from_ip(ip))
    total = 0
    for q in (papers, images):
        total += (await db.execute(q)).scalar_one()
    return total


async def enforce_active_limits(db: AsyncSession, owner: Owner, ip: str) -> None:
    """429 when the owner (3) or the client address (6; an IPv6 /64) has too much active work.

    Active = papers checking|processing plus image jobs queued|processing, not expired.
    """
    settings = get_settings()
    # Locks live until the upload commits (or rolls back). Order: owner, then IP.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"owner:{owner.id}"))))
    if owner.kind != OwnerKind.BROWSER.value:
        return  # API keys get a daily page quota instead
    # An unknown client address is one shared bucket (fail closed), like any other address.
    ip_key = rate_key_for_ip(ip)  # an IPv6 client's /64
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"ip:{ip_key}"))))
    if await _count_active(db, owner.id) >= settings.browser_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers")
    if await _count_active(db, ip=ip) >= settings.ip_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers from this address")
