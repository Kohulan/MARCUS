"""Security layer: response headers, request ids, safe errors, rate limits, CORS, docs.

Order of the ASGI stack (outermost first):

    SecurityMiddleware   headers + X-Request-ID on every response; catch-all 500
    CORSMiddleware       only when settings.cors_origins is non-empty
    IpRateLimitMiddleware  300/min per client IP, every route but GET /api/v2/health
    FastAPI app          per-owner limits are dependencies (`upload_limit`, `tools_limit`)

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

from marcus.api.deps import client_ip, current_owner
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

WINDOW_S = 60
EXEMPT = ("GET", "/api/v2/health")
RATE_LIMITED = "rate limited"
REDIS_TIMEOUT_S = 0.5  # a hung Redis must not stall every request
WARN_EVERY_S = 60.0

API_PREFIX = "/api/v2"
# The docs pages load Swagger UI / ReDoc from jsdelivr and run an inline bootstrap script.
DOCS_CSP = (
    "default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com "
    "https://cdn.redoc.ly; connect-src 'self'; worker-src blob:; frame-ancestors 'none'"
)


def _now() -> float:
    return time.time()


# --- request id, headers, catch-all ---------------------------------------------------------


def request_id_of(scope: Scope) -> str:
    """The id SecurityMiddleware gave this request (a fresh one if it never ran)."""
    state = scope.setdefault("state", {})
    if "request_id" not in state:
        state["request_id"] = _new_request_id(scope)
    return state["request_id"]


def _new_request_id(scope: Scope) -> str:
    incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
    if _REQUEST_ID.fullmatch(incoming):
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
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            # %r: the path is client-chosen and may hold newlines (log forging)
            log.exception("unhandled error request_id=%s %s %r", rid, scope["method"], scope["path"])
            if started:
                raise  # the response is already on the wire; let the server drop the connection
            response = JSONResponse(
                {"detail": "internal error", "request_id": rid}, status_code=500
            )
            await response(scope, receive, send_with_headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 shape without `input`, which can echo attacker data back."""
    errors = [{k: v for k, v in err.items() if k != "input"} for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


# --- rate limits ----------------------------------------------------------------------------


def limiter_redis() -> aioredis.Redis:
    return aioredis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=REDIS_TIMEOUT_S,
        socket_timeout=REDIS_TIMEOUT_S,
    )


class RateLimitUnavailable(Exception):
    pass


class RateLimiter:
    """Fixed one-minute windows in Redis: key `rl:{scope}:{key}:{window}`."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis
        self._last_warning: dict[str, float] = {}

    @staticmethod
    def limit_for(scope: str, settings: Settings) -> int:
        return {
            "upload": settings.rate_limit_upload_per_min,
            "tools": settings.rate_limit_tools_per_min,
            "ip": settings.rate_limit_ip_per_min,
        }[scope]

    async def hit(self, scope: str, key: str, *, fail_open: bool) -> int | None:
        """Count one request. Returns Retry-After seconds when over the limit, else None.

        Redis down: None (fail open) or RateLimitUnavailable (fail closed).
        """
        now = _now()
        window = int(now) // WINDOW_S
        rkey = f"rl:{scope}:{key}:{window}"
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(rkey)
                pipe.expire(rkey, WINDOW_S)
                count, _ = await pipe.execute()
        except (RedisError, OSError) as exc:
            self._warn(scope, exc, fail_open)
            if fail_open:
                return None
            raise RateLimitUnavailable(scope) from exc
        if count <= self.limit_for(scope, get_settings()):
            return None
        return max(1, math.ceil((window + 1) * WINDOW_S - now))

    def _warn(self, scope: str, exc: Exception, fail_open: bool) -> None:
        now = time.monotonic()
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
        retry = await self.limiter.hit("ip", client_ip(Request(scope)), fail_open=True)
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
    """10 uploads (papers + images) per owner per minute; fails closed without Redis."""
    await _owner_limit(request, owner, "upload", fail_open=False)


async def tools_limit(request: Request, owner: Owner = Depends(current_owner)) -> None:
    """60 tool calls per owner per minute; fails open without Redis."""
    await _owner_limit(request, owner, "tools", fail_open=True)


# --- wiring ---------------------------------------------------------------------------------


def _docs_routes(app: FastAPI) -> None:
    openapi_url = f"{API_PREFIX}/openapi.json"

    @app.get(f"{API_PREFIX}/docs", include_in_schema=False)
    async def swagger():
        response = get_swagger_ui_html(openapi_url=openapi_url, title=f"{app.title} docs")
        response.headers["Content-Security-Policy"] = DOCS_CSP
        return response

    @app.get(f"{API_PREFIX}/redoc", include_in_schema=False)
    async def redoc():
        response = get_redoc_html(openapi_url=openapi_url, title=f"{app.title} docs")
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
