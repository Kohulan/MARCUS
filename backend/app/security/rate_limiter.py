"""
Rate limiting implementation for MARCUS application.
Implements comprehensive rate limiting.
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limit rule configuration."""

    requests: int  # Number of requests allowed
    window: int  # Time window in seconds
    burst: int = 0  # Burst allowance (0 = no burst)
    penalty: int = 0  # Penalty seconds for violations


@dataclass
class ClientRecord:
    """Track rate limit state for a client."""

    requests: deque = field(default_factory=deque)
    violations: int = 0
    penalty_until: Optional[datetime] = None
    first_request: Optional[datetime] = None
    last_request: Optional[datetime] = None


class RateLimiter:
    """
    Advanced rate limiter with multiple strategies and progressive penalties.
    """

    # Default rate limit rules by endpoint pattern
    DEFAULT_RULES = {
        # File upload endpoints - more restrictive
        "upload": RateLimitRule(requests=5, window=60, burst=2, penalty=60),
        "pdf": RateLimitRule(requests=5, window=60, burst=1, penalty=30),
        # Processing endpoints - moderate limits
        "process": RateLimitRule(requests=10, window=60, burst=3, penalty=30),
        "ocsr": RateLimitRule(requests=15, window=60, burst=5, penalty=20),
        "depiction": RateLimitRule(requests=20, window=60, burst=10, penalty=15),
        # Session endpoints - lenient
        "session": RateLimitRule(requests=30, window=60, burst=10, penalty=10),
        "heartbeat": RateLimitRule(requests=60, window=60, burst=20, penalty=5),
        # Default for unmatched endpoints
        "default": RateLimitRule(requests=15, window=60, burst=5, penalty=20),
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.clients: Dict[str, ClientRecord] = defaultdict(ClientRecord)
        self.rules = self.DEFAULT_RULES.copy()
        self.stats = {
            "total_requests": 0,
            "blocked_requests": 0,
            "clients_tracking": 0,
            "violations_count": 0,
        }

        # Configuration from environment
        self._load_config()

        # Cleanup task
        self._cleanup_task = None
        if self.enabled:
            self._start_cleanup_task()

    def _load_config(self):
        """Load rate limiting configuration from environment."""
        try:
            # Check if rate limiting is enabled
            self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

            # Load custom rules from environment if provided
            custom_rules = os.getenv("RATE_LIMIT_RULES")
            if custom_rules:
                try:
                    rules_data = json.loads(custom_rules)
                    for endpoint, rule_data in rules_data.items():
                        self.rules[endpoint] = RateLimitRule(**rule_data)
                    logger.info(
                        f"Loaded custom rate limit rules for {len(rules_data)} endpoints"
                    )
                except Exception as e:
                    logger.error(f"Failed to parse custom rate limit rules: {e}")

        except Exception as e:
            logger.error(f"Error loading rate limit configuration: {e}")

    def _start_cleanup_task(self):
        """Start background cleanup task."""
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._cleanup_old_records())
        except RuntimeError:
            # No event loop running, cleanup will happen on demand
            pass

    async def _cleanup_old_records(self):
        """Cleanup old client records periodically."""
        while True:
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                current_time = datetime.now()

                # Remove old client records
                clients_to_remove = []
                for client_id, record in self.clients.items():
                    if (
                        record.last_request
                        and current_time - record.last_request > timedelta(hours=1)
                    ):
                        clients_to_remove.append(client_id)

                for client_id in clients_to_remove:
                    del self.clients[client_id]

                # Update stats
                self.stats["clients_tracking"] = len(self.clients)

                if clients_to_remove:
                    logger.debug(
                        f"Cleaned up {len(clients_to_remove)} old client records"
                    )

            except Exception as e:
                logger.error(f"Error in rate limit cleanup: {e}")
        try:
            while True:
                try:
                    await asyncio.sleep(300)  # Cleanup every 5 minutes
                    current_time = datetime.now()

                    # Remove old client records
                    clients_to_remove = []
                    for client_id, record in self.clients.items():
                        if (
                            record.last_request
                            and current_time - record.last_request > timedelta(hours=1)
                        ):
                            clients_to_remove.append(client_id)

                    for client_id in clients_to_remove:
                        del self.clients[client_id]

                    # Update stats
                    self.stats["clients_tracking"] = len(self.clients)

                    if clients_to_remove:
                        logger.debug(
                            f"Cleaned up {len(clients_to_remove)} old client records"
                        )

                except Exception as e:
                    logger.error(f"Error in rate limit cleanup: {e}")
        except asyncio.CancelledError:
            logger.info("Rate limit cleanup task cancelled. Exiting cleanup loop.")
            raise
    def get_endpoint_type(self, path: str) -> str:
        """Determine endpoint type from path for rule matching."""
        path_lower = path.lower()

        # Check specific patterns
        if "upload" in path_lower or "file" in path_lower:
            if "pdf" in path_lower:
                return "pdf"
            return "upload"
        elif "process" in path_lower:
            return "process"
        elif "ocsr" in path_lower:
            return "ocsr"
        elif "depiction" in path_lower or "depict" in path_lower:
            return "depiction"
        elif "session" in path_lower:
            if "heartbeat" in path_lower:
                return "heartbeat"
            return "session"

        return "default"

    def is_allowed(self, client_id: str, endpoint_path: str) -> Dict[str, Any]:
        """
        Check if request is allowed for client.

        Args:
            client_id: Client identifier (IP, session, user ID)
            endpoint_path: Request endpoint path

        Returns:
            dict: Result with allowed status and metadata
        """
        if not self.enabled:
            return {"allowed": True, "reason": "rate_limiting_disabled"}

        self.stats["total_requests"] += 1

        current_time = datetime.now()
        client_record = self.clients[client_id]
        endpoint_type = self.get_endpoint_type(endpoint_path)
        rule = self.rules.get(endpoint_type, self.rules["default"])

        # Update client tracking
        if not client_record.first_request:
            client_record.first_request = current_time
        client_record.last_request = current_time

        # Check if client is in penalty period
        if client_record.penalty_until and current_time < client_record.penalty_until:
            self.stats["blocked_requests"] += 1
            remaining_penalty = (
                client_record.penalty_until - current_time
            ).total_seconds()
            return {
                "allowed": False,
                "reason": "penalty_period",
                "retry_after": int(remaining_penalty),
                "endpoint_type": endpoint_type,
                "rule": rule.__dict__,
            }

        # Clean old requests outside the window
        window_start = current_time - timedelta(seconds=rule.window)
        while client_record.requests and client_record.requests[0] < window_start:
            client_record.requests.popleft()

        # Check if request count exceeds limit
        current_requests = len(client_record.requests)

        # Apply burst allowance
        effective_limit = rule.requests + rule.burst

        if current_requests >= effective_limit:
            # Rate limit exceeded
            client_record.violations += 1
            self.stats["blocked_requests"] += 1
            self.stats["violations_count"] += 1

            # Apply progressive penalty
            penalty_seconds = rule.penalty * min(
                client_record.violations, 5
            )  # Cap at 5x
            client_record.penalty_until = current_time + timedelta(
                seconds=penalty_seconds
            )

            logger.warning(
                f"Rate limit exceeded for {client_id} on {endpoint_type}: "
                f"{current_requests}/{effective_limit} requests. "
                f"Penalty: {penalty_seconds}s (violation #{client_record.violations})"
            )

            return {
                "allowed": False,
                "reason": "rate_limit_exceeded",
                "retry_after": penalty_seconds,
                "current_requests": current_requests,
                "limit": effective_limit,
                "window": rule.window,
                "endpoint_type": endpoint_type,
                "violations": client_record.violations,
                "rule": rule.__dict__,
            }

        # Request allowed - record it
        client_record.requests.append(current_time)

        return {
            "allowed": True,
            "reason": "within_limits",
            "current_requests": current_requests + 1,
            "limit": effective_limit,
            "window": rule.window,
            "endpoint_type": endpoint_type,
            "remaining": effective_limit - current_requests - 1,
            "rule": rule.__dict__,
        }

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get statistics for a specific client."""
        client_record = self.clients.get(client_id)
        if not client_record:
            return {"exists": False}

        current_time = datetime.now()

        return {
            "exists": True,
            "first_request": (
                client_record.first_request.isoformat()
                if client_record.first_request
                else None
            ),
            "last_request": (
                client_record.last_request.isoformat()
                if client_record.last_request
                else None
            ),
            "violations": client_record.violations,
            "in_penalty": bool(
                client_record.penalty_until
                and current_time < client_record.penalty_until
            ),
            "penalty_until": (
                client_record.penalty_until.isoformat()
                if client_record.penalty_until
                else None
            ),
            "current_requests": len(client_record.requests),
        }

    def reset_client(self, client_id: str) -> bool:
        """Reset rate limiting for a specific client."""
        if client_id in self.clients:
            del self.clients[client_id]
            logger.info(f"Reset rate limiting for client: {client_id}")
            return True
        return False

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global rate limiting statistics."""
        return {
            **self.stats,
            "enabled": self.enabled,
            "clients_tracking": len(self.clients),
            "rules_configured": len(self.rules),
            "rules": {name: rule.__dict__ for name, rule in self.rules.items()},
        }

    def update_rule(self, endpoint_type: str, rule: RateLimitRule):
        """Update rate limiting rule for an endpoint type."""
        self.rules[endpoint_type] = rule
        logger.info(f"Updated rate limit rule for {endpoint_type}: {rule}")

    def enable(self):
        """Enable rate limiting."""
        self.enabled = True
        if not self._cleanup_task:
            self._start_cleanup_task()
        logger.info("Rate limiting enabled")

    def disable(self):
        """Disable rate limiting."""
        self.enabled = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        logger.info("Rate limiting disabled")


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_client_identifier(request) -> str:
    """
    Extract client identifier from request.
    Priority: Session ID > User ID > IP Address
    """
    try:
        # Try to get session ID first
        session_id = None
        if hasattr(request.state, "session_id"):
            session_id = request.state.session_id
        elif hasattr(request, "headers"):
            session_id = request.headers.get("X-Session-ID")

        if session_id:
            return f"session:{session_id}"

        # Try to get user ID
        user_id = None
        if hasattr(request.state, "user_id"):
            user_id = request.state.user_id
        elif hasattr(request, "query_params"):
            user_id = request.query_params.get("user_id")

        if user_id:
            return f"user:{user_id}"

        # Fall back to IP address
        client_ip = None
        if hasattr(request, "client") and request.client:
            client_ip = request.client.host
        elif hasattr(request, "headers"):
            # Check for forwarded IP headers
            client_ip = (
                request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.headers.get("X-Real-IP")
                or request.headers.get("CF-Connecting-IP")
            )

        return f"ip:{client_ip or 'unknown'}"

    except Exception as e:
        logger.error(f"Error extracting client identifier: {e}")
        return "ip:unknown"
