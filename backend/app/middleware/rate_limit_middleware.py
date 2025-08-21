"""
Rate limiting middleware for MARCUS application.
Implements rate limiting middleware.
"""

import logging
from typing import Callable, Dict, Any
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.security.rate_limiter import rate_limiter, get_client_identifier

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce rate limiting across the application.
    """

    def __init__(self, app, exempt_paths: list = None, enabled: bool = True):
        """
        Initialize rate limiting middleware.

        Args:
            app: FastAPI application instance
            exempt_paths: List of paths exempt from rate limiting
            enabled: Whether rate limiting is enabled
        """
        super().__init__(app)
        self.enabled = enabled
        self.exempt_paths = exempt_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/",
            "/favicon.ico",
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through rate limiting checks.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response: HTTP response
        """
        # Skip rate limiting if disabled
        if not self.enabled or not rate_limiter.enabled:
            return await call_next(request)

        path = request.url.path

        # Check if path is exempt from rate limiting
        if self._is_exempt_path(path):
            return await call_next(request)

        # Get client identifier
        client_id = get_client_identifier(request)

        # Check rate limit
        rate_check = rate_limiter.is_allowed(client_id, path)

        if not rate_check["allowed"]:
            # Rate limit exceeded - return error response
            return self._create_rate_limit_response(rate_check, client_id, path)

        # Add rate limit headers to response
        response = await call_next(request)
        self._add_rate_limit_headers(response, rate_check)

        # Log rate limit info if high usage
        remaining = rate_check.get("remaining", 0)
        if remaining <= 3:  # Warn when close to limit
            logger.warning(
                f"Client {client_id} approaching rate limit on {rate_check['endpoint_type']}: "
                f"{rate_check['current_requests']}/{rate_check['limit']} requests"
            )

        return response

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        return any(path.startswith(exempt) for exempt in self.exempt_paths)

    def _create_rate_limit_response(
        self, rate_check: Dict[str, Any], client_id: str, path: str
    ) -> JSONResponse:
        """Create rate limit exceeded response."""
        reason = rate_check.get("reason", "unknown")
        retry_after = rate_check.get("retry_after", 60)
        endpoint_type = rate_check.get("endpoint_type", "unknown")

        # Log rate limit violation
        logger.warning(
            f"Rate limit exceeded - Client: {client_id}, Path: {path}, "
            f"Type: {endpoint_type}, Reason: {reason}"
        )

        # Create response based on reason
        if reason == "penalty_period":
            detail = "You are currently in a penalty period due to rate limit violations. Please wait before trying again."
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        else:
            current_requests = rate_check.get("current_requests", 0)
            limit = rate_check.get("limit", 0)
            window = rate_check.get("window", 60)
            violations = rate_check.get("violations", 0)

            detail = (
                f"Rate limit exceeded for {endpoint_type} endpoint. "
                f"You have made {current_requests}/{limit} requests in the last {window} seconds."
            )

            if violations > 1:
                detail += f" Repeated violations ({violations}) will result in longer penalties."

            status_code = status.HTTP_429_TOO_MANY_REQUESTS

        headers = {
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(rate_check.get("limit", 0)),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + retry_after),
            "X-RateLimit-Type": endpoint_type,
        }

        return JSONResponse(
            status_code=status_code,
            content={
                "detail": detail,
                "error_code": "RATE_LIMIT_EXCEEDED",
                "retry_after": retry_after,
                "endpoint_type": endpoint_type,
                "current_requests": rate_check.get("current_requests", 0),
                "limit": rate_check.get("limit", 0),
                "window": rate_check.get("window", 60),
            },
            headers=headers,
        )

    def _add_rate_limit_headers(self, response: Response, rate_check: Dict[str, Any]):
        """Add rate limiting headers to response."""
        try:
            import time

            limit = rate_check.get("limit", 0)
            remaining = rate_check.get("remaining", 0)
            window = rate_check.get("window", 60)
            endpoint_type = rate_check.get("endpoint_type", "default")

            # Add standard rate limit headers
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window)
            response.headers["X-RateLimit-Type"] = endpoint_type

            # Add custom headers for debugging
            response.headers["X-RateLimit-Current"] = str(
                rate_check.get("current_requests", 0)
            )
            response.headers["X-RateLimit-Window"] = str(window)

        except Exception as e:
            logger.error(f"Error adding rate limit headers: {e}")


# Import time module at module level
import time
