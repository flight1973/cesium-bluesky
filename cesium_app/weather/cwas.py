"""Center Weather Advisory (CWA) fetcher.

CWAs are short-term hazard bulletins issued by the
Center Weather Service Unit (CWSU) at each ARTCC
for hazards evolving faster than the SIGMET cycle
can keep up with.  Typically 2-4 hours valid,
polygon-bounded, hazard-qualified (TURB / ICE /
IFR / CNVTV / etc.).

API: ``aviationweather.gov/api/data/cwa?format=geojson``
No bbox filter — returns the full current set
(always a small number, ~5-20 active).

The polygon + hazard fields mirror SIGMETs closely,
so the frontend can render CWAs with the existing
``SigmetManager`` style — just under a distinct
layer toggle.
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

_API_BASE = "https://aviationweather.gov/api/data/cwa"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 180
FETCH_TIMEOUT_SEC = 10.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class CwaCache:
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


_cache = CwaCache()


async def get_cwas() -> list[dict]:
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
        logger.warning("CWA fetch failed: %s", exc)
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
            f"CWA-{props.get('cwsu','?')}-"
            f"{props.get('seriesId','?')}-"
            f"{props.get('validTimeFrom','')}"
        ),
        "type": "CWA",
        "cwsu": props.get("cwsu"),
        "name": props.get("name"),
        "series_id": props.get("seriesId"),
        "valid_from": props.get("validTimeFrom"),
        "valid_to": props.get("validTimeTo"),
        "hazard": props.get("hazard"),
        "qualifier": props.get("qualifier"),
        "rings": rings,
        "raw": props.get("cwaText"),
        # CWAs don't publish altitude bands in the
        # GeoJSON; render as a full column until we
        # parse the text for FL info.  Same treatment
        # as TFRs.
        "bottom_ft": 0.0,
        "top_ft": 60000.0,
    }
