"""WebSocket connection manager with topic-based subscriptions."""
import logging

import orjson
from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and topic broadcasts.

    Each connected client maintains a set of subscribed topics.
    The ``broadcast`` method sends only to clients subscribed to
    the given topic.
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}

    async def connect(self, ws: WebSocket) -> None:
        """Accept a WebSocket and register default subs."""
        await ws.accept()
        self._connections[ws] = {
            "ACDATA", "SIMINFO", "TRAILS",
        }
        logger.info(
            "WebSocket client connected (%d total)",
            len(self._connections),
        )

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from the connection pool."""
        self._connections.pop(ws, None)
        logger.info(
            "WebSocket client disconnected (%d remaining)",
            len(self._connections),
        )

    def subscribe(
        self,
        ws: WebSocket,
        topics: list[str],
    ) -> None:
        """Replace a client's topic subscriptions."""
        if ws in self._connections:
            self._connections[ws] = {
                t.upper() for t in topics
            }

    def unsubscribe(
        self,
        ws: WebSocket,
        topics: list[str],
    ) -> None:
        """Remove topics from a client's subscriptions."""
        if ws in self._connections:
            self._connections[ws] -= {
                t.upper() for t in topics
            }

    async def broadcast(
        self,
        topic: str,
        data: dict,
    ) -> None:
        """Send a message to all subscribed clients.

        Args:
            topic: The topic name (e.g. "ACDATA").
            data: The payload dict to serialize as JSON.
        """
        if not self._connections:
            return

        msg = orjson.dumps({"topic": topic, "data": data})
        disconnected: list[WebSocket] = []
        for ws, subs in self._connections.items():
            if topic not in subs:
                continue
            try:
                await ws.send_bytes(msg)
            except RuntimeError:
                # Client disconnected during send.
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        """Number of currently connected clients."""
        return len(self._connections)
