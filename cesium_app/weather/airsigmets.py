"""AIRMET / SIGMET fetcher + cache (aviationweather.gov).

Fetches the combined airmet/sigmet feed from the AWC
Data API, caches the results, and normalizes each
advisory to the minimum shape the frontend needs to
render it as a 3D extruded polygon:

    {
      id, type, hazard, severity,
      valid_from, valid_to,
      bottom_ft, top_ft,
      movement_dir, movement_spd,
      coords: [(lat, lon), ...],
      raw, icao,
    }

API reference: <https://aviationweather.gov/data/api/>.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://aviationweather.gov/api/data/airsigmet"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 300  # advisories refresh hourly; 5-min cache is fine
FETCH_TIMEOUT_SEC = 15.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class AirSigmetCache:
    """Single-key cache — the API returns the whole feed."""

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


_cache = AirSigmetCache()


async def get_advisories() -> list[dict]:
    """Public entry — cached AIRMET/SIGMET list."""
    return await _cache.get_or_fetch()


async def _fetch() -> list[dict]:
    headers = {"User-Agent": _USER_AGENT}
    params = {"format": "json"}
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SEC, headers=headers,
        ) as client:
            res = await client.get(_API_URL, params=params)
            res.raise_for_status()
            raw = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("airsigmet fetch failed: %s", exc)
        return []
    return [_normalize(a) for a in raw if a.get("coords")]


def _normalize(a: dict) -> dict:
    """Reduce to UI-friendly shape.

    Altitude handling: aviationweather returns two low
    and two high pairs (for two-part outlooks).  We
    take the widest altitude band — lowest of the lows
    and highest of the highs.  Null treated as "open"
    (surface for bottom, FL600 for top).
    """
    def _pick_low(a: dict) -> float:
        lo = [
            v for v in
            (a.get("altitudeLow1"), a.get("altitudeLow2"))
            if v is not None
        ]
        return min(lo) if lo else 0.0

    def _pick_high(a: dict) -> float:
        hi = [
            v for v in
            (a.get("altitudeHi1"), a.get("altitudeHi2"))
            if v is not None
        ]
        return max(hi) if hi else 60000.0

    # Unique ID per advisory so the frontend can upsert.
    aid = (
        f"{a.get('airSigmetType', '?')}-"
        f"{a.get('icaoId', '?')}-"
        f"{a.get('seriesId') or a.get('alphaChar') or ''}-"
        f"{a.get('validTimeFrom')}"
    )

    coords = [
        (float(c["lat"]), float(c["lon"]))
        for c in (a.get("coords") or [])
        if c.get("lat") is not None
        and c.get("lon") is not None
    ]

    return {
        "id": aid,
        "type": a.get("airSigmetType"),   # SIGMET / AIRMET
        "hazard": a.get("hazard"),
        "severity": a.get("severity"),
        "valid_from": a.get("validTimeFrom"),
        "valid_to": a.get("validTimeTo"),
        "bottom_ft": _pick_low(a),
        "top_ft": _pick_high(a),
        "movement_dir": a.get("movementDir"),
        "movement_spd": a.get("movementSpd"),
        "coords": coords,
        "raw": a.get("rawAirSigmet"),
        "icao": a.get("icaoId"),
    }
