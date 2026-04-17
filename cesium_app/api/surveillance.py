"""REST endpoints for live + replay surveillance feeds."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from cesium_app.ingest import aircraft_db
from cesium_app.surveillance import opensky
from cesium_app.surveillance import replay
from cesium_app.surveillance.conflict_detect import detect_conflicts

router = APIRouter(
    prefix="/api/surveillance", tags=["surveillance"],
)


async def _enrich_and_detect(items: list[dict]) -> dict:
    """Enrich with registry data, run CD, return response."""
    if items and aircraft_db.count() > 0:
        icaos = [a["icao24"] for a in items]
        reg_map = await asyncio.to_thread(
            aircraft_db.lookup_batch, icaos,
        )
        for ac in items:
            reg = reg_map.get(ac["icao24"])
            if reg:
                ac["registration"] = reg.get("registration") or ""
                ac["typecode"] = reg.get("typecode") or ""
                ac["model"] = reg.get("model") or ""
                ac["operator"] = reg.get("operator") or ""
                ac["owner"] = reg.get("owner") or ""

    conflicts = detect_conflicts(items) if items else {
        "confpairs": [], "lospairs": [],
        "conf_tcpa": [], "conf_dcpa": [],
        "nconf_cur": 0, "nlos_cur": 0,
    }

    return {
        "count": len(items),
        "items": items,
        **conflicts,
    }


@router.get("/live")
async def live_traffic(
    bounds: str = Query(
        ...,
        description=(
            "Bounding box 'lat_s,lon_w,lat_n,lon_e'."
        ),
    ),
) -> dict:
    """Live ADS-B positions enriched with aircraft
    registration data (tail number, type, operator).

    Each item has ``icao24``, ``callsign``, ``lat``,
    ``lon``, ``alt_ft``, ``gs_kt``, ``trk_deg``,
    ``vs_fpm``, ``on_ground``, ``squawk``, plus
    (when registry is populated):
    ``registration``, ``typecode``, ``model``,
    ``operator``.
    """
    parts = bounds.split(",")
    if len(parts) != 4:
        raise HTTPException(
            400, "bounds must be 'lat_s,lon_w,lat_n,lon_e'",
        )
    try:
        bbox = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(400, f"bad bbox: {exc}") from exc
    items = await opensky.get_live_traffic(bbox)
    return await _enrich_and_detect(items)


# ── Replay endpoints ───────────────────────────────────


@router.get("/replay/sessions")
async def replay_sessions() -> dict:
    """List available replay sessions."""
    sessions = await asyncio.to_thread(replay.list_sessions)
    return {"sessions": sessions}


@router.get("/replay/{label}")
async def replay_traffic(
    label: str,
    t: int = Query(
        ..., description="Unix epoch to query",
    ),
    tolerance: int = Query(
        10, description="Lookback window in seconds",
    ),
) -> dict:
    """Get traffic snapshot at a given epoch time.

    Returns the same shape as /live so the frontend
    can render replay data identically to live data.
    """
    time_range = await asyncio.to_thread(
        replay.get_time_range, label,
    )
    if time_range is None:
        raise HTTPException(
            404, f"Session '{label}' not found",
        )
    items = await asyncio.to_thread(
        replay.get_snapshot_with_trajectory,
        label, t, tolerance,
    )
    return await _enrich_and_detect(items)


@router.get("/replay/{label}/range")
async def replay_time_range(label: str) -> dict:
    """Get the min/max epoch for a session."""
    r = await asyncio.to_thread(
        replay.get_time_range, label,
    )
    if r is None:
        raise HTTPException(
            404, f"Session '{label}' not found",
        )
    return {"min_t": r[0], "max_t": r[1]}


@router.get("/replay/{label}/trails")
async def replay_trails(
    label: str,
    t: int = Query(..., description="Trails up to this epoch"),
    t_start: int | None = Query(None, description="Start epoch (default: session start)"),
    step: int = Query(1, description="Downsample interval (seconds)"),
) -> dict:
    """Trajectory trails between t_start and t.

    Returns {icao24: [[lat, lon, alt_m], ...]} at
    full (1 Hz) or downsampled resolution.
    """
    trails = await asyncio.to_thread(
        replay.get_trails, label, t_start, t, step,
    )
    return {"trails": trails, "count": len(trails)}
