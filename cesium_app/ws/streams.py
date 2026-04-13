"""WebSocket endpoint and broadcast loop for real-time state."""
import asyncio
import logging

import orjson
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect

from cesium_app.sim.bridge import SimBridge
from cesium_app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
manager = ConnectionManager()

# Track sequence numbers to avoid re-sending stale data.
_last_acdata_seq: int = 0
_last_trails_seq: int = 0
_last_siminfo_seq: int = 0


@router.websocket("/ws/sim")
async def websocket_sim(ws: WebSocket) -> None:
    """Multiplexed WebSocket for simulation state streaming.

    Server -> Client::

        {"topic": "ACDATA", "data": {...}}
        {"topic": "SIMINFO", "data": {...}}
        {"topic": "TRAILS", "data": {...}}

    Client -> Server::

        {"action": "subscribe", "topics": [...]}
        {"action": "unsubscribe", "topics": [...]}
        {"action": "command", "command": "CRE ..."}
    """
    await manager.connect(ws)
    bridge: SimBridge = ws.app.state.bridge

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    ws.receive_text(), timeout=0.05,
                )
                await _handle_client_message(
                    ws, bridge, raw,
                )
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("WebSocket error: %s", exc)
    finally:
        manager.disconnect(ws)


async def _handle_client_message(
    ws: WebSocket,
    bridge: SimBridge,
    raw: str,
) -> None:
    """Process a message received from the client.

    Args:
        ws: The WebSocket connection.
        bridge: The SimBridge instance.
        raw: Raw JSON string from the client.
    """
    try:
        msg = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return

    action = msg.get("action", "")
    if action == "subscribe":
        manager.subscribe(ws, msg.get("topics", []))
    elif action == "unsubscribe":
        manager.unsubscribe(ws, msg.get("topics", []))
    elif action == "command":
        cmd = msg.get("command", "")
        if cmd:
            bridge.stack_command(cmd)


async def broadcast_loop(app: FastAPI) -> None:
    """Background task: read snapshots and broadcast.

    Runs at ~20 Hz to catch both 5 Hz ACDATA and 1 Hz
    SIMINFO / TRAILS.  Only sends when new data is available
    (sequence numbers changed).

    Args:
        app: The FastAPI application instance.
    """
    global _last_acdata_seq  # pylint: disable=global-statement
    global _last_trails_seq  # pylint: disable=global-statement
    global _last_siminfo_seq  # pylint: disable=global-statement

    bridge: SimBridge = app.state.bridge
    collector = bridge.collector

    while True:
        await asyncio.sleep(0.05)  # 20 Hz poll

        if manager.client_count == 0:
            continue

        latest = collector.get_latest()

        # ACDATA -- 5 Hz
        if (
            latest["acdata_seq"] != _last_acdata_seq
            and latest["acdata"] is not None
        ):
            _last_acdata_seq = latest["acdata_seq"]
            await manager.broadcast(
                "ACDATA", latest["acdata"],
            )

        # SIMINFO -- 1 Hz
        if (
            latest["siminfo_seq"] != _last_siminfo_seq
            and latest["siminfo"] is not None
        ):
            _last_siminfo_seq = latest["siminfo_seq"]
            await manager.broadcast(
                "SIMINFO", latest["siminfo"],
            )

        # TRAILS -- 1 Hz (consume to clear)
        if latest["trails_seq"] != _last_trails_seq:
            _last_trails_seq = latest["trails_seq"]
            trails = collector.consume_trails()
            if trails:
                await manager.broadcast("TRAILS", trails)
