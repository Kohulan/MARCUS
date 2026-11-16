import ipaddress
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.core.db import get_db
from marcus.core.enums import OwnerKind, PaperStatus, PriorityClass
from marcus.core.models import ImageJob, Owner, Paper, Segment
from marcus.core.settings import get_settings
from marcus.core.tokens import hash_token, new_token

COOKIE_NAME = "marcus_owner"
COOKIE_MAX_AGE = 30 * 24 * 3600
COOKIE_PATH = "/api/v2"


def _parse_ip(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _trusted_networks() -> list:
    nets = []
    for entry in get_settings().trusted_proxies:
        try:
            nets.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError:
            continue
    return nets


def _is_trusted(addr, nets) -> bool:
    return any(addr in n for n in nets if n.version == addr.version)


def client_ip(request: Request) -> str:
    """Socket peer, or the right-most X-Forwarded-For entry that is not a trusted proxy."""
    peer = request.client.host if request.client else ""
    peer_addr = _parse_ip(peer)
    nets = _trusted_networks()
    if peer_addr is None or not nets or not _is_trusted(peer_addr, nets):
        return peer
    header = request.headers.get("x-forwarded-for")
    if not header:
        return peer
    for part in reversed(header.split(",")):
        addr = _parse_ip(part)
        if addr is None:
            return peer  # malformed chain: do not trust any of it
        if not _is_trusted(addr, nets):
            return str(addr)
    return peer


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


async def _touch(db: AsyncSession, owner: Owner) -> None:
    owner.last_seen_at = datetime.now(UTC)
    await db.commit()


async def current_owner(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> Owner:
    settings = get_settings()

    key = _bearer(request)
    if key is not None:
        owner = (
            await db.execute(
                select(Owner).where(
                    Owner.token_hash == hash_token(key),
                    Owner.kind == OwnerKind.API_KEY.value,
                )
            )
        ).scalar_one_or_none()
        if owner is None or owner.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        await _touch(db, owner)
        return owner

    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        owner = (
            await db.execute(
                select(Owner).where(
                    Owner.token_hash == hash_token(cookie),
                    Owner.kind == OwnerKind.BROWSER.value,
                    Owner.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if owner is not None:
            await _touch(db, owner)
            return owner

    ip = client_ip(request)
    ip_valid = _parse_ip(ip) is not None
    if ip_valid:
        # Serialize per-IP creation: the lock lives until the commit that inserts the owner.
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(ip))))
        since = datetime.now(UTC) - timedelta(hours=1)
        recent = (
            await db.execute(
                select(func.count())
                .select_from(Owner)
                .where(Owner.created_ip == func.cast(ip, INET), Owner.created_at >= since)
            )
        ).scalar_one()
        if recent >= settings.ip_max_new_owners_per_hour:
            raise HTTPException(status_code=429, detail="Too many new sessions from this address")

    token = new_token()
    owner = Owner(
        kind=OwnerKind.BROWSER.value,
        token_hash=hash_token(token),
        priority_class=int(PriorityClass.BROWSER),
        created_ip=ip if ip_valid else None,
    )
    db.add(owner)
    await db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )
    return owner


# --- owned resources -----------------------------------------------------------------------

NOT_FOUND = "not found"


def not_found() -> HTTPException:
    """The one 404 for missing, deleted and other owners' resources (no existence oracle)."""
    return HTTPException(status_code=404, detail=NOT_FOUND)


async def get_owned_paper(db: AsyncSession, owner: Owner, paper_id: uuid.UUID) -> Paper:
    paper = (
        await db.execute(
            select(Paper).where(
                Paper.id == paper_id,
                Paper.owner_id == owner.id,
                Paper.status != PaperStatus.DELETED.value,
            )
        )
    ).scalar_one_or_none()
    if paper is None:
        raise not_found()
    return paper


async def get_owned_image_job(db: AsyncSession, owner: Owner, job_id: uuid.UUID) -> ImageJob:
    job = (
        await db.execute(
            select(ImageJob).where(
                ImageJob.id == job_id,
                ImageJob.owner_id == owner.id,
                ImageJob.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise not_found()
    return job


async def get_owned_segment(
    db: AsyncSession, owner: Owner, segment_id: uuid.UUID
) -> tuple[Segment, Paper]:
    row = (
        await db.execute(
            select(Segment, Paper)
            .join(Paper, Paper.id == Segment.paper_id)
            .where(
                Segment.id == segment_id,
                Paper.owner_id == owner.id,
                Paper.status != PaperStatus.DELETED.value,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    return row[0], row[1]
