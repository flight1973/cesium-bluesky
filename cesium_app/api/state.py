"""REST endpoint for backend state flags.

Returns the state of various BlueSky toggles so the frontend
can keep its buttons in sync with what the sim is actually
doing — regardless of who changed the state (console, other
client, scenario file, etc.).
"""
from fastapi import APIRouter, Request

import bluesky as bs

router = APIRouter(prefix="/api/state", tags=["state"])


@router.get("")
async def get_state(request: Request) -> dict:
    """Return current backend toggle state.

    Returns:
        Dict with keys:
            trails_active: Whether trail recording is on.
            area_active: Name of active deletion area or null.
    """
    trails_active = False
    try:
        trails_active = bool(bs.traf.trails.active)
    except AttributeError:
        pass

    area_active: str | None = None
    try:
        from bluesky.plugins.area import Area
        inst = Area._instance
        if inst and inst.active:
            area_active = inst.delarea or None
    except (ImportError, AttributeError):
        pass

    return {
        "trails_active": trails_active,
        "area_active": area_active,
    }
