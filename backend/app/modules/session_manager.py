"""
Improved Session Manager for MARCUS Application
Handles user concurrency limits and waiting queue management with better performance.
"""

import asyncio
import time
import uuid
from typing import Dict, Set, Optional, List
from datetime import datetime, timedelta
import logging
from collections import deque

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages user sessions and enforces concurrency limits."""

    def __init__(self, max_concurrent_users: int = 3):
        self.max_concurrent_users = max_concurrent_users
        self.active_sessions: Dict[str, dict] = {}  # session_id -> session_info
        self.waiting_queue: deque = deque()  # Deque for better performance
        self.session_timeout = 300  # 5 minutes timeout instead of 1 minute
        self._session_lock = asyncio.Lock()  # For session operations
        self._cleanup_lock = asyncio.Lock()  # Separate lock for cleanup
        self._last_cleanup = time.time()
        self._cleanup_interval = 30  # Run cleanup every 30 seconds

        # Start background cleanup task
        asyncio.create_task(self._background_cleanup())

    async def _background_cleanup(self):
        """Background task to periodically clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired_sessions_background()
            except Exception as e:
                logger.error(f"Background cleanup error: {e}")

    async def _cleanup_expired_sessions_background(self):
        """Background cleanup that doesn't block session operations."""
        async with self._cleanup_lock:
            current_time = time.time()
            expired_sessions = []

            # Find expired active sessions
            for session_id, session_info in list(self.active_sessions.items()):
                if current_time - session_info["last_activity"] > self.session_timeout:
                    expired_sessions.append(session_id)

            # Remove expired sessions and promote waiting users
            for session_id in expired_sessions:
                logger.info(
                    f"Background cleanup: Session {session_id} expired due to inactivity"
                )
                async with self._session_lock:
                    if session_id in self.active_sessions:
                        del self.active_sessions[session_id]
                        # Promote waiting user if available
                        if (
                            self.waiting_queue
                            and len(self.active_sessions) < self.max_concurrent_users
                        ):
                            await self._promote_next_user()

            # Clean up expired waiting sessions
            waiting_queue_list = list(self.waiting_queue)
            self.waiting_queue.clear()

            for session in waiting_queue_list:
                if current_time - session["last_activity"] <= self.session_timeout:
                    self.waiting_queue.append(session)

            # Update queue positions
            for i, session in enumerate(self.waiting_queue):
                session["queue_position"] = i + 1

    async def create_session(self, user_id: Optional[str] = None) -> dict:
        """Create a new session for a user with improved error handling."""
        try:
            return await asyncio.wait_for(
                self._create_session_internal(user_id), timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("Session creation timed out after 5 seconds")
            raise Exception("Session creation timed out - server may be overloaded")
        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            raise

    async def _create_session_internal(self, user_id: Optional[str] = None) -> dict:
        """Internal session creation with optimized locking."""
        session_id = str(uuid.uuid4())
        current_time = time.time()

        session_info = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": current_time,
            "last_activity": current_time,
            "status": "waiting",
        }

        async with self._session_lock:
            # Light cleanup only if needed (not full cleanup)
            if current_time - self._last_cleanup > self._cleanup_interval:
                await self._light_cleanup()
                self._last_cleanup = current_time

            # Check if we can activate immediately
            if len(self.active_sessions) < self.max_concurrent_users:
                session_info["status"] = "active"
                self.active_sessions[session_id] = session_info
                logger.info(
                    f"Session {session_id} activated immediately. Active sessions: {len(self.active_sessions)}"
                )
            else:
                # Add to waiting queue
                self.waiting_queue.append(session_info)
                session_info["queue_position"] = len(self.waiting_queue)
                logger.info(
                    f"Session {session_id} added to queue at position {session_info['queue_position']}"
                )

            return session_info.copy()  # Return a copy to avoid external modifications

    async def _light_cleanup(self):
        """Quick cleanup that only removes obviously expired sessions."""
        current_time = time.time()
        expired_count = 0

        # Quick check for very old sessions only
        very_old_threshold = self.session_timeout * 2  # Only remove very old sessions

        for session_id in list(self.active_sessions.keys()):
            if (
                current_time - self.active_sessions[session_id]["last_activity"]
                > very_old_threshold
            ):
                del self.active_sessions[session_id]
                expired_count += 1

        if expired_count > 0:
            logger.info(f"Light cleanup removed {expired_count} very old sessions")

    async def _promote_next_user(self):
        """Promote the next user from waiting queue to active (must be called with session lock)."""
        if self.waiting_queue and len(self.active_sessions) < self.max_concurrent_users:
            next_session = self.waiting_queue.popleft()
            next_session["status"] = "active"
            next_session["activated_at"] = time.time()
            self.active_sessions[next_session["session_id"]] = next_session
            logger.info(
                f"Session {next_session['session_id']} promoted from queue to active"
            )

            # Update queue positions for remaining waiting users
            for i, session in enumerate(self.waiting_queue):
                session["queue_position"] = i + 1

            return next_session
        return None

    async def update_session_activity(self, session_id: str) -> bool:
        """Update the last activity timestamp for a session."""
        current_time = time.time()

        # Check active sessions first (most common case)
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["last_activity"] = current_time
            return True

        # Check waiting queue (less common, so do it after)
        for session in self.waiting_queue:
            if session["session_id"] == session_id:
                session["last_activity"] = current_time
                return True

        return False

    async def remove_session(self, session_id: str) -> bool:
        """Remove a session and promote waiting users if applicable."""
        async with self._session_lock:
            removed = False
            promoted_session = None

            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                removed = True
                logger.info(
                    f"Session {session_id} removed from active sessions. Active sessions: {len(self.active_sessions)}"
                )

                # Promote waiting user if we have space
                if self.waiting_queue:
                    promoted_session = await self._promote_next_user()

            # Remove from waiting queue
            original_queue = list(self.waiting_queue)
            self.waiting_queue.clear()

            for session in original_queue:
                if session["session_id"] != session_id:
                    self.waiting_queue.append(session)
                else:
                    removed = True

            # Update queue positions
            for i, session in enumerate(self.waiting_queue):
                session["queue_position"] = i + 1

            return removed

    async def get_session_status(self, session_id: str) -> Optional[dict]:
        """Get current status of a session."""
        # Check active sessions first
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id].copy()
            session["active_users_count"] = len(self.active_sessions)
            return session

        # Check waiting queue
        for i, session in enumerate(self.waiting_queue):
            if session["session_id"] == session_id:
                session_copy = session.copy()
                session_copy["queue_position"] = i + 1
                session_copy["active_users_count"] = len(self.active_sessions)
                session_copy["estimated_wait_time"] = self._estimate_wait_time(i + 1)
                return session_copy

        return None

    async def get_queue_status(self) -> dict:
        """Get overall queue and session status."""
        return {
            "active_sessions": len(self.active_sessions),
            "max_concurrent_users": self.max_concurrent_users,
            "waiting_queue_length": len(self.waiting_queue),
            "available_slots": max(
                0, self.max_concurrent_users - len(self.active_sessions)
            ),
        }

    def _estimate_wait_time(self, queue_position: int) -> int:
        """Estimate wait time in seconds based on queue position."""
        # More conservative estimate: assume average session length of 15 minutes
        avg_session_duration = 900  # 15 minutes in seconds
        return queue_position * (avg_session_duration // self.max_concurrent_users)

    async def reset_all_sessions(self):
        """Reset all sessions - clear active sessions and waiting queue."""
        async with self._session_lock:
            logger.info(
                f"Resetting all sessions. Active: {len(self.active_sessions)}, Waiting: {len(self.waiting_queue)}"
            )

            self.active_sessions.clear()
            self.waiting_queue.clear()

            logger.info("All sessions have been reset")
            return {
                "active_sessions": 0,
                "waiting_queue_length": 0,
                "max_concurrent_users": self.max_concurrent_users,
                "available_slots": self.max_concurrent_users,
            }

    # Legacy method for compatibility
    async def cleanup_expired_sessions(self):
        """Public method to clean up expired sessions."""
        await self._cleanup_expired_sessions_background()


# Global session manager instance
session_manager = SessionManager(max_concurrent_users=3)
