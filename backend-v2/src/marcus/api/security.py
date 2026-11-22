"""Security layer: response headers, request ids, safe errors, rate limits, CORS, docs.

Order of the ASGI stack (outermost first):

    SecurityMiddleware   headers + X-Request-ID on every response; a new owner's cookie;
                         catch-all 500
    CORSMiddleware       only when settings.cors_origins is non-empty
    IpRateLimitMiddleware  300/min per client IP (IPv6: per /64), every route but
                           GET /api/v2/health; GETs of page, crop and depiction images
                           have their own 3000/min bucket
    FastAPI app          per-owner limits are dependencies (`upload_limit`, `tools_limit`,
                         `annotate_limit`, `curation_limit`, `rgroup_limit`)

Both middlewares are pure ASGI (not BaseHTTPMiddleware), so SSE streams pass through
unbuffered. The catch-all lives in SecurityMiddleware rather than in Starlette's
ServerErrorMiddleware, which sits outside all user middleware and would send the 500
without the security headers.
"""

import logging
import math
import re
import time
import uuid
from collections import deque

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from marcus.api.deps import (
    COOKIE_NAME,
    NEW_OWNER_TOKEN,
    client_ip,
    current_owner,
    is_trusted_proxy,
    owner_cookie_header,
    rate_key_for_ip,
)
from marcus.api.redisutil import incr_with_ttl
from marcus.core import storage
from marcus.core.logging import log_context
from marcus.core.models import Owner
from marcus.core.settings import Settings, get_settings

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}
REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
_PAPER_PATH = re.compile(
    r"/api/v2/papers/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:/|$)"
)

ASSET_GET = re.compile(
    r"^/api/v2/(papers/[0-9a-f-]{36}/pages/\d{1,4}/image"
    r"|segments/[0-9a-f-]{36}/(image|depiction)"
    r"|images/[0-9a-f-]{36}/image)$"
)  # matched against scope["path"] (no query string)

WINDOW_S = 60
EXEMPT = ("GET", "/api/v2/health")
RATE_LIMITED = "rate limited"
# Circuit breaker (sliding window): BREAKER_FAILURES failed Redis calls (error or slower than
# settings.rate_limit_redis_timeout_s) within BREAKER_WINDOW_S open it; while open Redis is
# skipped for BREAKER_OPEN_S (no timeout wait per request). One slow call never opens it.
BREAKER_FAILURES = 3
BREAKER_WINDOW_S = 5.0
BREAKER_OPEN_S = 5.0
WARN_EVERY_S = 60.0

API_PREFIX = "/api/v2"
# The docs pages load Swagger UI / ReDoc from jsdelivr and run an inline bootstrap script.
# Exact versions, and the CSP allows only those package paths (not all of jsdelivr).
SWAGGER_UI_CDN = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/"
REDOC_CDN = "https://cdn.jsdelivr.net/npm/redoc@2.1.5/"
DOCS_CSP = (
    f"default-src 'none'; script-src 'unsafe-inline' {SWAGGER_UI_CDN} {REDOC_CDN}; "
    f"style-src 'unsafe-inline' {SWAGGER_UI_CDN} {REDOC_CDN} https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com "
    "https://cdn.redoc.ly; connect-src 'self'; worker-src blob:; frame-ancestors 'none'"
)


def _now() -> float:
    return time.time()


def _monotonic() -> float:
    return time.monotonic()


# --- request id, headers, catch-all ---------------------------------------------------------


def request_id_of(scope: Scope) -> str:
    """The id SecurityMiddleware gave this request (a fresh one if it never ran)."""
    state = scope.setdefault("state", {})
    if "request_id" not in state:
        state["request_id"] = _new_request_id(scope)
    return state["request_id"]


def _new_request_id(scope: Scope) -> str:
    """A proxy's well-formed X-Request-ID is kept (one id across the hops); else a new one.

    Only a trusted proxy may name the id: a client could otherwise plant ids in our logs.
    """
    incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
    peer = scope.get("client")
    if _REQUEST_ID.fullmatch(incoming) and peer and is_trusted_proxy(peer[0]):
        return incoming
    return uuid.uuid4().hex


class SecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = request_id_of(scope)
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)  # a route's own value wins
                headers.setdefault(REQUEST_ID_HEADER, rid)
                _add_owner_cookie(scope, headers)
            await send(message)

        paper = _PAPER_PATH.match(scope.get("path", ""))
        # request_id / paper_id go on every log line of this request (contextvars)
        with log_context(request_id=rid, paper_id=paper.group(1) if paper else None):
            try:
                await self.app(scope, receive, send_with_headers)
            except Exception:
                # %r: the path is client-chosen and may hold newlines (log forging)
                log.exception(
                    "unhandled error request_id=%s %s %r", rid, scope["method"], scope["path"]
                )
                if started:
                    raise  # the response is already on the wire; the server drops the connection
                response = JSONResponse(
                    {"detail": "internal error", "request_id": rid}, status_code=500
                )
                await response(scope, receive, send_with_headers)


def _add_owner_cookie(scope: Scope, headers: MutableHeaders) -> None:
    """The one place the owner cookie is set (new or renewed): on any response (error, file,
    stream)."""
    token = scope.get("state", {}).get(NEW_OWNER_TOKEN)
    if not token:
        return
    prefix = f"{COOKIE_NAME}="
    if any(v.startswith(prefix) for v in headers.getlist("set-cookie")):
        return  # the route set it itself
    headers.append("set-cookie", owner_cookie_header(token))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 shape without `input`, which can echo attacker data back."""
    errors = [{k: v for k, v in err.items() if k != "input"} for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


# --- rate limits ----------------------------------------------------------------------------


def limiter_redis() -> aioredis.Redis:
    settings = get_settings()
    timeout = settings.rate_limit_redis_timeout_s  # a hung Redis must not stall every request
    return aioredis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=timeout, socket_timeout=timeout
    )


class RateLimitUnavailable(Exception):
    pass


class RateLimiter:
    """Fixed one-minute windows in Redis: key `rl:{scope}:{key}:{window}`.

    A circuit breaker, shared by all scopes: BREAKER_FAILURES Redis failures within the last
    BREAKER_WINDOW_S (a sliding window; a success in between does not reset it) open it. While
    open, Redis is skipped for BREAKER_OPEN_S and every hit is refused per scope: uploads fail
    closed (503), ip and tools fail open; that includes a call already in flight when it
    opened and failing afterwards. When it closes, the failure count starts from zero.
    A failed call that leaves the breaker closed is let through in every scope, so one slow
    Redis call never refuses uploads.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis
        self._last_warning: dict[str, float] = {}
        self._open_until = 0.0
        self._failures: deque[float] = deque()  # monotonic times of recent Redis failures

    def _is_open(self) -> bool:
        return _monotonic() < self._open_until

    def _record_failure(self) -> bool:
        """Count one Redis failure; True if the breaker is now open."""
        now = _monotonic()
        self._failures.append(now)
        while now - self._failures[0] > BREAKER_WINDOW_S:
            self._failures.popleft()
        if len(self._failures) >= BREAKER_FAILURES:
            self._open_until = now + BREAKER_OPEN_S
            self._failures.clear()
            return True
        return False

    @staticmethod
    def limit_for(scope: str, settings: Settings) -> int:
        return {
            "upload": settings.rate_limit_upload_per_min,
            "tools": settings.rate_limit_tools_per_min,
            "ip": settings.rate_limit_ip_per_min,
            "ip_assets": settings.rate_limit_ip_assets_per_min,
            "annotate": settings.rate_limit_annotate_per_min,
            "curation": settings.rate_limit_curation_per_min,
            "rgroup": settings.rate_limit_rgroup_per_min,
        }[scope]

    async def hit(self, scope: str, key: str, *, fail_open: bool) -> int | None:
        """Count one request. Returns Retry-After seconds when over the limit, else None.

        Breaker open: None (fail open) or RateLimitUnavailable (fail closed). A Redis failure
        that does not open the breaker: None.
        """
        if self._is_open():
            if fail_open:
                return None
            raise RateLimitUnavailable(scope)
        now = _now()
        window = int(now) // WINDOW_S
        rkey = f"rl:{scope}:{key}:{window}"
        try:
            count = await incr_with_ttl(self.redis, rkey, WINDOW_S, first_only=True)
        except (RedisError, OSError) as exc:
            # A call that was in flight when the breaker opened is refused like any hit while
            # open; it is not counted (the count restarts when the breaker closes).
            opened = self._is_open() or self._record_failure()
            refuse = opened and not fail_open
            self._warn(scope, exc, not refuse)
            if refuse:
                raise RateLimitUnavailable(scope) from exc
            return None
        if count <= self.limit_for(scope, get_settings()):
            return None
        return max(1, math.ceil((window + 1) * WINDOW_S - now))

    def _warn(self, scope: str, exc: Exception, fail_open: bool) -> None:
        now = _monotonic()
        last = self._last_warning.get(scope)
        if last is not None and now - last < WARN_EVERY_S:
            return
        self._last_warning[scope] = now
        action = "failing open" if fail_open else "refusing requests (503)"
        log.warning("rate-limit redis unavailable for scope %s, %s: %r", scope, action, exc)


def _limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


class IpRateLimitMiddleware:
    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (scope["method"], scope["path"]) == EXEMPT:
            await self.app(scope, receive, send)
            return
        key = rate_key_for_ip(client_ip(Request(scope)))
        is_asset = scope["method"] == "GET" and ASSET_GET.match(scope["path"]) is not None
        retry = await self.limiter.hit("ip_assets" if is_asset else "ip", key, fail_open=True)
        if retry is not None:
            response = JSONResponse(
                {"detail": RATE_LIMITED}, status_code=429, headers={"Retry-After": str(retry)}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def _owner_limit(request: Request, owner: Owner, scope: str, fail_open: bool) -> None:
    try:
        retry = await _limiter(request).hit(scope, str(owner.id), fail_open=fail_open)
    except RateLimitUnavailable:
        raise HTTPException(status_code=503, detail="service unavailable") from None
    if retry is not None:
        raise HTTPException(
            status_code=429, detail=RATE_LIMITED, headers={"Retry-After": str(retry)}
        )


async def upload_limit(request: Request, owner: Owner = Depends(current_owner)) -> None:
    """503 while the data volume is below its free-space floor (new work only: accepted papers
    go on); then 10 uploads (papers + images) per owner per minute, failing closed while the
    breaker is open."""
    if storage.disk_is_full():
        log.warning("upload refused: data volume below its free-space floor")
        raise HTTPException(status_code=503, detail="storage is full, try again later")
    await _owner_limit(request, owner, "upload", fail_open=False)


async def annotate_limit(request: Request, owner: Owner = Depends(current_owner)) -> None:
    """5 annotation starts per owner per minute (the GPU model serves one paper at a time);
    fails closed while the breaker is open, like uploads."""
    await _owner_limit(request, owner, "annotate", fail_open=False)


async def rgroup_limit(request: Request, owner: Owner = Depends(current_owner)) -> None:
    """20 R-group reading starts per owner per minute (the GPU model reads one scaffold at a
    time); fails closed while the breaker is open, like annotation."""
    await _owner_limit(request, owner, "rgroup", fail_open=False)


async def curation_limit(request: Request, owner: Owner = Depends(current_owner)) -> None:
    """30 annotation curation saves/resets per owner per minute (each save locates values in
    the paper's text); fails open without Redis, like tools."""
    await _owner_limit(request, owner, "curation", fail_open=True)


async def tools_limit(request: Request, owner: Owner = Depends(current_owner)) -> None:
    """60 tool calls per owner per minute; fails open without Redis."""
    await _owner_limit(request, owner, "tools", fail_open=True)


# --- wiring ---------------------------------------------------------------------------------


def _docs_routes(app: FastAPI) -> None:
    openapi_url = f"{API_PREFIX}/openapi.json"

    @app.get(f"{API_PREFIX}/docs", include_in_schema=False)
    async def swagger():
        response = get_swagger_ui_html(
            openapi_url=openapi_url,
            title=f"{app.title} docs",
            swagger_js_url=f"{SWAGGER_UI_CDN}swagger-ui-bundle.js",
            swagger_css_url=f"{SWAGGER_UI_CDN}swagger-ui.css",
        )
        response.headers["Content-Security-Policy"] = DOCS_CSP
        return response

    @app.get(f"{API_PREFIX}/redoc", include_in_schema=False)
    async def redoc():
        response = get_redoc_html(
            openapi_url=openapi_url,
            title=f"{app.title} docs",
            redoc_js_url=f"{REDOC_CDN}bundles/redoc.standalone.js",
        )
        response.headers["Content-Security-Policy"] = DOCS_CSP
        return response


def fastapi_docs_kwargs(settings: Settings) -> dict:
    """Docs off unless `expose_docs`; then only the schema under /api/v2 (pages added below)."""
    openapi_url = f"{API_PREFIX}/openapi.json" if settings.expose_docs else None
    return {"openapi_url": openapi_url, "docs_url": None, "redoc_url": None}


def install(app: FastAPI, settings: Settings) -> None:
    """Add the security middleware, handlers and (optionally) docs pages to `app`."""
    if settings.expose_docs:
        _docs_routes(app)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.state.rate_limiter = RateLimiter(limiter_redis())
    # add_middleware puts each new layer outside the previous ones: innermost first.
    app.add_middleware(IpRateLimitMiddleware, limiter=app.state.rate_limiter)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type", "Authorization"],
        )
    app.add_middleware(SecurityMiddleware)
