"""REST endpoints for weather data.

First-pass: METARs from aviationweather.gov.  Future
endpoints (SIGMETs, AIRMETs, PIREPs, NEXRAD, HRRR,
GOES) will live in this router too.
"""
from fastapi import APIRouter, HTTPException, Query

from cesium_app.credentials import get_secret

from cesium_app.weather import airsigmets as airsigmets_mod
from cesium_app.weather import decoder
from cesium_app.weather import cwas as cwas_mod
from cesium_app.weather import gairmets as gairmets_mod
from cesium_app.weather import isigmets as isigmets_mod
from cesium_app.weather import metars as metars_mod
from cesium_app.weather import mis as mis_mod
from cesium_app.weather import pireps as pireps_mod
from cesium_app.weather import station_info as station_info_mod
from cesium_app.weather import tafs as tafs_mod
from cesium_app.weather import tcf as tcf_mod
from cesium_app.weather import era5 as era5_mod
from cesium_app.weather import wafs as wafs_mod
from cesium_app.weather import volcanic_ash as va_mod

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/metars")
async def list_metars(
    bounds: str = Query(
        ...,
        description=(
            "Bounding box 'lat_s,lon_w,lat_n,lon_e' "
            "in degrees."
        ),
    ),
    units: str = Query(
        "aviation",
        description=(
            "Unit system for decoded output: "
            "'aviation' (kt, °C/°F, ft), "
            "'si' (m/s, °C, m), "
            "'imperial' (mph, °F, ft)."
        ),
    ),
) -> dict:
    """METARs within a lat/lon bounding box.

    Returns whatever aviationweather.gov has for the
    last two hours in the requested bbox, normalized
    into a minimal schema.  Results are cached with a
    short TTL, so repeated calls for the same area are
    cheap.
    """
    parts = bounds.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "bounds must be "
                "'lat_s,lon_w,lat_n,lon_e'"
            ),
        )
    try:
        lat_s, lon_w, lat_n, lon_e = (
            float(x) for x in parts
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"bad bounds: {exc}",
        ) from exc
    if lat_s >= lat_n or lon_w >= lon_e:
        raise HTTPException(
            status_code=400,
            detail="bounds must satisfy lat_s<lat_n, lon_w<lon_e",
        )

    items = await metars_mod.get_metars(
        (lat_s, lon_w, lat_n, lon_e),
    )
    # Attach a decoded plain-English narrative to each
    # METAR so the frontend can display both raw + decoded.
    u = units if units in ('aviation', 'si', 'imperial') else 'aviation'
    for m in items:
        m["decoded"] = decoder.decode_metar(m, u)
    return {"count": len(items), "metars": items}


@router.get("/airsigmets")
async def list_airsigmets(
    types: str = Query(
        "SIGMET,AIRMET",
        description=(
            "Comma-separated filter for airSigmetType "
            "values to include (e.g., "
            "'SIGMET' or 'SIGMET,AIRMET')."
        ),
    ),
) -> dict:
    """Active AIRMETs and SIGMETs across the feed.

    The upstream feed is small (dozens of entries at
    most), so we return the whole set and let the
    frontend filter by view bbox.  Caching happens at
    the fetch layer.
    """
    wanted = {
        t.strip().upper() for t in types.split(",")
        if t.strip()
    }
    items = await airsigmets_mod.get_advisories()
    filtered = [
        a for a in items
        if (a.get("type") or "").upper() in wanted
    ]
    return {"count": len(filtered), "items": filtered}


@router.get("/gairmets")
async def list_gairmets(
    forecast_hour: int | None = Query(
        None,
        description=(
            "Filter to a single forecast slice: "
            "0, 3, 6, 9, or 12. Omit for all slices."
        ),
    ),
) -> dict:
    """Active Graphical AIRMETs.

    Distinct from text AIRMETs — drawn graphically by
    forecasters, issued as structured JSON, time-sliced
    into 3-hour forecast snapshots.
    """
    items = await gairmets_mod.get_gairmets()
    if forecast_hour is not None:
        items = [
            a for a in items
            if a.get("forecast_hour") == forecast_hour
        ]
    return {"count": len(items), "items": items}


@router.get("/pireps")
async def list_pireps(
    bounds: str = Query(
        ...,
        description=(
            "Bounding box 'lat_s,lon_w,lat_n,lon_e' "
            "in degrees."
        ),
    ),
) -> dict:
    """Pilot Reports (PIREPs) within a bbox.

    AWC GeoJSON endpoint.  Each item carries position
    plus altitude (``alt_ft`` / ``fl_100ft``) and the
    raw report text — useful for turbulence / icing
    overlays and cockpit-view pop-ups.
    """
    parts = bounds.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=400,
            detail="bounds must be 'lat_s,lon_w,lat_n,lon_e'",
        )
    try:
        bbox = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"bad bbox: {exc}",
        ) from exc
    items = await pireps_mod.get_pireps(bbox)
    return {"count": len(items), "items": items}


@router.get("/cwas")
async def list_cwas() -> dict:
    """Active Center Weather Advisories (CWAs).

    Per-ARTCC short-term hazard bulletins (2-4 hr
    valid).  Polygon + hazard + qualifier; render
    with the SIGMET style under a distinct layer
    toggle.
    """
    items = await cwas_mod.get_cwas()
    return {"count": len(items), "items": items}


@router.get("/isigmets")
async def list_isigmets() -> dict:
    """Active International SIGMETs.

    Oceanic / non-FAA FIR hazards, typically TC
    (tropical cyclone) and VA (volcanic ash).
    Carries altitude band + movement vector.
    """
    items = await isigmets_mod.get_isigmets()
    return {"count": len(items), "items": items}


@router.get("/tafs")
async def list_tafs(
    bounds: str = Query(
        ...,
        description=(
            "Bounding box 'lat_s,lon_w,lat_n,lon_e'."
        ),
    ),
    units: str = Query(
        "aviation",
        description="Unit system: aviation, si, imperial",
    ),
) -> dict:
    """Terminal Area Forecasts within a bbox.

    Each airport's TAF contains a time-bracketed
    forecast block array (``fcsts``) — the UI can
    step through them for 'weather at KDFW 6 hours
    from now' queries.
    """
    parts = bounds.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=400,
            detail="bounds must be 'lat_s,lon_w,lat_n,lon_e'",
        )
    try:
        bbox = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"bad bbox: {exc}",
        ) from exc
    items = await tafs_mod.get_tafs(bbox)
    u = units if units in ('aviation', 'si', 'imperial') else 'aviation'
    for taf in items:
        taf["decoded"] = decoder.decode_taf_block(taf, u)
    return {"count": len(items), "items": items}


@router.get("/tcf")
async def list_tcf() -> dict:
    """TFM Convective Forecast (TCF).

    Short-range convective forecast polygons —
    where thunderstorms are expected in the next
    2-6 hours.  Polygon + coverage + tops + growth.
    """
    items = await tcf_mod.get_tcf()
    return {"count": len(items), "items": items}


@router.get("/mis")
async def list_mises() -> dict:
    """Active Meteorological Impact Statements (MIS).

    Free-form text bulletins from CWSU
    forecasters when weather is expected to
    significantly impact ATM operations.  Often
    empty (MISes are rare).  No GeoJSON upstream;
    each item carries the raw text body.
    """
    items = await mis_mod.get_mises()
    return {"count": len(items), "items": items}


@router.get("/stations")
async def list_stations(
    bounds: str = Query(
        ...,
        description=(
            "Bounding box 'lat_s,lon_w,lat_n,lon_e'. "
            "Required by the upstream endpoint."
        ),
    ),
) -> dict:
    """METAR-reporting station index within a bbox.

    Reference data — which ICAO codes actually
    report METARs, with coords and network
    membership.  Cached per-bbox for a day.
    """
    parts = bounds.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=400,
            detail="bounds must be 'lat_s,lon_w,lat_n,lon_e'",
        )
    try:
        bbox = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"bad bbox: {exc}",
        ) from exc
    items = await station_info_mod.get_stations(bbox)
    return {"count": len(items), "items": items}


# ── Phase 4: Deep weather sources ────────────────────

@router.get("/volcanic-ash")
async def list_volcanic_ash() -> dict:
    """Active volcanic ash advisories — merged from
    AWC ISIGMETs (VA polygons) + NOAA VAAC (text
    narratives).  No credentials required."""
    items = await va_mod.get_volcanic_ash()
    return {"count": len(items), "items": items}


@router.get("/era5/status")
async def era5_status() -> dict:
    """ERA5 availability check — whether the CDS
    API dependencies + credentials are configured."""
    return {
        "available": era5_mod.is_available(),
        "has_cdsapi": era5_mod._HAS_CDS,
        "has_xarray": era5_mod._HAS_XARRAY,
        "has_credentials": bool(
            get_secret("ecmwf_cds", "uid")
        ),
    }


@router.get("/era5/grid")
async def era5_grid(
    date: str = Query(
        ..., description="YYYY-MM-DD",
    ),
    variable: str = Query(
        "u_component_of_wind",
        description="ERA5 variable name",
    ),
    level: int = Query(
        500, description="Pressure level (hPa)",
    ),
) -> dict:
    """2D grid slice from a downloaded ERA5 GRIB2 file.

    Requires ERA5 data to have been pre-downloaded
    via ``python -m cesium_app.ingest era5 --date <date>``.
    Returns 404 if data isn't cached yet.
    """
    grib = era5_mod.era5_dir() / f"era5_pl_{date}.grib2"
    if not grib.exists():
        raise HTTPException(
            404,
            f"ERA5 data for {date} not downloaded. "
            f"Run: python -m cesium_app.ingest era5 "
            f"--date {date}",
        )
    grid = era5_mod.parse_grid(
        grib, variable=variable, level=level,
    )
    if grid is None:
        raise HTTPException(
            500, "ERA5 parse failed (check xarray + cfgrib)",
        )
    return grid


@router.get("/wafs/status")
async def wafs_status() -> dict:
    """WAFS availability check."""
    return {
        "available": wafs_mod.is_available(),
        "has_xarray": wafs_mod._HAS_XARRAY,
        "has_credentials": bool(
            get_secret("noaa_wifs", "token")
        ),
    }
