"""
Improved WebSocket router for real-time session management and user queue updates.
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


class SessionWebSocketManager:
    """Manages WebSocket connections for session updates with improved performance."""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self._broadcast_lock = asyncio.Lock()
        self._broadcast_queue = asyncio.Queue()
        self._is_broadcasting = False

        # Start background broadcast worker
        asyncio.create_task(self._broadcast_worker())

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.connections[session_id] = websocket
        logger.info(
            f"WebSocket connected for session {session_id}. Total connections: {len(self.connections)}"
        )

    def disconnect(self, session_id: str):
        """Remove a WebSocket connection."""
        if session_id in self.connections:
            del self.connections[session_id]
            logger.info(
                f"WebSocket disconnected for session {session_id}. Total connections: {len(self.connections)}"
            )

    async def send_message(self, session_id: str, message: dict) -> bool:
        """Send a message to a specific session."""
        if session_id not in self.connections:
            return False

        try:
            websocket = self.connections[session_id]
            await asyncio.wait_for(
                websocket.send_text(json.dumps(message)),
                timeout=2.0,  # Shorter timeout to prevent blocking
            )
            return True
        except (Exception, asyncio.TimeoutError) as e:
            logger.warning(f"Failed to send message to session {session_id}: {e}")
            self.disconnect(session_id)
            return False

    async def _broadcast_worker(self):
        """Background worker that processes broadcast requests."""
        while True:
            try:
                # Wait for broadcast request
                await self._broadcast_queue.get()

                # Process the broadcast
                await self._do_broadcast_queue_update()

            except Exception as e:
                logger.error(f"Broadcast worker error: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on persistent errors

    async def _do_broadcast_queue_update(self):
        """Actually perform the broadcast to all connected sessions."""
        if not self.connections:
            return

        try:
            queue_status = await session_manager.get_queue_status()
            session_ids = list(
                self.connections.keys()
            )  # Snapshot to avoid modification during iteration

            # Create all tasks first
            tasks = []
            for session_id in session_ids:
                if session_id in self.connections:  # Double-check session still exists
                    task = asyncio.create_task(
                        self._send_queue_update(session_id, queue_status)
                    )
                    tasks.append(task)

            # Execute all sends concurrently with shorter timeout
            if tasks:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=3.0
                )

        except asyncio.TimeoutError:
            logger.warning("Broadcast queue update timed out after 3 seconds")
        except Exception as e:
            logger.error(f"Error during broadcast queue update: {e}")

    async def _send_queue_update(self, session_id: str, queue_status: dict):
        """Send queue update to a specific session."""
        try:
            session_status = await session_manager.get_session_status(session_id)
            if session_status:
                message = {
                    "type": "queue_update",
                    "session_status": session_status,
                    "queue_status": queue_status,
                }
                await self.send_message(session_id, message)
        except Exception as e:
            logger.error(f"Error sending queue update to {session_id}: {e}")

    async def broadcast_queue_update(self):
        """Queue a broadcast request (non-blocking)."""
        try:
            # Add to queue without blocking
            self._broadcast_queue.put_nowait("broadcast_request")
        except asyncio.QueueFull:
            logger.warning("Broadcast queue is full, skipping broadcast")


# Global WebSocket manager
ws_manager = SessionWebSocketManager()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time session updates."""
    await ws_manager.connect(websocket, session_id)

    try:
        while True:
            # Listen for messages from client with timeout
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            if message.get("type") == "heartbeat":
                # Update session activity (non-blocking)
                asyncio.create_task(session_manager.update_session_activity(session_id))

                # Send current status back
                session_status = await session_manager.get_session_status(session_id)
                if session_status:
                    queue_status = await session_manager.get_queue_status()
                    response = {
                        "type": "status_update",
                        "session_status": session_status,
                        "queue_status": queue_status,
                    }
                    await websocket.send_text(json.dumps(response))

            elif message.get("type") == "disconnect":
                # User wants to disconnect
                logger.info(f"User requested disconnect for session {session_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        ws_manager.disconnect(session_id)
        # Remove session in background (non-blocking)
        asyncio.create_task(session_manager.remove_session(session_id))
        # Queue broadcast update (non-blocking)
        if ws_manager.connections:
            asyncio.create_task(ws_manager.broadcast_queue_update())


@router.post("/create")
async def create_session(user_id: str = Query(None)):
    """Create a new user session."""
    try:
        session_info = await session_manager.create_session(user_id)
        queue_status = await session_manager.get_queue_status()

        # Queue broadcast update in background (non-blocking)
        if ws_manager.connections:
            asyncio.create_task(ws_manager.broadcast_queue_update())

        return {"success": True, "session": session_info, "queue_status": queue_status}
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create session: {str(e)}"
        )


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
        removed = await session_manager.remove_session(session_id)

        # Always queue broadcast update (non-blocking)
        if ws_manager.connections:
            asyncio.create_task(ws_manager.broadcast_queue_update())

        if removed:
            return {"success": True, "message": "Session removed successfully"}
        else:
            logger.info(
                f"Session {session_id} was not found (may have already expired)"
            )
            return {
                "success": True,
                "message": "Session was already removed or expired",
            }

    except Exception as e:
        logger.error(f"Failed to remove session: {e}")
        # Still queue broadcast update even if there was an error
        try:
            asyncio.create_task(ws_manager.broadcast_queue_update())
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
        # Close WebSocket connections in background
        disconnected_count = 0
        session_ids = list(ws_manager.connections.keys())

        for session_id in session_ids:
            try:
                connection = ws_manager.connections[session_id]
                asyncio.create_task(connection.close(code=1000, reason="Session reset"))
                ws_manager.disconnect(session_id)
                disconnected_count += 1
            except Exception as e:
                logger.error(f"Error closing WebSocket for session {session_id}: {e}")

        # Reset all sessions
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
