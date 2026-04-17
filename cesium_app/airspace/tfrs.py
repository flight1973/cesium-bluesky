"""TFR fetcher + cache from FAA GeoServer.

The FAA hosts Temporary Flight Restrictions as a
public OGC Web Feature Service at
``https://tfr.faa.gov/geoserver/TFR/ows``.  The
primary feature type is ``TFR:V_TFR_LOC`` with one
polygon per active TFR.  Updates hourly+.

The GeoJSON feed exposes geometry + metadata (title,
state, NOTAM key, legal basis) but not altitude band
— that lives in the detail TFR document on the FAA
TFR site.  For the basic overlay we render as
full-column volumes; extending to per-TFR altitudes
is a follow-on (would require fetching
``tfr.faa.gov/save_pages/<notam>.html`` per active
TFR and parsing).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_WFS_URL = "https://tfr.faa.gov/geoserver/TFR/ows"
_TYPE_NAME = "TFR:V_TFR_LOC"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 300
FETCH_TIMEOUT_SEC = 20.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class TfrCache:
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


_cache = TfrCache()


async def get_tfrs() -> list[dict]:
    return await _cache.get_or_fetch()


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
        logger.warning("TFR fetch failed: %s", exc)
        return []
    return [
        _normalize(f) for f in gj.get("features", [])
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _normalize(f: dict) -> dict:
    """FAA WFS feature → UI-friendly shape.

    Geometry collapses MultiPolygon / Polygon rings to
    a flat list of vertex rings, each as
    ``[(lat, lon), ...]``.  Matches the SIGMET shape
    close enough that the frontend can reuse the same
    renderer.
    """
    props = f.get("properties", {}) or {}
    geom = f.get("geometry", {}) or {}
    rings = _extract_rings(geom)

    notam_key = props.get("NOTAM_KEY") or ""
    tfr_id = (
        f"TFR-{notam_key or props.get('GID', 'unknown')}"
    )

    return {
        "id": tfr_id,
        "type": "TFR",
        "notam_key": notam_key,
        "title": props.get("TITLE") or "",
        "state": props.get("STATE") or "",
        "legal": props.get("LEGAL") or "",
        "last_mod": props.get("LAST_MODIFICATION_DATETIME"),
        "rings": rings,
        # Altitude band unknown from WFS — render as
        # full-column volume; 0 to 60,000 ft is a safe
        # visual default.  Override per-TFR when we
        # add the detail-page parser.
        "bottom_ft": 0.0,
        "top_ft": 60000.0,
    }


def _extract_rings(geom: dict) -> list[list[tuple]]:
    """Flatten (Multi)Polygon geometry to lat/lon rings."""
    kind = geom.get("type")
    coords = geom.get("coordinates") or []
    out: list[list[tuple]] = []
    if kind == "Polygon":
        for ring in coords:
            out.append([
                (float(c[1]), float(c[0]))
                for c in ring if len(c) >= 2
            ])
    elif kind == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                out.append([
                    (float(c[1]), float(c[0]))
                    for c in ring if len(c) >= 2
                ])
    return out
