"""TFM Convective Forecast (TCF) fetcher.

Short-range convective forecast polygons issued
by the Collaborative Convective Forecast Product
(CCFP) — shows where thunderstorms are expected
in the next 2-6 hours.  Distinct from SIGMETs
(which describe existing conditions) and from
the SPC outlook (which covers a broader time
range with lower spatial precision).

API: ``aviationweather.gov/api/data/tcf?format=geojson``
No bbox — returns the full current set (typically
5-20 polygons).  Refresh every 30 min.
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

_API_BASE = "https://aviationweather.gov/api/data/tcf"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 1800
FETCH_TIMEOUT_SEC = 15.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class TcfCache:
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


_cache = TcfCache()


async def get_tcf() -> list[dict]:
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
            if res.status_code == 204:
                return []
            res.raise_for_status()
            gj = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("TCF fetch failed: %s", exc)
        return []
    feats = gj.get("features") or []
    return [
        _normalize(f) for f in feats
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _normalize(f: dict) -> dict:
    props = f.get("properties", {}) or {}
    rings = _extract_rings(f.get("geometry") or {})
    return {
        "id": (
            f"TCF-{props.get('validTimeFrom','')}-"
            f"{props.get('coverage','')}"
        ),
        "type": "TCF",
        "valid_from": props.get("validTimeFrom"),
        "valid_to": props.get("validTimeTo"),
        "coverage": props.get("coverage"),
        "tops": props.get("tops"),
        "growth": props.get("growth"),
        "confidence": props.get("confidence"),
        "hazard": "CONVECTIVE",
        "rings": rings,
        "bottom_ft": 0.0,
        "top_ft": (
            float(props["tops"]) * 100.0
            if props.get("tops") is not None
            else 60000.0
        ),
    }
