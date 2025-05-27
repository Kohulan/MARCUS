"""
WebSocket router for real-time session management and user queue updates.
"""

import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import JSONResponse

from app.modules.session_manager import session_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])

# Store active WebSocket connections by session_id
active_connections: Dict[str, WebSocket] = {}


class SessionWebSocketManager:
    """Manages WebSocket connections for session updates."""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.connections[session_id] = websocket
        logger.info(f"WebSocket connected for session {session_id}")

    def disconnect(self, session_id: str):
        """Remove a WebSocket connection."""
        if session_id in self.connections:
            del self.connections[session_id]
            logger.info(f"WebSocket disconnected for session {session_id}")

    async def send_message(self, session_id: str, message: dict):
        """Send a message to a specific session."""
        if session_id in self.connections:
            try:
                await self.connections[session_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send message to session {session_id}: {e}")
                self.disconnect(session_id)

    async def broadcast_queue_update(self):
        """Broadcast queue status to all connected sessions."""
        queue_status = await session_manager.get_queue_status()

        # Send updates to all waiting sessions
        for session_id in list(self.connections.keys()):
            session_status = await session_manager.get_session_status(session_id)
            if session_status:
                message = {
                    "type": "queue_update",
                    "session_status": session_status,
                    "queue_status": queue_status,
                }
                await self.send_message(session_id, message)


# Global WebSocket manager
ws_manager = SessionWebSocketManager()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time session updates."""
    await ws_manager.connect(websocket, session_id)

    try:
        while True:
            # Listen for heartbeat messages from client
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "heartbeat":
                # Update session activity
                await session_manager.update_session_activity(session_id)

                # Send current status back
                session_status = await session_manager.get_session_status(session_id)
                queue_status = await session_manager.get_queue_status()

                response = {
                    "type": "status_update",
                    "session_status": session_status,
                    "queue_status": queue_status,
                }
                await websocket.send_text(json.dumps(response))

            elif message.get("type") == "disconnect":
                # User wants to disconnect - remove session immediately
                logger.info(f"User requested disconnect for session {session_id}")
                await session_manager.remove_session(session_id)
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        ws_manager.disconnect(session_id)
        # Remove session immediately when WebSocket disconnects
        # This ensures queue advances quickly when users close tabs
        await session_manager.remove_session(session_id)
        # Broadcast update to remaining users
        if ws_manager.connections:
            await ws_manager.broadcast_queue_update()


@router.post("/create")
async def create_session(user_id: str = Query(None)):
    """Create a new user session."""
    try:
        session_info = await session_manager.create_session(user_id)
        queue_status = await session_manager.get_queue_status()

        # Broadcast queue update to all connected users (only if there are connections)
        if ws_manager.connections:
            await ws_manager.broadcast_queue_update()

        return {"success": True, "session": session_info, "queue_status": queue_status}
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.get("/status/{session_id}")
async def get_session_status(session_id: str):
    """Get current status of a session."""
    try:
        session_status = await session_manager.get_session_status(session_id)
        if not session_status:
            raise HTTPException(status_code=404, detail="Session not found")

        queue_status = await session_manager.get_queue_status()

        return {
            "success": True,
            "session_status": session_status,
            "queue_status": queue_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get session status")


@router.post("/remove/{session_id}")
async def remove_session_post(session_id: str):
    """Remove a session (POST method for better browser compatibility)."""
    return await remove_session(session_id)


@router.delete("/remove/{session_id}")
async def remove_session(session_id: str):
    """Remove a session."""
    try:
        # Clean up expired sessions first
        await session_manager.cleanup_expired_sessions()

        removed = await session_manager.remove_session(session_id)

        # Always broadcast queue update regardless of whether session was found
        if ws_manager.connections:
            await ws_manager.broadcast_queue_update()

        if removed:
            return {"success": True, "message": "Session removed successfully"}
        else:
            # Session might have already expired or been removed
            logger.info(
                f"Session {session_id} was not found (may have already expired)"
            )
            return {
                "success": True,
                "message": "Session was already removed or expired",
            }

    except Exception as e:
        logger.error(f"Failed to remove session: {e}")
        # Still broadcast update even if there was an error
        try:
            await ws_manager.broadcast_queue_update()
        except:
            pass
        raise HTTPException(status_code=500, detail="Failed to remove session")


@router.get("/queue")
async def get_queue_status():
    """Get overall queue status."""
    try:
        queue_status = await session_manager.get_queue_status()
        return {"success": True, "queue_status": queue_status}
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get queue status")


@router.post("/heartbeat/{session_id}")
async def session_heartbeat(session_id: str):
    """Update session activity timestamp."""
    try:
        updated = await session_manager.update_session_activity(session_id)

        if updated:
            session_status = await session_manager.get_session_status(session_id)
            return {"success": True, "session_status": session_status}
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session activity: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session activity")


@router.post("/reset")
async def reset_all_sessions():
    """Reset all sessions - clear active sessions and waiting queue."""
    try:
        # Close any WebSocket connections first
        disconnected_count = 0
        for session_id in list(ws_manager.connections.keys()):
            try:
                connection = ws_manager.connections[session_id]
                await connection.close(code=1000, reason="Session reset")
                ws_manager.disconnect(session_id)
                disconnected_count += 1
            except Exception as e:
                logger.error(f"Error closing WebSocket for session {session_id}: {e}")

        # Then reset all sessions
        queue_status = await session_manager.reset_all_sessions()

        logger.info(
            f"Reset complete. Closed {disconnected_count} WebSocket connections."
        )

        return {
            "success": True,
            "message": f"All sessions have been reset. Closed {disconnected_count} WebSocket connections.",
            "queue_status": queue_status,
        }
    except Exception as e:
        logger.error(f"Failed to reset sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset sessions")
