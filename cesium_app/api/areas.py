"""REST endpoints for area/shape definition and queries."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from bluesky.tools import areafilter

router = APIRouter(prefix="/api/areas", tags=["areas"])


class BoxArea(BaseModel):
    """Request body for creating a rectangular area.

    Attributes:
        name: Shape name (used for AREA activation).
        lat1: First corner latitude.
        lon1: First corner longitude.
        lat2: Opposite corner latitude.
        lon2: Opposite corner longitude.
        top: Optional top altitude (accepts FL350, 35000,
            1000ft, etc.).
        bottom: Optional bottom altitude.
        activate: If true, also activate as deletion area.
    """

    name: str
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    top: str | None = None
    bottom: str | None = None
    activate: bool = False


class PolyArea(BaseModel):
    """Request body for creating a polygonal area.

    Attributes:
        name: Shape name.
        coords: List of [lat, lon] pairs (3+ vertices).
        top: Optional top altitude.
        bottom: Optional bottom altitude.
        activate: If true, activate as deletion area.
    """

    name: str
    coords: list[list[float]] = Field(..., min_length=3)
    top: str | None = None
    bottom: str | None = None
    activate: bool = False


class CircleArea(BaseModel):
    """Request body for creating a circular area.

    Attributes:
        name: Shape name.
        lat: Center latitude.
        lon: Center longitude.
        radius: Radius in nautical miles.
        top: Optional top altitude.
        bottom: Optional bottom altitude.
        activate: If true, activate as deletion area.
    """

    name: str
    lat: float
    lon: float
    radius: float
    top: str | None = None
    bottom: str | None = None
    activate: bool = False


class ActivateArea(BaseModel):
    """Request body for activating a deletion area.

    Attributes:
        name: Shape name to activate.
    """

    name: str


def _bridge(request: Request):
    return request.app.state.bridge


@router.get("")
async def list_areas(request: Request) -> dict:
    """List all defined areas and the active area name.

    Returns:
        Dict with shapes (name → shape info) and the
        currently active deletion area name (or null).
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


@router.post("/box", status_code=201)
async def create_box(
    request: Request,
    body: BoxArea,
) -> dict:
    """Create a rectangular (Box) area.

    If top/bottom are omitted, the area is a full vertical
    column. If specified, the area is limited to that
    altitude band.
    """
    parts = [
        f"BOX {body.name}",
        f"{body.lat1}",
        f"{body.lon1}",
        f"{body.lat2}",
        f"{body.lon2}",
    ]
    if body.top or body.bottom:
        parts.append(body.top or "100000")
        parts.append(body.bottom or "0")
    cmd = ",".join(parts).replace(
        f"BOX {body.name},", f"BOX {body.name},", 1,
    )
    # Build as "BOX name,..." (first separator is comma).
    cmd = (
        f"BOX {body.name}," +
        ",".join(parts[1:])
    )
    _bridge(request).stack_command(cmd)
    if body.activate:
        _bridge(request).stack_command(
            f"AREA {body.name}",
        )
    return {"status": "ok", "command": cmd}


@router.post("/poly", status_code=201)
async def create_poly(
    request: Request,
    body: PolyArea,
) -> dict:
    """Create a polygonal area from a list of vertices.

    Each vertex is [lat, lon]. Minimum 3 vertices.
    If top/bottom are specified, uses POLYALT command.
    """
    coord_str = ",".join(
        f"{lat},{lon}" for lat, lon in body.coords
    )
    if body.top or body.bottom:
        t = body.top or "100000"
        b = body.bottom or "0"
        cmd = f"POLYALT {body.name},{t},{b},{coord_str}"
    else:
        cmd = f"POLY {body.name},{coord_str}"
    _bridge(request).stack_command(cmd)
    if body.activate:
        _bridge(request).stack_command(
            f"AREA {body.name}",
        )
    return {"status": "ok", "command": cmd}


@router.post("/circle", status_code=201)
async def create_circle(
    request: Request,
    body: CircleArea,
) -> dict:
    """Create a circular area.

    Radius is in nautical miles.
    """
    parts = [
        str(body.lat),
        str(body.lon),
        str(body.radius),
    ]
    if body.top or body.bottom:
        parts.append(body.top or "100000")
        parts.append(body.bottom or "0")
    cmd = f"CIRCLE {body.name}," + ",".join(parts)
    _bridge(request).stack_command(cmd)
    if body.activate:
        _bridge(request).stack_command(
            f"AREA {body.name}",
        )
    return {"status": "ok", "command": cmd}


@router.post("/activate")
async def activate_area(
    request: Request,
    body: ActivateArea,
) -> dict:
    """Set the active deletion area.

    Aircraft leaving this shape will be deleted from sim.
    """
    if body.name.upper() not in {
        k.upper() for k in areafilter.basic_shapes.keys()
    }:
        raise HTTPException(
            status_code=404,
            detail=f"Shape {body.name!r} not found",
        )
    _bridge(request).stack_command(f"AREA {body.name}")
    return {"status": "ok", "command": f"AREA {body.name}"}


@router.post("/deactivate")
async def deactivate_area(request: Request) -> dict:
    """Turn off the deletion area (shape stays defined)."""
    _bridge(request).stack_command("AREA OFF")
    return {"status": "ok", "command": "AREA OFF"}


@router.delete("/{name}")
async def delete_shape(
    request: Request,
    name: str,
) -> dict:
    """Delete a defined shape."""
    _bridge(request).stack_command(f"DEL {name}")
    return {"status": "ok", "command": f"DEL {name}"}
