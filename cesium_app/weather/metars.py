"""METAR fetcher + cache (aviationweather.gov).

Fetches METARs from the AWC Data API for a given
lat/lon bounding box, caches results in-memory with a
configurable TTL, and normalizes the response into a
minimal schema that the frontend consumes.

API reference: <https://aviationweather.gov/data/api/>.
No auth required; they ask that consumers send a
reasonable ``User-Agent``.

Rate-limit sensible behavior:
- Cache per-bbox responses for ``CACHE_TTL_SEC``
  (default 3 minutes — METARs update every ~5 min).
- Slightly widen the requested bbox so small camera
  moves still hit the cache.
"""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://aviationweather.gov/api/data/metar"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 180
FETCH_TIMEOUT_SEC = 10.0
# Widen each bbox-edge by this margin before hashing so
# tiny camera moves can reuse the last fetch.
BBOX_WIDEN_DEG = 0.5


@dataclass
class MetarCacheEntry:
    """One cached METAR query result."""

    fetched_at: float
    metars: list[dict]


@dataclass
class MetarCache:
    """In-memory bbox→metars cache with TTL."""

    ttl_sec: float = CACHE_TTL_SEC
    _by_bbox: dict[str, MetarCacheEntry] = field(
        default_factory=dict,
    )
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
    )

    def _key(self, bbox: tuple) -> str:
        """Quantized bbox key so nearby queries collide."""
        lat_s, lon_w, lat_n, lon_e = bbox
        # Round to BBOX_WIDEN_DEG granularity.
        q = BBOX_WIDEN_DEG
        return (
            f"{round(lat_s / q) * q:.2f},"
            f"{round(lon_w / q) * q:.2f},"
            f"{round(lat_n / q) * q:.2f},"
            f"{round(lon_e / q) * q:.2f}"
        )

    async def get_or_fetch(
        self, bbox: tuple,
    ) -> list[dict]:
        """Return cached metars for bbox, or fetch fresh."""
        key = self._key(bbox)
        now = time.time()
        async with self._lock:
            entry = self._by_bbox.get(key)
            if entry and (now - entry.fetched_at) < self.ttl_sec:
                return entry.metars
        # Cache miss / expired — fetch outside the lock.
        metars = await _fetch_metars(bbox)
        async with self._lock:
            self._by_bbox[key] = MetarCacheEntry(
                fetched_at=now, metars=metars,
            )
            # Drop ancient entries so the cache doesn't
            # grow unboundedly as the user pans around.
            stale = now - self.ttl_sec * 4
            self._by_bbox = {
                k: e for k, e in self._by_bbox.items()
                if e.fetched_at > stale
            }
        return metars


_default_cache = MetarCache()


async def get_metars(bbox: tuple) -> list[dict]:
    """Public entry: cached METARs for a bbox."""
    return await _default_cache.get_or_fetch(bbox)


async def _fetch_metars(bbox: tuple) -> list[dict]:
    """Hit aviationweather.gov and normalize results."""
    lat_s, lon_w, lat_n, lon_e = bbox
    # AWC wants ``bbox=lat_s,lon_w,lat_n,lon_e``.
    params = {
        "bbox": f"{lat_s},{lon_w},{lat_n},{lon_e}",
        "format": "json",
        "hours": "2",
    }
    url = _API_BASE + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SEC,
            headers=headers,
        ) as client:
            res = await client.get(url)
            res.raise_for_status()
            raw = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "METAR fetch failed for bbox=%s: %s",
            bbox, exc,
        )
        return []

    return [_normalize(m) for m in raw]


def _normalize(m: dict) -> dict:
    """Reduce AWC's wide schema to what the UI uses.

    Speeds returned in knots, temperatures in °C,
    altimeter in hPa (matches AWC).  Flight category
    is one of VFR / MVFR / IFR / LIFR / None.
    """
    return {
        "icao": m.get("icaoId"),
        "name": m.get("name"),
        "lat": m.get("lat"),
        "lon": m.get("lon"),
        "elev_m": m.get("elev"),
        "obs_time": m.get("reportTime"),
        "temp_c": m.get("temp"),
        "dewp_c": m.get("dewp"),
        "wdir_deg": m.get("wdir"),
        "wspd_kt": m.get("wspd"),
        "wgst_kt": m.get("wgst"),
        "visib": m.get("visib"),
        "altim_hpa": m.get("altim"),
        "cover": m.get("cover"),
        "clouds": m.get("clouds"),
        "flt_cat": m.get("fltCat"),
        "raw": m.get("rawOb"),
    }
