"""METAR-reporting station index fetcher.

Every AWC METAR is keyed by ICAO — this endpoint
supplies the index: which ICAO codes are actually
METAR-reporting stations, their coordinates,
elevations, and network membership (METAR,
aviation, IATA, etc.).

API: ``aviationweather.gov/api/data/stationinfo?format=geojson``
Reference-data endpoint: refresh daily at most.
Cache with a long TTL; the upstream won't thank us
for polling it on every map pan.
"""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://aviationweather.gov/api/data/stationinfo"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 86400
FETCH_TIMEOUT_SEC = 30.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class StationInfoCache:
    ttl_sec: float = CACHE_TTL_SEC
    _by_bbox: dict[str, _CacheEntry] = field(
        default_factory=dict,
    )
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
    )

    async def get_or_fetch(
        self, bbox: tuple,
    ) -> list[dict]:
        # Quantize bbox to the nearest degree so
        # nearby queries reuse the cache.  Station
        # coords are effectively static.
        lat_s, lon_w, lat_n, lon_e = bbox
        key = (
            f"{round(lat_s):+d},{round(lon_w):+d},"
            f"{round(lat_n):+d},{round(lon_e):+d}"
        )
        now = time.time()
        async with self._lock:
            e = self._by_bbox.get(key)
            if e and (now - e.fetched_at) < self.ttl_sec:
                return e.items
        items = await _fetch(bbox)
        async with self._lock:
            self._by_bbox[key] = _CacheEntry(
                fetched_at=now, items=items,
            )
        return items


_cache = StationInfoCache()


async def get_stations(bbox: tuple) -> list[dict]:
    return await _cache.get_or_fetch(bbox)


async def _fetch(bbox: tuple) -> list[dict]:
    # AWC stationinfo requires bbox + zoom (or
    # explicit station IDs).  Zoom 7 = ~regional
    # density; high zoom would cap the returned set.
    lat_s, lon_w, lat_n, lon_e = bbox
    params = {
        "format": "geojson",
        "bbox": f"{lat_s},{lon_w},{lat_n},{lon_e}",
        "zoom": "7",
    }
    url = _API_BASE + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SEC, headers=headers,
        ) as client:
            res = await client.get(url)
            res.raise_for_status()
            gj = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Station info fetch failed: %s", exc,
        )
        return []
    feats = gj.get("features") or []
    return [
        _normalize(f) for f in feats
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _normalize(f: dict) -> dict:
    props = f.get("properties", {}) or {}
    geom = f.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None]
    lon = float(coords[0]) if coords[0] is not None else None
    lat = float(coords[1]) if coords[1] is not None else None
    return {
        "icao": props.get("icaoId") or props.get("id"),
        "iata": props.get("iataId"),
        "faa_id": props.get("faaId"),
        "name": props.get("site"),
        "state": props.get("state"),
        "country": props.get("country"),
        "lat": lat,
        "lon": lon,
        "elev_m": props.get("elev"),
        # AWC returns a ``siteType`` array like
        # ['METAR'] or ['METAR','TAF']; preserve it
        # verbatim for the UI to filter on.
        "site_types": props.get("siteType") or [],
    }
