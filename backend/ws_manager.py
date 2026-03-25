"""
WebSocket manager for real-time dashboard updates.
Broadcasts events to connected clients when data changes.
"""
import asyncio
import json
import logging
from typing import Dict, Set
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str = "dashboard"):
        await websocket.accept()
        async with self._lock:
            if channel not in self.active_connections:
                self.active_connections[channel] = set()
            self.active_connections[channel].add(websocket)
        logger.info(f"WebSocket connected to channel '{channel}'. Active: {len(self.active_connections.get(channel, set()))}")

    async def disconnect(self, websocket: WebSocket, channel: str = "dashboard"):
        async with self._lock:
            if channel in self.active_connections:
                self.active_connections[channel].discard(websocket)
                if not self.active_connections[channel]:
                    del self.active_connections[channel]
        logger.info(f"WebSocket disconnected from channel '{channel}'.")

    async def broadcast(self, channel: str, event_type: str, data: dict = None):
        """Broadcast an event to all connections on a channel."""
        connections = self.active_connections.get(channel, set()).copy()
        if not connections:
            return

        message = json.dumps({
            "type": event_type,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        disconnected = []
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    self.active_connections.get(channel, set()).discard(conn)

    async def broadcast_stats_update(self):
        """Broadcast a signal that dashboard stats should be refreshed."""
        await self.broadcast("dashboard", "stats_update")

    async def broadcast_journey_update(self, journey_id: str, action: str = "updated"):
        """Broadcast journey change event."""
        await self.broadcast("dashboard", "journey_update", {"journey_id": journey_id, "action": action})

    async def broadcast_incident_update(self, journey_id: str):
        """Broadcast incident change event."""
        await self.broadcast("dashboard", "incident_update", {"journey_id": journey_id})

    async def broadcast_sync_update(self, stats: dict = None):
        """Broadcast sync completion event."""
        await self.broadcast("dashboard", "sync_update", stats or {})

    @property
    def connection_count(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())


# Singleton instance
ws_manager = ConnectionManager()
