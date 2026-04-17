"""REST endpoint for PAN target resolution.

Per-client camera move — the resolver is server-side
(it needs access to ``bs.navdb`` and ``bs.traf``), but
the actual camera fly-to happens in the requesting
browser only.  This avoids one user's ``PAN KDFW``
from resetting every other browser's view.
"""
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/pan", tags=["pan"])


@router.get("/resolve")
async def resolve_pan(
    request: Request,
    id: str = Query(
        ...,
        description=(
            "Identifier to resolve: aircraft callsign, "
            "airport ICAO, waypoint/navaid name, or "
            "'lat,lon' pair."
        ),
    ),
) -> dict:
    """Resolve a PAN identifier to a camera target.

    Lookup precedence: aircraft > airport > waypoint >
    lat/lon.  Returns 404 when nothing matches.
    """
    bridge = request.app.state.bridge
    result = bridge._resolve_pan_target(id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"PAN: could not resolve {id!r}",
        )
    result["identifier"] = id
    return result
