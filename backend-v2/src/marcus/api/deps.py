import ipaddress
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.asyncio import AsyncSession

from marcus.core.db import get_db
from marcus.core.enums import (
    ACTIVE_IMAGE_STATUSES,
    ACTIVE_PAPER_STATUSES,
    Engine,
    ImageJobStatus,
    OwnerKind,
    PaperStatus,
    PriorityClass,
)
from marcus.core.models import ImageJob, Owner, Paper, Segment
from marcus.core.settings import fake_enabled, get_settings
from marcus.core.tokens import hash_token, new_token

COOKIE_NAME = "marcus_owner"
COOKIE_MAX_AGE = 30 * 24 * 3600
COOKIE_PATH = "/api/v2"
UNKNOWN_IP = "unknown"
# request.state key: SecurityMiddleware adds the cookie for it to whatever response goes out.
# Set for a new owner and, to renew the cookie's Max-Age (sliding expiry), for a known one.
NEW_OWNER_TOKEN = "new_owner_token"
TOUCH_EVERY = timedelta(seconds=60)  # last_seen_at is written at most this often
IPV6_RATE_PREFIX = 64  # one IPv6 client usually holds a whole /64


def _parse_ip(value: str):
    """An address, or None. An IPv4-mapped IPv6 address (dual-stack socket) is its IPv4."""
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if addr.version == 6 and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def rate_key_for_ip(ip: str) -> str:
    """The per-address bucket for limits: an IPv6 client's /64, else the address as is.

    Used by the per-IP rate limit, the new-owner limit and the active-paper limit.
    """
    addr = _parse_ip(ip)
    if addr is None or addr.version == 4:
        return ip
    return str(ipaddress.IPv6Network((int(addr), IPV6_RATE_PREFIX), strict=False))


def _trusted_networks() -> list:
    # Entries are validated when Settings load (an invalid one stops startup).
    return [ipaddress.ip_network(e, strict=False) for e in get_settings().trusted_proxies]


def _is_trusted(addr, nets) -> bool:
    return any(addr in n for n in nets if n.version == addr.version)


def is_trusted_proxy(host: str | None) -> bool:
    """Whether a socket peer is one of `trusted_proxies`."""
    addr = _parse_ip(host) if host else None
    return addr is not None and _is_trusted(addr, _trusted_networks())


def client_ip(request: Request) -> str:
    """Socket peer, or the right-most X-Forwarded-For entry that is not a trusted proxy.

    Every X-Forwarded-For header line is read (joined in order), so a client-sent line cannot
    hide the line a proxy added. A missing or unparseable peer gives `UNKNOWN_IP`, which the
    limits treat as one shared bucket.
    """
    peer_addr = _parse_ip(request.client.host) if request.client and request.client.host else None
    if peer_addr is None:
        return UNKNOWN_IP
    peer = str(peer_addr)
    nets = _trusted_networks()
    if not nets or not _is_trusted(peer_addr, nets):
        return peer
    header = ",".join(request.headers.getlist("x-forwarded-for"))
    if not header.strip():
        return peer
    for part in reversed(header.split(",")):
        addr = _parse_ip(part)
        if addr is None:
            return peer  # malformed chain: do not trust any of it
        if not _is_trusted(addr, nets):
            return str(addr)
    return peer


def owners_from_ip(ip: str):
    """SQL condition for browser owners created from `ip`'s bucket (`rate_key_for_ip`).

    Unknown = created without an IP; IPv6 = any address in the same /64.
    """
    if ip == UNKNOWN_IP or _parse_ip(ip) is None:
        where = Owner.created_ip.is_(None)
    else:
        # `<<=`: contained in or equal to (an IPv4 key is a single address)
        where = Owner.created_ip.op("<<=")(func.cast(rate_key_for_ip(ip), INET))
    return and_(Owner.kind == OwnerKind.BROWSER.value, where)


def _used():
    """SQL condition: the owner was used after the request that created it: it came back with
    its cookie (last_seen_at moved, see `_touch`) or has a paper or an image job (a cookie-less
    upload creates both in one request). A new browser's parallel first requests each create
    an owner, but the browser keeps one cookie: the others are never used, and only the total
    cap (ip_max_new_sessions_per_hour) counts them."""
    return or_(
        Owner.last_seen_at > Owner.created_at,
        exists().where(Paper.owner_id == Owner.id),
        exists().where(ImageJob.owner_id == Owner.id),
    )


TOO_MANY_SESSIONS = "Too many new sessions from this address"


async def advisory_xact_lock(db: AsyncSession, key: str) -> None:
    """Postgres advisory lock on `key` (hashed), held until the transaction ends."""
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))


async def _lock_address(db: AsyncSession, ip: str) -> None:
    """Serialize owner creation and first use per address bucket (until the commit)."""
    await advisory_xact_lock(db, rate_key_for_ip(ip))


async def _check_first_use(db: AsyncSession, owner: Owner) -> None:
    """An unused owner coming back for the first time becomes used: refuse (429, as at
    creation) if its address already has ip_max_new_owners_per_hour used owners created in the
    last hour. Without this, owners collected unused (only the total cap applies) could all be
    used later. An owner already used (a cookie-less upload gave it a paper) or created over an
    hour ago is not counted again. The caller's commit (the touch) ends the lock."""
    since = datetime.now(UTC) - timedelta(hours=1)
    if owner.created_at < since:
        return
    ip = str(owner.created_ip) if owner.created_ip is not None else UNKNOWN_IP
    await _lock_address(db, ip)
    already = (
        await db.execute(select(func.count()).select_from(Owner).where(Owner.id == owner.id, _used()))
    ).scalar_one()
    if already:
        return
    used = (
        await db.execute(
            select(func.count())
            .select_from(Owner)
            .where(owners_from_ip(ip), Owner.created_at >= since, Owner.id != owner.id, _used())
        )
    ).scalar_one()
    if used >= get_settings().ip_max_new_owners_per_hour:
        await db.rollback()
        raise HTTPException(status_code=429, detail=TOO_MANY_SESSIONS)


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


async def _touch(db: AsyncSession, owner: Owner) -> bool:
    """Record activity at most once a minute (no write per request). True if it wrote.

    The first return of an owner is always recorded (last_seen_at moves past created_at): that
    marks it as used for the new-owner limit (`_used`)."""
    now = datetime.now(UTC)
    first_return = owner.last_seen_at is not None and owner.last_seen_at <= owner.created_at
    if (
        owner.last_seen_at is not None
        and not first_return
        and now - owner.last_seen_at < TOUCH_EVERY
    ):
        return False
    owner.last_seen_at = now
    await db.commit()
    return True


def owner_cookie_header(token: str) -> str:
    """The `Set-Cookie` value for a browser owner's token (new, or renewed on use)."""
    response = Response()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=get_settings().cookie_secure,
    )
    return response.headers["set-cookie"]


async def current_owner(request: Request, db: AsyncSession = Depends(get_db)) -> Owner:
    """The caller's owner: API key, else browser cookie, else a new browser owner (limits per
    client address and hour: ip_max_new_owners_per_hour used owners, ip_max_new_sessions_per_hour
    owner rows in all).

    A new owner's token goes on `request.state`; SecurityMiddleware sets the cookie on the
    response, whatever it is (an error, a file, a stream), not only on a route's own one.
    A known browser owner's cookie is sent again with a fresh Max-Age whenever its activity is
    recorded (at most once a minute), so the cookie expires 30 days after the last use, not
    after the first visit.
    """
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
            if owner.last_seen_at is not None and owner.last_seen_at <= owner.created_at:
                await _check_first_use(db, owner)  # its first return makes it a used owner
            if await _touch(db, owner):
                setattr(request.state, NEW_OWNER_TOKEN, cookie)  # sliding expiry
            return owner

    ip = client_ip(request)
    ip_valid = _parse_ip(ip) is not None
    # Serialize per-IP creation: the lock lives until the commit that inserts the owner.
    # An unknown address is one shared bucket (fail closed), not a free pass.
    await _lock_address(db, ip)
    since = datetime.now(UTC) - timedelta(hours=1)
    total, used = (
        await db.execute(
            select(func.count(), func.count().filter(_used()))
            .select_from(Owner)
            .where(owners_from_ip(ip), Owner.created_at >= since)
        )
    ).one()
    if (
        used >= settings.ip_max_new_owners_per_hour
        or total >= settings.ip_max_new_sessions_per_hour
    ):
        raise HTTPException(status_code=429, detail=TOO_MANY_SESSIONS)

    token = new_token()
    owner = Owner(
        kind=OwnerKind.BROWSER.value,
        token_hash=hash_token(token),
        priority_class=int(PriorityClass.BROWSER),
        created_ip=ip if ip_valid else None,
    )
    db.add(owner)
    await db.commit()
    setattr(request.state, NEW_OWNER_TOKEN, token)
    return owner


# --- owned resources -----------------------------------------------------------------------

NOT_FOUND = "not found"


def not_found() -> HTTPException:
    """The one 404 for missing, deleted and other owners' resources (no existence oracle)."""
    return HTTPException(status_code=404, detail=NOT_FOUND)


def require_engine_enabled(engine: Engine) -> None:
    """422 for the fake engine unless fake engines are enabled (every route that takes one)."""
    if engine == Engine.FAKE and not fake_enabled():
        raise HTTPException(status_code=422, detail="Engine not available")


_DELETED = {Paper: PaperStatus.DELETED.value, ImageJob: ImageJobStatus.DELETED.value}
_ACTIVE = {Paper: ACTIVE_PAPER_STATUSES, ImageJob: ACTIVE_IMAGE_STATUSES}


def visible(model: type[Paper] | type[ImageJob]) -> tuple:
    """Conditions for a paper or image job to be served at all: not deleted and not expired. An
    expired one waits for the daily retention purge, but is already gone for every client (the
    same 404 as a missing one)."""
    return (model.status != _DELETED[model], model.expires_at >= func.now())


def active(model: type[Paper] | type[ImageJob]) -> tuple:
    """Conditions for active work (papers checking|processing, image jobs queued|processing).
    Expired work is gone for the client (404) even before the purge, so it is not active."""
    return (model.status.in_(_ACTIVE[model]), model.expires_at >= func.now())


async def get_owned_paper(db: AsyncSession, owner: Owner, paper_id: uuid.UUID) -> Paper:
    paper = (
        await db.execute(
            select(Paper).where(
                Paper.id == paper_id,
                Paper.owner_id == owner.id,
                *visible(Paper),
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
                *visible(ImageJob),
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
                *visible(Paper),
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    return row[0], row[1]
