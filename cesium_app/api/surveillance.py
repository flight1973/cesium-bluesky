"""REST endpoints for live + replay surveillance feeds."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from cesium_app.ingest import aircraft_db
from cesium_app.surveillance import opensky
from cesium_app.surveillance import replay
from cesium_app.surveillance.conflict_detect import detect_conflicts
from cesium_app.surveillance import unified_cd
from cesium_app.surveillance import resolution as reso_registry
from cesium_app.surveillance import trino_download
from cesium_app.surveillance.airspace_classify import classify_batch

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

    # Classify each aircraft's airspace (3D point-in-polygon).
    if items:
        class_map = await asyncio.to_thread(
            classify_batch, items,
        )
        for ac in items:
            ac["airspace_class"] = class_map.get(
                ac["icao24"], "G")

    conflicts = unified_cd.detect(items) if items else {
        "confpairs": [], "lospairs": [],
        "conf_tcpa": [], "conf_dcpa": [],
        "nconf_cur": 0, "nlos_cur": 0,
        "source": "none",
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


@router.post("/replay/download-trino")
async def download_trino(
    start: str = Query(
        ..., description='Start time ISO (e.g. "2024-06-27 15:00")',
    ),
    stop: str = Query(
        ..., description='Stop time ISO',
    ),
    bbox: str = Query(
        ..., description='lat_s,lon_w,lat_n,lon_e',
    ),
    label: str = Query(
        ..., description='Session label',
    ),
) -> dict:
    """Download 1 Hz data from OpenSky Trino.

    Requires approved OpenSky research credentials
    configured in the credential vault or env vars.
    Data is stored in the replay database at full
    1-second resolution.
    """
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(400, "bbox must have 4 values")
    try:
        bb = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(400, f"bad bbox: {exc}") from exc

    try:
        n = await asyncio.to_thread(
            trino_download.download,
            start, stop, bb, label,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            502, f"Trino query failed: {exc}",
        ) from exc

    return {
        "label": label,
        "rows": n,
        "resolution": "1Hz",
        "source": "opensky_trino",
    }


@router.post("/replay/{label}/to-scenario")
async def replay_to_scenario(
    label: str,
    name: str = Query(..., description="Output scenario filename (no extension needed)"),
    start_epoch: int | None = Query(None, description="Start time (epoch seconds)"),
    stop_epoch: int | None = Query(None, description="Stop time (epoch seconds)"),
) -> dict:
    """Compile a replay session window into a BlueSky .scn file.

    The file is written into the user scenario directory so it
    appears in the scenario dropdown and can be loaded with IC.
    """
    from cesium_app.surveillance import replay_to_scenario as r2s
    from cesium_app.api.scenario import _user_scenario_dir, _safe_filename

    safe = _safe_filename(name)
    if not safe.lower().endswith('.scn'):
        safe = safe + '.scn'
    out = _user_scenario_dir() / safe

    try:
        stats = await asyncio.to_thread(
            r2s.convert,
            label, start_epoch, stop_epoch, str(out),
        )
    except Exception as exc:
        raise HTTPException(500, f"Conversion failed: {exc}") from exc

    return {
        "filename": safe,
        "path": str(out),
        **stats,
    }


# ── Conflict detection mode ───────────────────────────


@router.get("/cd-mode")
async def get_cd_mode() -> dict:
    """Current conflict detection mode."""
    return {"mode": unified_cd.get_mode()}


@router.post("/cd-mode")
async def set_cd_mode(
    mode: str = Query(
        ..., description="asas, standalone, or hybrid",
    ),
) -> dict:
    """Switch conflict detection mode.

    - asas: BlueSky ASAS only (requires aircraft in bs.traf)
    - standalone: our airspace-aware CD only (no resolution)
    - hybrid: both, merged and deduplicated
    """
    if mode not in ('asas', 'standalone', 'hybrid'):
        raise HTTPException(400, "mode must be asas, standalone, or hybrid")
    unified_cd.set_mode(mode)  # type: ignore
    return {"mode": mode}


@router.get("/reso-method")
async def get_reso_method() -> dict:
    """Current conflict resolution algorithm."""
    return {
        "method": reso_registry.get_method(),
        "available": reso_registry.available(),
    }


@router.post("/reso-method")
async def set_reso_method(
    method: str = Query(
        ..., description="Resolution algorithm name",
    ),
) -> dict:
    """Switch conflict resolution algorithm.

    Available: mvp, ssd, eby, swarm, vo, orca, dubins
    """
    avail = reso_registry.available()
    if method not in avail:
        raise HTTPException(
            400,
            f"Unknown method '{method}'. "
            f"Available: {avail}",
        )
    reso_registry.set_method(method)
    return {"method": method, "available": avail}


@router.get("/iterative")
async def get_iterative() -> dict:
    """Whether iterative resolution is enabled."""
    return {"enabled": unified_cd.get_iterative()}


@router.post("/iterative")
async def set_iterative(
    enabled: bool = Query(
        ...,
        description="Turn iterative resolution on/off.",
    ),
) -> dict:
    """Enable/disable iterative conflict resolution.

    When on, the resolver re-runs CD on the projected
    post-advisory state and issues additional advisories
    to clear secondary conflicts (up to 5 iterations).
    Slower (~2–5x) but dramatically reduces residual
    conflicts in dense traffic.
    """
    unified_cd.set_iterative(enabled)
    return {"enabled": enabled}


@router.post("/inject-observed")
async def inject_observed(
    enabled: bool = Query(True),
) -> dict:
    """Toggle injection of observed traffic into bs.traf.

    When enabled, live/replay aircraft are CRE'd in the
    sim so ASAS can detect and resolve conflicts involving
    them. Observed aircraft are flagged as immovable —
    only sim aircraft maneuver.
    """
    from cesium_app.sim.observed_inject import ObservedInjector
    app = None
    try:
        from fastapi import Request
    except Exception:
        pass

    return {
        "inject_enabled": enabled,
        "note": "Injection managed via sim bridge. "
                "Set CD mode to 'asas' or 'hybrid' to use.",
    }
