"""WebSocket connection manager with topic-based subscriptions."""
import logging
import math

import orjson
from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


def _json_default(obj: object) -> object:
    """Fallback serializer for orjson.

    Converts NaN/Inf floats to None and numpy scalars
    to native Python types.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if hasattr(obj, 'item'):  # numpy scalar
        val = obj.item()
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return None
        return val
    if hasattr(obj, 'tolist'):  # numpy array
        return obj.tolist()
    raise TypeError(
        f'Object of type {type(obj).__name__} '
        'is not JSON serializable'
    )


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
            "ACDATA", "SIMINFO", "TRAILS", "CMDLOG",
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

        try:
            msg = orjson.dumps(
                {"topic": topic, "data": data},
                option=(
                    orjson.OPT_SERIALIZE_NUMPY
                    | orjson.OPT_NON_STR_KEYS
                ),
                default=_json_default,
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Serialization failed for %s: %s",
                topic, exc,
            )
            return

        disconnected: list[WebSocket] = []
        for ws, subs in self._connections.items():
            if topic not in subs:
                continue
            try:
                await ws.send_bytes(msg)
            except Exception:  # pylint: disable=broad-except
                # Client disconnected mid-send.
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        """Number of currently connected clients."""
        return len(self._connections)
