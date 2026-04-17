"""NOAA WAFS (World Area Forecast System) adapter.

Gridded icing, turbulence, and cumulonimbus
forecasts from the WAFS Internet File Service
(WIFS).  These are the authoritative forecast
grids that pilots use for pre-flight weather
briefings — higher fidelity than the polygon-
based SIGMETs/G-AIRMETs we already ingest.

**Requires**:
- WIFS API access (free registration at
  ``aviationweather.gov/wifs/``)
- ``xarray`` + ``cfgrib`` for GRIB2 parsing

Usage flow:
1. User registers at WIFS
2. Enters credentials via vault:
   ``PUT /api/credentials/noaa_wifs/token``
3. ``python -m cesium_app.ingest wafs``
   downloads the latest forecast GRIB2
4. Parsed grids served via
   ``GET /api/weather/wafs/icing?level=FL250``

Available products:
- **Icing** — probability + severity by FL
- **Turbulence** — CAT + in-cloud by FL
- **Cumulonimbus** — CB probability + tops
"""
from __future__ import annotations

import logging
from pathlib import Path

from cesium_app.credentials import get_secret, register_integration
from cesium_app.store.db import _data_dir

logger = logging.getLogger(__name__)

try:
    import xarray as xr
    _HAS_XARRAY = True
except ImportError:
    _HAS_XARRAY = False

try:
    register_integration(
        "noaa_wifs",
        label="NOAA WIFS (WAFS)",
        description=(
            "Auth: token. "
            "Fields: token. "
            "Register at aviationweather.gov/wifs/. "
            "Powers gridded icing/turbulence/CB forecasts."
        ),
    )
except Exception:
    pass


def is_available() -> bool:
    token = get_secret("noaa_wifs", "token")
    return bool(token and _HAS_XARRAY)


def wafs_dir() -> Path:
    p = _data_dir() / "wafs"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def download_latest(
    product: str = "icing",
) -> Path | None:
    """Download the latest WAFS forecast GRIB2.

    ``product``: 'icing', 'turbulence', or 'cb'.
    Returns the path to the downloaded file, or
    None if not configured.
    """
    if not is_available():
        logger.info(
            "WAFS not available (missing xarray "
            "or WIFS credentials)"
        )
        return None

    import asyncio
    import httpx

    token = get_secret("noaa_wifs", "token")
    # WIFS API endpoint pattern (subject to change;
    # check aviationweather.gov/wifs/api.html).
    _WIFS_BASE = "https://aviationweather.gov/wifs/data"
    product_map = {
        "icing": "icing",
        "turbulence": "turb",
        "cb": "cb",
    }
    prod = product_map.get(product, product)
    outpath = wafs_dir() / f"wafs_{prod}_latest.grib2"

    async def _fetch():
        async with httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "cesium-bluesky/0.1",
            },
        ) as client:
            res = await client.get(
                f"{_WIFS_BASE}/{prod}",
            )
            res.raise_for_status()
            outpath.write_bytes(res.content)
        return outpath

    try:
        return await _fetch()
    except Exception as exc:
        logger.warning("WAFS download failed: %s", exc)
        return None


def parse_grid(
    grib_path: Path,
    level_fl: int = 250,
) -> dict | None:
    """Parse a WAFS GRIB2 file into a 2D grid at the
    given flight level.  Returns a JSON-serializable
    dict or None."""
    if not _HAS_XARRAY:
        return None
    try:
        ds = xr.open_dataset(
            grib_path, engine="cfgrib",
        )
        var_name = list(ds.data_vars)[0]
        # WAFS levels are in flight levels (hundreds of ft)
        da = ds[var_name].sel(
            level=level_fl, method="nearest",
        )
        return {
            "product": grib_path.stem,
            "level_fl": level_fl,
            "lats": da.latitude.values.tolist(),
            "lons": da.longitude.values.tolist(),
            "values": da.values.tolist(),
            "units": str(da.attrs.get("units", "")),
        }
    except Exception as exc:
        logger.warning("WAFS parse failed: %s", exc)
        return None
