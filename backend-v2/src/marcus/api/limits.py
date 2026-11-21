"""Active-work limits shared by every route that starts a pipeline (papers, image jobs)."""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.api.deps import active, advisory_xact_lock, rate_key_for_ip
from marcus.core.enums import OwnerKind
from marcus.core.models import ImageJob, Owner, Paper
from marcus.core.quota import pages_used_stmt
from marcus.core.settings import get_settings


async def _count_active(
    db: AsyncSession, *, owner_id: uuid.UUID | None = None, ip: str | None = None
) -> int:
    """Active papers plus image jobs of one owner, or started from one address bucket (`ip`:
    the work's own `started_ip`, not its owner's recorded IP, which retention deletes), in
    one statement (two scalar subqueries)."""
    papers = select(func.count()).select_from(Paper).where(*active(Paper))
    images = select(func.count()).select_from(ImageJob).where(*active(ImageJob))
    if ip is None:
        papers = papers.where(Paper.owner_id == owner_id)
        images = images.where(ImageJob.owner_id == owner_id)
    else:
        key = rate_key_for_ip(ip)
        papers = papers.where(Paper.started_ip == key)
        images = images.where(ImageJob.started_ip == key)
    total = select(papers.scalar_subquery() + images.scalar_subquery())
    return (await db.execute(total)).scalar_one()


async def enforce_active_limits(db: AsyncSession, owner: Owner, ip: str) -> None:
    """429 when the owner (3) or the client address (6; an IPv6 /64) has too much active work.

    Active = papers checking|processing plus image jobs queued|processing, not expired.
    """
    settings = get_settings()
    # Locks live until the upload commits (or rolls back). Order: owner, then IP.
    await advisory_xact_lock(db, f"owner:{owner.id}")
    if owner.kind != OwnerKind.BROWSER.value:
        # API keys get a daily page quota instead; the owner lock above serialises uploads.
        if owner.daily_page_quota is not None:
            used = (await db.execute(pages_used_stmt(owner.id))).scalar_one()
            if used >= owner.daily_page_quota:
                raise HTTPException(status_code=429, detail="daily quota exceeded")
        return
    # An unknown client address is one shared bucket (fail closed), like any other address.
    ip_key = rate_key_for_ip(ip)  # an IPv6 client's /64
    await advisory_xact_lock(db, f"ip:{ip_key}")
    if await _count_active(db, owner_id=owner.id) >= settings.browser_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers")
    if await _count_active(db, ip=ip) >= settings.ip_max_active_papers:
        raise HTTPException(status_code=429, detail="Too many active papers from this address")
