"""Geoid undulation lookup via EGM2008.

Converts mean-sea-level altitudes to height-above-
ellipsoid (the reference Cesium and GPS use):

    HAE = MSL + N(lat, lon)

where ``N`` is the geoid undulation from NGA's
Earth Gravitational Model 2008 (EGM2008).

Grid data comes from PROJ's
``us_nga_egm08_25.tif`` — the 25 arc-minute
resolution EGM2008 grid, ~80 MB, bundled under
``data/proj_grids/``.  Accuracy is a few meters
worldwide; installing the 1 arc-minute grid
(``egm2008-1``, 75 MB) as described in
``project_altitude_references.md`` is a drop-in
upgrade for procedure-accurate vertical work.

Thread-safe: pyproj's ``Transformer`` is not shared
across threads, so each call to :func:`undulation`
gets the same lazy-cached instance.  In practice our
ingest is single-threaded and the REST path reads
the already-compiled polyline from SQLite, so
threading isn't on the hot path.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import pyproj
from pyproj import Transformer

from cesium_app.store.db import _data_dir

logger = logging.getLogger(__name__)

_GRID_FILE = "us_nga_egm08_25.tif"
_GRIDS_SUBDIR = "proj_grids"

_lock = threading.Lock()
_transformer: Transformer | None = None
_registered = False


def _grid_dir() -> Path:
    return _data_dir() / _GRIDS_SUBDIR


def _ensure_registered() -> bool:
    """Wire our grids dir into pyproj's search path.

    Returns True if the EGM2008 grid file is present
    and ready to use.  False if the grid is missing —
    callers should fall back to a zero undulation in
    that case rather than crash on a dev machine
    that hasn't run ``projsync`` yet.
    """
    global _registered
    if _registered:
        return (_grid_dir() / _GRID_FILE).exists()
    grid_path = _grid_dir() / _GRID_FILE
    if not grid_path.exists():
        logger.warning(
            "EGM2008 grid %s not found; HAE≡MSL until "
            "it's installed (`projsync --file %s "
            "--target-dir %s`).",
            grid_path, _GRID_FILE, _grid_dir(),
        )
        _registered = True
        return False
    pyproj.datadir.append_data_dir(str(_grid_dir()))
    _registered = True
    return True


def _get_transformer() -> Transformer | None:
    global _transformer
    if _transformer is not None:
        return _transformer
    with _lock:
        if _transformer is not None:
            return _transformer
        if not _ensure_registered():
            return None
        _transformer = Transformer.from_pipeline(
            f"+proj=pipeline +step +proj=vgridshift "
            f"+grids={_GRID_FILE} +multiplier=1"
        )
        return _transformer


def undulation(lat: float, lon: float) -> float:
    """Geoid-to-ellipsoid offset N in meters.

    ``N > 0`` means MSL is *above* the ellipsoid at
    (lat, lon); ``N < 0`` means *below* (true for
    most of the continental US, ~-15 m to -35 m).
    """
    t = _get_transformer()
    if t is None:
        return 0.0
    # vgridshift takes (lon, lat, h_msl) → (lon, lat, h_hae).
    # Passing h_msl=0 returns N directly.
    _, _, hae = t.transform(lon, lat, 0.0)
    return hae


def msl_ft_to_hae_m(
    alt_msl_ft: float,
    lat: float,
    lon: float,
) -> float:
    """Convert MSL feet → HAE meters at (lat, lon)."""
    t = _get_transformer()
    msl_m = alt_msl_ft * 0.3048
    if t is None:
        return msl_m
    _, _, hae_m = t.transform(lon, lat, msl_m)
    return hae_m
