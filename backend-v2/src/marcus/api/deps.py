import ipaddress
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import and_, func, select
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
UNKNOWN_IP = "unknown"
# request.state key: SecurityMiddleware adds the cookie for it to whatever response goes out
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


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


async def _touch(db: AsyncSession, owner: Owner) -> None:
    """Record activity at most once a minute (no write per request)."""
    now = datetime.now(UTC)
    if owner.last_seen_at is not None and now - owner.last_seen_at < TOUCH_EVERY:
        return
    owner.last_seen_at = now
    await db.commit()


def owner_cookie_header(token: str) -> str:
    """The `Set-Cookie` value for a new browser owner's token."""
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
    """The caller's owner: API key, else browser cookie, else a new browser owner.

    A new owner's token goes on `request.state`; SecurityMiddleware sets the cookie on the
    response, whatever it is (an error, a file, a stream), not only on a route's own one.
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
            await _touch(db, owner)
            return owner

    ip = client_ip(request)
    ip_valid = _parse_ip(ip) is not None
    # Serialize per-IP creation: the lock lives until the commit that inserts the owner.
    # An unknown address is one shared bucket (fail closed), not a free pass.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(rate_key_for_ip(ip)))))
    since = datetime.now(UTC) - timedelta(hours=1)
    recent = (
        await db.execute(
            select(func.count())
            .select_from(Owner)
            .where(owners_from_ip(ip), Owner.created_at >= since)
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
    setattr(request.state, NEW_OWNER_TOKEN, token)
    return owner


# --- owned resources -----------------------------------------------------------------------

NOT_FOUND = "not found"


def not_found() -> HTTPException:
    """The one 404 for missing, deleted and other owners' resources (no existence oracle)."""
    return HTTPException(status_code=404, detail=NOT_FOUND)


def paper_visible() -> tuple:
    """Conditions for a paper to be served at all: not deleted and not expired. An expired
    paper waits for the daily retention purge, but is already gone for every client (the same
    404 as a missing one)."""
    return (Paper.status != PaperStatus.DELETED.value, Paper.expires_at >= func.now())


async def get_owned_paper(db: AsyncSession, owner: Owner, paper_id: uuid.UUID) -> Paper:
    paper = (
        await db.execute(
            select(Paper).where(
                Paper.id == paper_id,
                Paper.owner_id == owner.id,
                *paper_visible(),
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
                ImageJob.expires_at >= func.now(),
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
                *paper_visible(),
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    return row[0], row[1]
