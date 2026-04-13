"""REST endpoints for area/shape queries."""
from fastapi import APIRouter, Request

from bluesky.tools import areafilter

router = APIRouter(prefix="/api/areas", tags=["areas"])


@router.get("")
async def list_areas(request: Request) -> dict:
    """List all defined areas/shapes and the active area.

    Returns:
        Dict with shapes and active deletion area name.
    """
    shapes: dict[str, dict] = {}
    for name, shape in areafilter.basic_shapes.items():
        info: dict = {"name": name}
        if hasattr(shape, 'coordinates'):
            info["coordinates"] = list(
                shape.coordinates,
            )
        if hasattr(shape, 'top'):
            info["top"] = shape.top
        if hasattr(shape, 'bottom'):
            info["bottom"] = shape.bottom
        info["type"] = type(shape).__name__
        shapes[name] = info

    # Get active deletion area from the Area plugin.
    active: str | None = None
    try:
        from bluesky.plugins.area import Area
        inst = Area._instance
        if inst and inst.active:
            active = inst.delarea or None
    except (ImportError, AttributeError):
        pass

    return {
        "shapes": shapes,
        "active_area": active,
    }
