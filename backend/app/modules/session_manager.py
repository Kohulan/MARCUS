"""
Session Manager for MARCUS Application
Handles user concurrency limits and waiting queue management.
"""

import asyncio
import time
import uuid
from typing import Dict, Set, Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages user sessions and enforces concurrency limits."""

    def __init__(self, max_concurrent_users: int = 3):
        self.max_concurrent_users = max_concurrent_users
        self.active_sessions: Dict[str, dict] = {}  # session_id -> session_info
        self.waiting_queue: List[dict] = []  # List of waiting users
        self.session_timeout = 300  # 5 minutes timeout for inactive sessions
        self._lock = asyncio.Lock()

    async def create_session(self, user_id: Optional[str] = None) -> dict:
        """
        Create a new session for a user.
        Returns session info with status (active, waiting) and position if waiting.
        """
        async with self._lock:
            session_id = str(uuid.uuid4())
            current_time = time.time()

            # Clean up expired sessions first
            await self._cleanup_expired_sessions()

            session_info = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": current_time,
                "last_activity": current_time,
                "status": "waiting",
            }

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

            return session_info

    async def update_session_activity(self, session_id: str) -> bool:
        """Update the last activity timestamp for a session."""
        async with self._lock:
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["last_activity"] = time.time()
                return True

            # Check waiting queue
            for session in self.waiting_queue:
                if session["session_id"] == session_id:
                    session["last_activity"] = time.time()
                    return True

            return False

    async def remove_session(self, session_id: str) -> bool:
        """Remove a session and promote waiting users if applicable."""
        async with self._lock:
            removed = False

            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                removed = True
                logger.info(
                    f"Session {session_id} removed from active sessions. Active sessions: {len(self.active_sessions)}"
                )

            # Remove from waiting queue
            self.waiting_queue = [
                s for s in self.waiting_queue if s["session_id"] != session_id
            ]

            # Promote waiting user if we have space
            if (
                removed
                and self.waiting_queue
                and len(self.active_sessions) < self.max_concurrent_users
            ):
                next_session = self.waiting_queue.pop(0)
                next_session["status"] = "active"
                next_session["activated_at"] = time.time()
                self.active_sessions[next_session["session_id"]] = next_session
                logger.info(
                    f"Session {next_session['session_id']} promoted from queue to active"
                )

                # Update queue positions for remaining waiting users
                for i, session in enumerate(self.waiting_queue):
                    session["queue_position"] = i + 1

            return removed

    async def get_session_status(self, session_id: str) -> Optional[dict]:
        """Get current status of a session."""
        async with self._lock:
            # Check active sessions
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
                    session_copy["estimated_wait_time"] = self._estimate_wait_time(
                        i + 1
                    )
                    return session_copy

            return None

    async def get_queue_status(self) -> dict:
        """Get overall queue and session status."""
        async with self._lock:
            await self._cleanup_expired_sessions()

            return {
                "active_sessions": len(self.active_sessions),
                "max_concurrent_users": self.max_concurrent_users,
                "waiting_queue_length": len(self.waiting_queue),
                "available_slots": max(
                    0, self.max_concurrent_users - len(self.active_sessions)
                ),
            }

    async def cleanup_expired_sessions(self):
        """Public method to clean up expired sessions."""
        return await self._cleanup_expired_sessions()

    async def _cleanup_expired_sessions(self):
        """Remove sessions that have been inactive for too long."""
        current_time = time.time()
        expired_sessions = []

        # Check active sessions for expiration
        for session_id, session_info in self.active_sessions.items():
            if current_time - session_info["last_activity"] > self.session_timeout:
                expired_sessions.append(session_id)

        # Remove expired active sessions
        for session_id in expired_sessions:
            logger.info(f"Session {session_id} expired due to inactivity")
            await self.remove_session(session_id)

        # Clean up expired waiting sessions
        self.waiting_queue = [
            session
            for session in self.waiting_queue
            if current_time - session["last_activity"] <= self.session_timeout
        ]

        # Update queue positions after cleanup
        for i, session in enumerate(self.waiting_queue):
            session["queue_position"] = i + 1

    def _estimate_wait_time(self, queue_position: int) -> int:
        """Estimate wait time in seconds based on queue position."""
        # Rough estimate: assume average session length of 30 minutes
        avg_session_duration = 1800  # 30 minutes in seconds
        return queue_position * (avg_session_duration // self.max_concurrent_users)

    async def reset_all_sessions(self):
        """Reset all sessions - clear active sessions and waiting queue."""
        async with self._lock:
            logger.info(
                f"Resetting all sessions. Active: {len(self.active_sessions)}, Waiting: {len(self.waiting_queue)}"
            )

            # Clear all active sessions
            self.active_sessions.clear()

            # Clear waiting queue
            self.waiting_queue.clear()

            logger.info("All sessions have been reset")
            return {
                "active_sessions": 0,
                "waiting_queue_length": 0,
                "max_concurrent_users": self.max_concurrent_users,
                "available_slots": self.max_concurrent_users,
            }


# Global session manager instance
session_manager = SessionManager(max_concurrent_users=3)
