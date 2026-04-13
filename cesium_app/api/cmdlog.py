"""REST endpoint for the server command log."""
from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/cmdlog", tags=["cmdlog"])


@router.get("")
async def get_command_log(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    """Return the most recent commands sent to the stack.

    Captures commands from all sources: REST endpoints,
    WebSocket client messages, scenario files, and internal
    BlueSky code.

    Args:
        limit: Max number of entries to return (1-500).

    Returns:
        List of entries, each with simt, utc, sender, command.
    """
    bridge = request.app.state.bridge
    return bridge.get_command_log(limit=limit)
