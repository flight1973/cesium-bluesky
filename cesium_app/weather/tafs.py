"""Terminal Area Forecast (TAF) fetcher.

TAFs are 24-30 hour airport-specific forecasts
issued by Terminal Aerodrome Forecast providers.
Unlike METARs (observations), TAFs are forecasts
— structured as a series of time-bracketed
forecast blocks (BECMG / TEMPO / FM) describing
wind, visibility, weather, and cloud layers.

API: ``aviationweather.gov/api/data/taf?format=geojson``
Accepts a ``bbox`` param to filter by airport
position.  Refresh every 30 min — TAFs update on
6-hour cycles with occasional amendments.

Normalized shape preserves the full forecast-
blocks array so the UI can surface "weather at
KDFW 3 hours from now" queries.  Raw text stays
available for pilot-readable display.
"""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://aviationweather.gov/api/data/taf"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 1800
FETCH_TIMEOUT_SEC = 15.0
BBOX_WIDEN_DEG = 1.0  # TAFs are per-airport, so a
                     # coarser bbox cache is fine.


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class TafCache:
    ttl_sec: float = CACHE_TTL_SEC
    _by_bbox: dict[str, _CacheEntry] = field(
        default_factory=dict,
    )
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
    )

    def _key(self, bbox: tuple) -> str:
        lat_s, lon_w, lat_n, lon_e = bbox
        q = BBOX_WIDEN_DEG
        return (
            f"{round(lat_s / q) * q:.1f},"
            f"{round(lon_w / q) * q:.1f},"
            f"{round(lat_n / q) * q:.1f},"
            f"{round(lon_e / q) * q:.1f}"
        )

    async def get_or_fetch(self, bbox: tuple) -> list[dict]:
        key = self._key(bbox)
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
            stale = now - self.ttl_sec * 4
            self._by_bbox = {
                k: e for k, e in self._by_bbox.items()
                if e.fetched_at > stale
            }
        return items


_cache = TafCache()


async def get_tafs(bbox: tuple) -> list[dict]:
    return await _cache.get_or_fetch(bbox)


async def _fetch(bbox: tuple) -> list[dict]:
    lat_s, lon_w, lat_n, lon_e = bbox
    params = {
        "bbox": f"{lat_s},{lon_w},{lat_n},{lon_e}",
        "format": "geojson",
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
            "TAF fetch failed bbox=%s: %s", bbox, exc,
        )
        return []
    feats = gj.get("features") or []
    return [
        _normalize(f) for f in feats
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _normalize(f: dict) -> dict:
    """One Feature per forecast block.

    AWC's GeoJSON shape ships one Feature per
    time-bracketed block (BECMG/TEMPO/FM slice),
    not one per airport — multiple blocks belong to
    the same TAF and share the same ``id`` (ICAO).
    We keep that shape flat; callers that want the
    full airport TAF group by ``icao``.

    Key fields: ``id`` is the ICAO, ``fcst_type``
    is the block type (BECMG/TEMPO/FM/FROM),
    ``time_group`` is the block sequence index.
    """
    props = f.get("properties", {}) or {}
    geom = f.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None]
    lon = float(coords[0]) if coords[0] is not None else None
    lat = float(coords[1]) if coords[1] is not None else None
    icao = props.get("id")
    return {
        "id": (
            f"TAF-{icao or '?'}-"
            f"{props.get('issueTime','')}-"
            f"{props.get('timeGroup','0')}"
        ),
        "icao": icao,
        "name": props.get("site"),
        "lat": lat,
        "lon": lon,
        "issue_time": props.get("issueTime"),
        "valid_from": props.get("validTimeFrom"),
        "valid_to": props.get("validTimeTo"),
        "time_group": props.get("timeGroup"),
        "fcst_type": props.get("fcstType"),
        # Forecast values for this block
        "wdir_deg": props.get("wdir"),
        "wspd_kt": props.get("wspd"),
        "wgst_kt": props.get("wgst"),
        "visib": props.get("visib"),
        "ceil_ft": props.get("ceil"),
        "clouds": props.get("clouds"),
        "flt_cat": props.get("fltcat"),
        "raw": props.get("rawTAF"),
    }
