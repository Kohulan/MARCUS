"""
Session middleware for MARCUS application.
Validates active sessions and tracks API usage.
"""

import time
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.modules.session_manager import session_manager
import logging

logger = logging.getLogger(__name__)


class SessionMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce session management and track API usage."""

    def __init__(self, app, exempt_paths=None):
        super().__init__(app)
        # Paths that don't require active session validation
        self.exempt_paths = exempt_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/session",  # Session management endpoints
            "/",
            "/latest",
            "/v1",
        ]

    async def dispatch(self, request: Request, call_next):
        # Check if this path is exempt from session validation
        path = request.url.path

        # Allow exempt paths
        if any(path.startswith(exempt) for exempt in self.exempt_paths):
            return await call_next(request)

        # For API endpoints, validate session
        if path.startswith("/v1/") or path.startswith("/latest/"):
            session_id = self.extract_session_id(request)

            if not session_id:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Session ID required. Please create a session first.",
                        "error_code": "NO_SESSION",
                    },
                )

            # Validate session is active
            session_status = await session_manager.get_session_status(session_id)

            if not session_status:
                return JSONResponse(
                    status_code=404,
                    content={
                        "detail": "Session not found or expired.",
                        "error_code": "SESSION_NOT_FOUND",
                    },
                )

            if session_status.get("status") != "active":
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Session is not active. Please wait in queue.",
                        "error_code": "SESSION_NOT_ACTIVE",
                        "queue_position": session_status.get("queue_position"),
                        "estimated_wait_time": session_status.get(
                            "estimated_wait_time"
                        ),
                    },
                )

            # Update session activity
            await session_manager.update_session_activity(session_id)

            # Add session info to request state for use in endpoints
            request.state.session_id = session_id
            request.state.session_status = session_status

        # Continue processing request
        response = await call_next(request)

        # Add session info to response headers for debugging
        if hasattr(request.state, "session_id"):
            response.headers["X-Session-ID"] = request.state.session_id
            response.headers["X-Session-Status"] = "active"

        return response

    def extract_session_id(self, request: Request) -> str:
        """Extract session ID from request headers or query parameters."""
        # Check headers first
        session_id = request.headers.get("X-Session-ID")
        if session_id:
            return session_id

        # Check query parameters
        session_id = request.query_params.get("session_id")
        if session_id:
            return session_id

        # Check cookies
        session_id = request.cookies.get("marcus_session_id")
        if session_id:
            return session_id

        return None
