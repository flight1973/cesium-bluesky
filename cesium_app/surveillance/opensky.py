"""OpenSky Network live ADS-B adapter.

Free tier: unauthenticated, ~10-15 s update rate,
global coverage.  Optional auth (username +
password) increases rate limits to ~5 s.

API: ``opensky-network.org/api/states/all?bbox=...``
Returns state vectors — one per transponder with
position, velocity, heading, vertical rate,
callsign, and ICAO 24-bit address (Mode S hex).

Per the modular-feeds directive: works without
credentials; credentials from vault improve
refresh rate but are not required.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from cesium_app.credentials import get_secret

logger = logging.getLogger(__name__)

_API_BASE = "https://opensky-network.org/api/states/all"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 12  # match OpenSky's ~10-15 s refresh
FETCH_TIMEOUT_SEC = 15.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]
    bbox_key: str


@dataclass
class OpenSkyCache:
    ttl_sec: float = CACHE_TTL_SEC
    _entry: _CacheEntry | None = None
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
    )

    async def get_or_fetch(
        self, bbox: tuple[float, float, float, float],
    ) -> list[dict]:
        key = f"{bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}"
        now = time.time()
        async with self._lock:
            e = self._entry
            if (e and e.bbox_key == key
                    and (now - e.fetched_at) < self.ttl_sec):
                return e.items
        items = await _fetch(bbox)
        async with self._lock:
            self._entry = _CacheEntry(
                fetched_at=now, items=items, bbox_key=key,
            )
        return items


_cache = OpenSkyCache()


async def get_live_traffic(
    bbox: tuple[float, float, float, float],
) -> list[dict]:
    """Live ADS-B positions within a lat/lon bbox.

    ``bbox``: ``(lat_s, lon_w, lat_n, lon_e)``
    matching our standard convention.
    """
    return await _cache.get_or_fetch(bbox)


async def _fetch(
    bbox: tuple[float, float, float, float],
) -> list[dict]:
    lat_s, lon_w, lat_n, lon_e = bbox
    params = {
        "lamin": str(lat_s),
        "lomin": str(lon_w),
        "lamax": str(lat_n),
        "lomax": str(lon_e),
    }
    # Optional auth for higher rate limits.
    user = get_secret("opensky", "username")
    pw = get_secret("opensky", "password")
    auth = (user, pw) if user and pw else None
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SEC, headers=headers,
            auth=auth,
        ) as client:
            res = await client.get(_API_BASE, params=params)
            res.raise_for_status()
            data = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "OpenSky fetch failed bbox=%s: %s",
            bbox, exc,
        )
        return []
    states = data.get("states") or []
    return [_normalize(s) for s in states if s[5] is not None]


def _normalize(s: list) -> dict:
    """OpenSky state vector → our ObservedAircraft shape.

    State vector indices (from OpenSky docs):
    0: icao24, 1: callsign, 2: origin_country,
    3: time_position, 4: last_contact, 5: longitude,
    6: latitude, 7: baro_altitude (m), 8: on_ground,
    9: velocity (m/s), 10: true_track (deg),
    11: vertical_rate (m/s), 12: sensors,
    13: geo_altitude (m, HAE), 14: squawk,
    15: spi, 16: position_source
    """
    icao24 = s[0] or ""
    callsign = (s[1] or "").strip()
    lon = s[5]
    lat = s[6]
    # Prefer geometric (HAE) altitude when available;
    # fall back to barometric.
    alt_m = s[13] if s[13] is not None else (s[7] or 0)
    gs_ms = s[9] or 0
    trk = s[10] or 0
    vs_ms = s[11] or 0
    on_ground = bool(s[8])
    squawk = s[14] or ""

    return {
        "icao24": icao24,
        "callsign": callsign,
        "lat": float(lat),
        "lon": float(lon),
        "alt_m": float(alt_m),
        "alt_ft": float(alt_m) / 0.3048,
        "gs_kt": float(gs_ms) / 0.514444,
        "trk_deg": float(trk),
        "vs_fpm": float(vs_ms) / 0.00508,
        "on_ground": on_ground,
        "squawk": squawk,
        "source": "OPENSKY",
    }
