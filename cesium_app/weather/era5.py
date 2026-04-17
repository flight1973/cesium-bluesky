"""ERA5 reanalysis weather data adapter.

ECMWF's ERA5 provides hourly 3D atmospheric grids
(wind, temperature, humidity, cloud fraction) on
pressure levels — the foundation for volumetric
cloud rendering and real wind-field animation.

**Requires**:
- ``cdsapi`` Python package (``pip install cdsapi``)
- CDS account + API key (free registration at
  ``cds.climate.copernicus.eu``)
- ``xarray`` + ``cfgrib`` for GRIB2 parsing

All are **optional** per the modular-feeds
directive.  If not installed or not configured,
this module returns empty results and logs an
info-level message.

Usage flow:
1. User registers at CDS, gets UID + API key
2. Enters credentials via vault:
   ``PUT /api/credentials/ecmwf_cds/uid``
   ``PUT /api/credentials/ecmwf_cds/api_key``
3. ``python -m cesium_app.ingest era5 --date 2026-04-16``
   downloads a GRIB2 file for the requested date/bbox
4. The adapter parses it into a 3D grid served via
   ``GET /api/weather/era5/wind?level=500``
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from cesium_app.credentials import get_secret, register_integration
from cesium_app.store.db import _data_dir

logger = logging.getLogger(__name__)

# Optional heavy deps — guarded per modular-feeds.
try:
    import cdsapi
    _HAS_CDS = True
except ImportError:
    _HAS_CDS = False

try:
    import xarray as xr
    _HAS_XARRAY = True
except ImportError:
    _HAS_XARRAY = False

# Register with vault so the credentials panel shows it.
try:
    register_integration(
        "ecmwf_cds",
        label="ECMWF CDS (ERA5)",
        description=(
            "Auth: token. "
            "Fields: uid, api_key. "
            "Register free at cds.climate.copernicus.eu. "
            "Powers 3D wind/cloud/humidity grids."
        ),
    )
except Exception:
    pass  # DB might not be ready yet


def is_available() -> bool:
    """True if all dependencies + credentials are present."""
    if not _HAS_CDS or not _HAS_XARRAY:
        return False
    uid = get_secret("ecmwf_cds", "uid")
    key = get_secret("ecmwf_cds", "api_key")
    return bool(uid and key)


def era5_dir() -> Path:
    p = _data_dir() / "era5"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def download_pressure_levels(
    date: str,
    *,
    variables: list[str] | None = None,
    levels: list[int] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> Path | None:
    """Download ERA5 pressure-level data for one date.

    Returns the path to the downloaded GRIB2 file,
    or None if credentials/deps are missing.

    Default variables: u/v wind, temperature,
    relative humidity, specific cloud ice/liquid
    water content.  Default levels: 1000, 925,
    850, 700, 500, 300, 200 hPa.
    """
    if not is_available():
        logger.info(
            "ERA5 not available (missing cdsapi, "
            "xarray, or CDS credentials)"
        )
        return None

    uid = get_secret("ecmwf_cds", "uid")
    key = get_secret("ecmwf_cds", "api_key")

    if variables is None:
        variables = [
            "u_component_of_wind",
            "v_component_of_wind",
            "temperature",
            "relative_humidity",
            "specific_cloud_ice_water_content",
            "specific_cloud_liquid_water_content",
        ]
    if levels is None:
        levels = [1000, 925, 850, 700, 500, 300, 200]
    if bbox is None:
        # Default: CONUS
        bbox = (50, -130, 24, -60)  # N, W, S, E

    outpath = era5_dir() / f"era5_pl_{date}.grib2"
    if outpath.exists():
        logger.info("ERA5 %s already cached at %s", date, outpath)
        return outpath

    import asyncio
    def _download():
        c = cdsapi.Client(
            url="https://cds.climate.copernicus.eu/api",
            key=f"{uid}:{key}",
        )
        c.retrieve(
            "reanalysis-era5-pressure-levels",
            {
                "product_type": "reanalysis",
                "variable": variables,
                "pressure_level": [str(l) for l in levels],
                "year": date[:4],
                "month": date[5:7],
                "day": date[8:10],
                "time": [
                    "00:00", "06:00", "12:00", "18:00",
                ],
                "area": list(bbox),
                "format": "grib",
            },
            str(outpath),
        )
        return outpath

    return await asyncio.to_thread(_download)


def parse_grid(
    grib_path: Path,
    variable: str = "u_component_of_wind",
    level: int = 500,
    time_idx: int = 0,
) -> dict | None:
    """Parse a downloaded GRIB2 file into a JSON-
    serializable 2D grid for one variable + level
    + time step.

    Returns ``{lats, lons, values, variable, level,
    time}`` or None if parsing fails.
    """
    if not _HAS_XARRAY:
        return None
    try:
        ds = xr.open_dataset(
            grib_path,
            engine="cfgrib",
            backend_kwargs={
                "filter_by_keys": {
                    "shortName": _short_name(variable),
                    "level": level,
                },
            },
        )
        var_name = list(ds.data_vars)[0]
        da = ds[var_name].isel(time=time_idx)
        return {
            "variable": variable,
            "level": level,
            "lats": da.latitude.values.tolist(),
            "lons": da.longitude.values.tolist(),
            "values": da.values.tolist(),
            "units": str(da.attrs.get("units", "")),
        }
    except Exception as exc:
        logger.warning("ERA5 parse failed: %s", exc)
        return None


_SHORT_NAMES = {
    "u_component_of_wind": "u",
    "v_component_of_wind": "v",
    "temperature": "t",
    "relative_humidity": "r",
    "specific_cloud_ice_water_content": "ciwc",
    "specific_cloud_liquid_water_content": "clwc",
}


def _short_name(long_name: str) -> str:
    return _SHORT_NAMES.get(long_name, long_name)
