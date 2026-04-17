"""SUA (Special Use Airspace) fetcher from FAA GeoServer.

``https://sua.faa.gov/geoserver/SUA/ows`` exposes
``SUA:sua_location`` with ~2000 features covering
Prohibited, Restricted, Warning, Alert, MOA, and
other controlled-access volumes.

``type`` property encodes the SUA class:
    P = Prohibited
    R = Restricted
    W = Warning
    A = Alert
    M = MOA (Military Operations Area)
    N = National Security Area
    T = Training / other

Altitude band is not in this base layer — the
companion ``SUA:schedule`` layer has per-SUA scheduled
altitudes and active hours.  First pass renders full
columns; a scheduled / altitude-limited refinement
comes later.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from cesium_app.airspace.tfrs import _extract_rings
from cesium_app.store import airspace_cache

logger = logging.getLogger(__name__)

_DB_SOURCE = "sua"

_WFS_URL = "https://sua.faa.gov/geoserver/SUA/ows"
_TYPE_NAME = "SUA:sua_location"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 3600  # SUAs change rarely; 1-hr cache is fine
FETCH_TIMEOUT_SEC = 30.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class SuaCache:
    ttl_sec: float = CACHE_TTL_SEC
    _entry: _CacheEntry | None = None
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
    )

    async def get_or_fetch(self) -> list[dict]:
        now = time.time()
        async with self._lock:
            e = self._entry
            if e and (now - e.fetched_at) < self.ttl_sec:
                return e.items
        items = await _fetch()
        async with self._lock:
            self._entry = _CacheEntry(
                fetched_at=now, items=items,
            )
        return items


_cache = SuaCache()


async def get_suas(
    types: set[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """All SUAs, or filtered by single-letter type codes.

    Prefers the persistent SQLite cache when populated
    (``python -m cesium_app.ingest suas``).  Falls
    back to the live WFS fetch with in-memory TTL
    caching when the DB is empty.
    """
    wanted = {t.upper() for t in types} if types else None
    if await asyncio.to_thread(
        airspace_cache.has_source, _DB_SOURCE,
    ):
        return await asyncio.to_thread(
            airspace_cache.query,
            type_="SUA",
            subtypes=wanted,
            bbox=bbox,
        )
    items = await _cache.get_or_fetch()
    if wanted:
        items = [
            a for a in items
            if (a.get("sua_class") or "").upper() in wanted
        ]
    return items


async def _fetch() -> list[dict]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": _TYPE_NAME,
        "outputFormat": "application/json",
    }
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SEC, headers=headers,
        ) as client:
            res = await client.get(
                _WFS_URL, params=params,
            )
            res.raise_for_status()
            gj = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("SUA fetch failed: %s", exc)
        return []
    return [
        _normalize(f) for f in gj.get("features", [])
        if (f.get("geometry") or {}).get("coordinates")
    ]


_CLASS_LABEL = {
    "P": "Prohibited",
    "R": "Restricted",
    "W": "Warning",
    "A": "Alert",
    "M": "MOA",
    "N": "National Security",
    "T": "Training",
}


def _s(v) -> str:
    """Coerce any property value to a trimmed string.

    FAA feeds mix types (ints, None, strings with
    padding); this keeps the normalizer robust.
    """
    if v is None:
        return ""
    return str(v).strip()


def _normalize(f: dict) -> dict:
    props = f.get("properties", {}) or {}
    rings = _extract_rings(f.get("geometry") or {})
    sua_class = _s(props.get("type")).upper()
    name = _s(props.get("sua_name"))
    sua_id = _s(props.get("sua_id"))

    return {
        "id": f"SUA-{sua_id or props.get('__gid')}",
        "type": "SUA",
        "sua_class": sua_class,
        "sua_class_label": _CLASS_LABEL.get(
            sua_class, sua_class,
        ),
        "sua_id": sua_id,
        "name": name,
        "state": _s(props.get("state")),
        "center_id": _s(props.get("center_id")),
        "notes": _s(props.get("notes")),
        "rings": rings,
        "bottom_ft": 0.0,
        "top_ft": 60000.0,
    }
