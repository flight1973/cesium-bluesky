"""REST endpoints for wind field control and queries.

BlueSky stores wind as a collection of lat/lon definition
points, each with a vertical profile on a fixed 100 ft
altitude grid (0 - 45,000 ft).  Horizontal interpolation
between points uses inverse-distance-squared weighting;
vertical uses linear interpolation.  The aircraft physics
treats TAS as invariant and adjusts ground speed / track
based on sampled wind at each aircraft position.

All endpoints accept a unit system selector (``units``)
with values ``aviation`` (kt, default), ``si`` (m/s), or
``imperial`` (mph).  Direction is always degrees true,
met convention (direction wind is *from*).
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/wind", tags=["wind"])

UnitSystem = Literal["aviation", "si", "imperial"]

# Unit conversion factors (to / from m/s).
_KT_PER_MS = 1.0 / 0.514444
_MPH_PER_MS = 2.23693629
_FT_PER_M = 1.0 / 0.3048


def _ms_to_user(ms: float, units: UnitSystem) -> float:
    """Convert m/s into the requested unit system."""
    if units == "si":
        return ms
    if units == "imperial":
        return ms * _MPH_PER_MS
    return ms * _KT_PER_MS  # aviation -> knots


def _user_to_ms(value: float, units: UnitSystem) -> float:
    """Convert a speed from the requested system into m/s."""
    if units == "si":
        return value
    if units == "imperial":
        return value / _MPH_PER_MS
    return value / _KT_PER_MS  # aviation -> knots


def _speed_unit_label(units: UnitSystem) -> str:
    """Human-readable unit symbol for the given system."""
    return {
        "aviation": "kt",
        "si": "m/s",
        "imperial": "mph",
    }[units]


def _vector_to_from_dir(
    vnorth_ms: float, veast_ms: float,
) -> tuple[float, float]:
    """Convert a wind vector (N/E m/s) to (from-dir deg, spd m/s).

    Uses METAR convention: direction is where wind is coming
    from.  This is the inverse of BlueSky's internal storage,
    which represents wind as a "toward" vector:
      vnorth = spd * cos(dir_from + pi)
      veast  = spd * sin(dir_from + pi)
    So dir_from = atan2(veast, vnorth) + pi, normalized to
    [0, 360).
    """
    import math
    spd = math.hypot(vnorth_ms, veast_ms)
    if spd < 1e-6:
        return 0.0, 0.0
    dir_from = math.degrees(
        math.atan2(veast_ms, vnorth_ms),
    ) + 180.0
    return dir_from % 360.0, spd


def _bridge(request: Request):
    return request.app.state.bridge


# ── Request / response models ────────────────────────────

class UniformWind(BaseModel):
    """Set a uniform (altitude-independent, global) wind.

    Attributes:
        direction_deg: Direction wind is *from*, in degrees
            true (METAR convention).  0 = north, 90 = east.
        speed: Wind speed in the unit system given by
            ``units`` (aviation=kt, si=m/s, imperial=mph).
        altitude_ft: If given, create a 3D point at this
            altitude only; otherwise create a 2D field
            (altitude-independent).
        units: Unit system for ``speed``.  Default aviation.
    """

    direction_deg: float = Field(..., ge=0, le=360)
    speed: float = Field(..., ge=0)
    altitude_ft: float | None = None
    units: UnitSystem = "aviation"


class WindSampleResponse(BaseModel):
    """Wind at a queried position."""

    lat: float
    lon: float
    altitude_ft: float
    direction_deg: float
    speed: float
    units: UnitSystem
    unit_label: str
    north_ms: float
    east_ms: float


class WindInfoPoint(BaseModel):
    """One point in the wind field."""

    lat: float
    lon: float
    has_profile: bool


class WindInfoResponse(BaseModel):
    """Wind field metadata."""

    dim: int  # 0=none, 1=constant, 2=2D, 3=3D
    dim_label: str
    npoints: int
    points: list[WindInfoPoint]


# ── Endpoints ────────────────────────────────────────────

_DIM_LABELS = {
    0: "none",
    1: "constant",
    2: "2D",
    3: "3D",
}


@router.get("/info", response_model=WindInfoResponse)
async def wind_info(request: Request) -> WindInfoResponse:
    """Return wind field metadata and definition points.

    Does not include full per-point profiles (use
    ``/api/wind/sample`` for per-position queries).
    """
    import bluesky as bs
    wind = bs.traf.wind
    dim = int(getattr(wind, "winddim", 0))
    lats = list(getattr(wind, "lat", []))
    lons = list(getattr(wind, "lon", []))

    # A point has a real 3D profile if its vertical column
    # in vnorth/veast varies with altitude.  We approximate
    # by checking dim: dim 3 means at least one point has
    # a profile.  For simplicity per-point, we flag all as
    # has_profile when dim == 3.
    has_profile = dim == 3
    points = [
        WindInfoPoint(
            lat=float(la), lon=float(lo),
            has_profile=has_profile,
        )
        for la, lo in zip(lats, lons)
    ]
    return WindInfoResponse(
        dim=dim,
        dim_label=_DIM_LABELS.get(dim, "unknown"),
        npoints=len(points),
        points=points,
    )


class WindGridCell(BaseModel):
    """One grid cell of the wind field."""

    lat: float
    lon: float
    direction_deg: float
    speed_kt: float


class WindGridResponse(BaseModel):
    """Grid-sampled wind field for barb rendering."""

    altitude_ft: float
    spacing_deg: float
    bounds: list[float]  # [lat_s, lon_w, lat_n, lon_e]
    cells: list[WindGridCell]


@router.get("/grid", response_model=WindGridResponse)
async def wind_grid(
    request: Request,
    bounds: str = Query(
        ...,
        description=(
            "Bounding box as 'lat_s,lon_w,lat_n,lon_e'. "
            "Values in degrees."
        ),
    ),
    altitude_ft: float = Query(
        0,
        ge=0,
        le=60000,
        description="Altitude to sample at, in feet.",
    ),
    spacing_deg: float = Query(
        1.0,
        gt=0,
        le=10.0,
        description=(
            "Grid spacing in degrees. 1.0 gives roughly "
            "~100 km cells at equator."
        ),
    ),
) -> WindGridResponse:
    """Sample the wind field on a regular lat/lon grid.

    Designed for aviation-barb rendering on the map.
    Speeds are always returned in knots (barbs are
    knot-native); direction is degrees true, met
    convention (direction wind is *from*).
    """
    import numpy as np
    import bluesky as bs

    parts = [float(x) for x in bounds.split(",")]
    if len(parts) != 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "bounds must be 'lat_s,lon_w,lat_n,lon_e'"
            ),
        )
    lat_s, lon_w, lat_n, lon_e = parts
    if lat_s >= lat_n or lon_w >= lon_e:
        raise HTTPException(
            status_code=400,
            detail=(
                "bounds must satisfy lat_s < lat_n and "
                "lon_w < lon_e"
            ),
        )

    # Cap the cell count so we don't accidentally ask
    # for millions of samples on a tiny spacing across
    # a big bbox.
    n_lat = int(round((lat_n - lat_s) / spacing_deg)) + 1
    n_lon = int(round((lon_e - lon_w) / spacing_deg)) + 1
    if n_lat * n_lon > 10000:
        raise HTTPException(
            status_code=400,
            detail=(
                f"grid too large ({n_lat} x {n_lon} = "
                f"{n_lat * n_lon} cells); tighten "
                f"bounds or increase spacing_deg"
            ),
        )

    lats = np.linspace(lat_s, lat_n, n_lat)
    lons = np.linspace(lon_w, lon_e, n_lon)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    lat_flat = lat_grid.flatten()
    lon_flat = lon_grid.flatten()
    alt_m = altitude_ft / _FT_PER_M
    alt_flat = np.full_like(lat_flat, alt_m)

    wind = bs.traf.wind
    try:
        vn_arr, ve_arr = wind.getdata(
            lat_flat, lon_flat, alt_flat,
        )
        vn_arr = np.asarray(vn_arr)
        ve_arr = np.asarray(ve_arr)
    except (AttributeError, IndexError, ValueError):
        vn_arr = np.zeros_like(lat_flat)
        ve_arr = np.zeros_like(lat_flat)

    # Vectorized "vector → from-direction" conversion.
    spd_ms = np.hypot(vn_arr, ve_arr)
    dir_from = (
        np.degrees(np.arctan2(ve_arr, vn_arr)) + 180.0
    ) % 360.0
    # Points with near-zero speed have ill-defined
    # direction; zero it out for determinism.
    dir_from = np.where(spd_ms < 1e-6, 0.0, dir_from)
    spd_kt = spd_ms * _KT_PER_MS

    cells = [
        WindGridCell(
            lat=float(la),
            lon=float(lo),
            direction_deg=float(d),
            speed_kt=float(s),
        )
        for la, lo, d, s in zip(
            lat_flat, lon_flat, dir_from, spd_kt,
        )
    ]

    return WindGridResponse(
        altitude_ft=altitude_ft,
        spacing_deg=spacing_deg,
        bounds=[lat_s, lon_w, lat_n, lon_e],
        cells=cells,
    )


@router.get("/sample", response_model=WindSampleResponse)
async def wind_sample(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    altitude_ft: float = Query(0, ge=0),
    units: UnitSystem = Query("aviation"),
) -> WindSampleResponse:
    """Sample the wind field at a lat/lon/alt point.

    Altitude is in feet (matches UI convention).  Returns
    direction (from, deg) and speed in the requested units,
    along with the raw N/E components in m/s for clients
    that want vector math.
    """
    import numpy as np
    import bluesky as bs

    # BlueSky wind getdata() accepts arrays; wrap scalars.
    alt_m = altitude_ft / _FT_PER_M
    wind = bs.traf.wind
    try:
        vn_arr, ve_arr = wind.getdata(
            np.array([lat]),
            np.array([lon]),
            np.array([alt_m]),
        )
        vn = float(vn_arr[0])
        ve = float(ve_arr[0])
    except (AttributeError, IndexError, ValueError):
        vn, ve = 0.0, 0.0

    dir_from, spd_ms = _vector_to_from_dir(vn, ve)
    return WindSampleResponse(
        lat=lat,
        lon=lon,
        altitude_ft=altitude_ft,
        direction_deg=dir_from,
        speed=_ms_to_user(spd_ms, units),
        units=units,
        unit_label=_speed_unit_label(units),
        north_ms=vn,
        east_ms=ve,
    )


@router.post("/uniform", status_code=201)
async def set_uniform_wind(
    request: Request,
    body: UniformWind,
) -> dict:
    """Set a single wind definition that applies globally.

    Without ``altitude_ft``, creates a 2D (altitude-
    independent) field: any aircraft anywhere gets this
    wind.  With ``altitude_ft``, creates a 3D point at that
    altitude and lat/lon 0/0; BlueSky interpolates the
    vertical profile between this point's altitude and
    neighbouring layers.

    BlueSky's ``WIND`` command expects knots internally; we
    convert from the user's units before stacking.
    """
    speed_ms = _user_to_ms(body.speed, body.units)
    speed_kt = speed_ms * _KT_PER_MS

    # BlueSky's WIND command: WIND lat lon [alt] dir spd
    # (alt in ft, dir in deg-from, spd in kt)
    parts = ["WIND 0 0"]
    if body.altitude_ft is not None:
        parts.append(f"{body.altitude_ft:.0f}")
    parts.append(f"{body.direction_deg:.1f}")
    parts.append(f"{speed_kt:.1f}")
    cmd = " ".join(parts)
    _bridge(request).stack_command(cmd)
    return {
        "status": "ok",
        "command": cmd,
        "speed_ms": speed_ms,
    }


@router.delete("")
async def clear_wind(request: Request) -> dict:
    """Clear all wind definitions (field becomes empty).

    Sends ``WIND 0 0 DEL`` — BlueSky treats the ``DEL``
    token as a clear-all signal regardless of the lat/lon.
    """
    cmd = "WIND 0 0 DEL"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


class DefinedWindPoint(BaseModel):
    """One user-defined wind point."""

    lat: float
    lon: float
    altitude_ft: float | None
    direction_deg: float
    speed: float
    units: UnitSystem
    unit_label: str
    origin: str = "user"


class NewWindPoint(BaseModel):
    """Request body for creating / updating a wind point.

    Lat/lon is required.  ``altitude_ft`` omitted means
    the point applies at all altitudes (2D point).
    """

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    direction_deg: float = Field(..., ge=0, le=360)
    speed: float = Field(..., ge=0)
    altitude_ft: float | None = None
    units: UnitSystem = "aviation"


class DeleteWindPointBody(BaseModel):
    """Body for DELETE /api/wind/points (deletes one)."""

    lat: float
    lon: float
    altitude_ft: float | None = None


class MetarWindObs(BaseModel):
    """One METAR observation to turn into a wind point."""

    icao: str
    lat: float
    lon: float
    wdir_deg: float | None = None
    wspd_kt: float | None = None


class ImportMetarWindsBody(BaseModel):
    """Replace all METAR-origin wind points with a new set."""

    metars: list[MetarWindObs]


@router.get("/points")
async def list_wind_points(
    request: Request,
    units: UnitSystem = Query("aviation"),
) -> dict:
    """List every user-defined wind point.

    Returns the **defined** points (what the user or
    scenario set), not interpolated samples of the wind
    field.  Speeds converted to the requested unit
    system; direction is always deg true (met
    convention).
    """
    bridge = _bridge(request)
    raw = bridge.get_wind_points()
    label = _speed_unit_label(units)
    points = [
        DefinedWindPoint(
            lat=p["lat"],
            lon=p["lon"],
            altitude_ft=p["altitude_ft"],
            direction_deg=p["direction_deg"],
            speed=_ms_to_user(
                p["speed_kt"] / _KT_PER_MS, units,
            ),
            units=units,
            unit_label=label,
            origin=p.get("origin", "user"),
        )
        for p in raw
    ]
    return {
        "count": len(points),
        "points": [p.model_dump() for p in points],
    }


@router.post("/points", status_code=201)
async def create_wind_point(
    request: Request,
    body: NewWindPoint,
) -> dict:
    """Create or add a user-defined wind point.

    The WIND command is additive in BlueSky — stacking
    the same point twice leaves two entries in the
    shadow list.  To replace a point, DELETE it first
    then POST the new values.
    """
    speed_ms = _user_to_ms(body.speed, body.units)
    speed_kt = speed_ms * _KT_PER_MS

    parts = [f"WIND {body.lat:.4f} {body.lon:.4f}"]
    if body.altitude_ft is not None:
        parts.append(f"{body.altitude_ft:.0f}")
    parts.append(f"{body.direction_deg:.1f}")
    parts.append(f"{speed_kt:.1f}")
    cmd = " ".join(parts)
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.delete("/points")
async def delete_wind_point(
    request: Request,
    body: DeleteWindPointBody,
) -> dict:
    """Delete a single user-defined wind point.

    BlueSky's wind field doesn't support per-point
    deletion, so this is implemented as *clear all +
    replay remaining*.  Side effect: the sim briefly
    observes a cleared wind field before the replay
    completes (a few ticks at most).
    """
    removed = _bridge(request).delete_wind_point(
        body.lat, body.lon, body.altitude_ft,
    )
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=(
                "No matching wind point at "
                f"({body.lat}, {body.lon}, "
                f"altitude_ft={body.altitude_ft})"
            ),
        )
    return {"status": "ok"}


@router.post("/import-metars")
async def import_metar_winds(
    request: Request,
    body: ImportMetarWindsBody,
) -> dict:
    """Replace METAR-origin wind points with a fresh set.

    Keeps user-defined wind points intact.  Stacks one
    2D WIND command per METAR with non-calm wind.
    Re-run whenever the upstream METAR data refreshes.
    """
    observations = [
        m.model_dump() for m in body.metars
    ]
    count = _bridge(request).import_metar_winds(
        observations,
    )
    return {"status": "ok", "imported": count}


@router.delete("/metar-winds")
async def clear_metar_winds(request: Request) -> dict:
    """Remove all METAR-origin wind points.

    User-defined wind points are preserved.
    """
    removed = _bridge(request).clear_metar_winds()
    return {"status": "ok", "removed": removed}


@router.get("/aircraft/{acid}")
async def aircraft_wind(
    request: Request,
    acid: str,
    units: UnitSystem = Query("aviation"),
) -> dict:
    """Wind sampled at a specific aircraft's position.

    Reads ``bs.traf.windnorth[idx]`` and
    ``bs.traf.windeast[idx]`` — the values used by the sim
    in that aircraft's ground-speed calculation this frame.
    """
    import bluesky as bs
    idx = bs.traf.id2idx(acid.upper())
    if idx < 0:
        raise HTTPException(
            status_code=404,
            detail=f"Aircraft {acid!r} not found",
        )
    try:
        vn = float(bs.traf.windnorth[idx])
        ve = float(bs.traf.windeast[idx])
    except (AttributeError, IndexError):
        vn, ve = 0.0, 0.0
    dir_from, spd_ms = _vector_to_from_dir(vn, ve)
    return {
        "acid": acid.upper(),
        "direction_deg": dir_from,
        "speed": _ms_to_user(spd_ms, units),
        "units": units,
        "unit_label": _speed_unit_label(units),
        "north_ms": vn,
        "east_ms": ve,
    }
