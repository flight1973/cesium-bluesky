"""REST endpoints for aircraft traffic management."""
from fastapi import APIRouter, HTTPException, Request

from cesium_app.models.aircraft import AddWaypoint
from cesium_app.models.aircraft import AircraftCreate
from cesium_app.models.aircraft import AircraftSetValue
from cesium_app.models.aircraft import AircraftState
from cesium_app.models.aircraft import AircraftToggle
from cesium_app.models.aircraft import RouteData
from cesium_app.sim.bridge import SimBridge

router = APIRouter(
    prefix="/api/aircraft",
    tags=["aircraft"],
)


def _bridge(request: Request) -> SimBridge:
    """Extract the SimBridge from app state."""
    return request.app.state.bridge


@router.post("", status_code=201)
async def create_aircraft(
    request: Request,
    body: AircraftCreate,
) -> dict:
    """Create a new aircraft (CRE command)."""
    cmd = (
        f"CRE {body.acid},{body.actype},"
        f"{body.lat},{body.lon},"
        f"{body.hdg},{body.alt},{body.spd}"
    )
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.delete("/{acid}")
async def delete_aircraft(
    request: Request,
    acid: str,
) -> dict:
    """Delete an aircraft (DEL command)."""
    _bridge(request).stack_command(f"DEL {acid}")
    return {"status": "ok", "command": f"DEL {acid}"}


@router.get("", response_model=list[AircraftState])
async def list_aircraft(
    request: Request,
) -> list[AircraftState]:
    """Get state of all aircraft."""
    data = _bridge(request).get_aircraft_data()
    return [
        AircraftState(
            acid=data["id"][i],
            lat=data["lat"][i],
            lon=data["lon"][i],
            alt=data["alt"][i],
            tas=data["tas"][i],
            cas=data["cas"][i],
            gs=data["gs"][i],
            trk=data["trk"][i],
            vs=data["vs"][i],
        )
        for i in range(len(data["id"]))
    ]


@router.get("/{acid}", response_model=AircraftState)
async def get_aircraft(
    request: Request,
    acid: str,
) -> dict:
    """Get state of a single aircraft."""
    ac = _bridge(request).get_aircraft_by_id(acid)
    if ac is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aircraft {acid} not found",
        )
    return ac


@router.get("/{acid}/detail")
async def get_aircraft_detail(
    request: Request,
    acid: str,
) -> dict:
    """Get full aircraft detail including autopilot and route."""
    detail = _bridge(request).get_aircraft_detail(acid)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aircraft {acid} not found",
        )
    return detail


@router.get("/{acid}/route", response_model=RouteData)
async def get_route(
    request: Request,
    acid: str,
) -> dict:
    """Get route/flight plan for an aircraft."""
    route = _bridge(request).get_route_data(acid)
    if route is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aircraft {acid} not found",
        )
    return route


@router.post("/{acid}/hdg")
async def set_heading(
    request: Request,
    acid: str,
    body: AircraftSetValue,
) -> dict:
    """Set aircraft heading (HDG command)."""
    cmd = f"HDG {acid} {body.value}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/alt")
async def set_altitude(
    request: Request,
    acid: str,
    body: AircraftSetValue,
) -> dict:
    """Set aircraft altitude in feet (ALT command)."""
    cmd = f"ALT {acid} {body.value}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/spd")
async def set_speed(
    request: Request,
    acid: str,
    body: AircraftSetValue,
) -> dict:
    """Set aircraft speed in knots CAS or Mach."""
    cmd = f"SPD {acid} {body.value}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/vs")
async def set_vertical_speed(
    request: Request,
    acid: str,
    body: AircraftSetValue,
) -> dict:
    """Set vertical speed in fpm (VS command)."""
    cmd = f"VS {acid} {body.value}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/lnav")
async def toggle_lnav(
    request: Request,
    acid: str,
    body: AircraftToggle,
) -> dict:
    """Toggle lateral navigation (LNAV command)."""
    state = "ON" if body.on else "OFF"
    cmd = f"LNAV {acid} {state}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/vnav")
async def toggle_vnav(
    request: Request,
    acid: str,
    body: AircraftToggle,
) -> dict:
    """Toggle vertical navigation (VNAV command)."""
    state = "ON" if body.on else "OFF"
    cmd = f"VNAV {acid} {state}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/addwpt")
async def add_waypoint(
    request: Request,
    acid: str,
    body: AddWaypoint,
) -> dict:
    """Add a waypoint to the aircraft route."""
    parts = [f"ADDWPT {acid} {body.wpname}"]
    if body.alt is not None:
        parts.append(str(body.alt))
    if body.spd is not None:
        parts.append(str(body.spd))
    cmd = " ".join(parts)
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/dest")
async def set_destination(
    request: Request,
    acid: str,
    body: AddWaypoint,
) -> dict:
    """Set aircraft destination (DEST command)."""
    cmd = f"DEST {acid} {body.wpname}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/{acid}/orig")
async def set_origin(
    request: Request,
    acid: str,
    body: AddWaypoint,
) -> dict:
    """Set aircraft origin (ORIG command)."""
    cmd = f"ORIG {acid} {body.wpname}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}
