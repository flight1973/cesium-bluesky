"""International SIGMET (ISIGMET) fetcher.

WAFC-issued SIGMETs over the high seas and
non-FAA FIRs — critical for oceanic / long-haul
flights.  Hazards skew toward tropical cyclones
(TC) and volcanic ash (VA) rather than the
convective / turb / ice mix that dominates
continental SIGMETs.

API: ``aviationweather.gov/api/data/isigmet?format=geojson``
No bbox parameter — returns the full active set
(always small, ~10-50).  Refresh every 15 min —
ISIGMETs evolve slowly.
"""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

from cesium_app.airspace.tfrs import _extract_rings

logger = logging.getLogger(__name__)

_API_BASE = "https://aviationweather.gov/api/data/isigmet"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 900
FETCH_TIMEOUT_SEC = 10.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class IsigmetCache:
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


_cache = IsigmetCache()


async def get_isigmets() -> list[dict]:
    return await _cache.get_or_fetch()


async def _fetch() -> list[dict]:
    params = {"format": "geojson"}
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
        logger.warning("ISIGMET fetch failed: %s", exc)
        return []
    feats = gj.get("features") or []
    return [
        _normalize(f) for f in feats
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _normalize(f: dict) -> dict:
    """ISIGMET schema carries more than CONUS SIGMETs:

    - ``top`` / ``base`` in feet when published
    - ``dir`` / ``spd`` for movement vector
      (translates to a future "drift polygon"
      prediction)
    - ``firId`` / ``firName`` — the oceanic FIR
      that owns the advisory
    """
    props = f.get("properties", {}) or {}
    rings = _extract_rings(f.get("geometry") or {})
    top_ft = props.get("top")
    base_ft = props.get("base")
    return {
        "id": (
            f"ISIGMET-{props.get('icaoId','?')}-"
            f"{props.get('seriesId','?')}-"
            f"{props.get('validTimeFrom','')}"
        ),
        "type": "ISIGMET",
        "icao": props.get("icaoId"),
        "fir_id": props.get("firId"),
        "fir_name": props.get("firName"),
        "series_id": props.get("seriesId"),
        "valid_from": props.get("validTimeFrom"),
        "valid_to": props.get("validTimeTo"),
        "hazard": props.get("hazard"),
        "qualifier": props.get("qualifier"),
        "dir_deg": props.get("dir"),
        "spd_kt": props.get("spd"),
        "rings": rings,
        "raw": props.get("rawSigmet"),
        "bottom_ft": (
            float(base_ft) if base_ft is not None
            else 0.0
        ),
        "top_ft": (
            float(top_ft) if top_ft is not None
            else 60000.0
        ),
    }
