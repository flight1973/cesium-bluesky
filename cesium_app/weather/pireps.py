"""PIREP fetcher + cache (aviationweather.gov).

Pilot weather reports — point observations keyed by
position and flight level, carrying turbulence /
icing / visibility / sky-condition narrative from
the reporting pilot.  Unique among AWC products for
carrying altitude: each report is a 3D point.

API: ``aviationweather.gov/api/data/pirep?format=geojson``
Refresh: we poll every 2 minutes (PIREPs trickle in
continuously; 2 min is enough to feel live without
hammering the upstream).

Normalized shape mirrors the METAR adapter's style
— bbox-keyed TTL cache, flat dict per observation,
geometry flattened to ``lat/lon/fl_100ft``.
"""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://aviationweather.gov/api/data/pirep"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 120
FETCH_TIMEOUT_SEC = 10.0
BBOX_WIDEN_DEG = 0.5


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class PirepCache:
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
            f"{round(lat_s / q) * q:.2f},"
            f"{round(lon_w / q) * q:.2f},"
            f"{round(lat_n / q) * q:.2f},"
            f"{round(lon_e / q) * q:.2f}"
        )

    async def get_or_fetch(
        self, bbox: tuple,
    ) -> list[dict]:
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
            # Drop ancient entries; cache can grow
            # unbounded on heavy panning otherwise.
            stale = now - self.ttl_sec * 4
            self._by_bbox = {
                k: e for k, e in self._by_bbox.items()
                if e.fetched_at > stale
            }
        return items


_cache = PirepCache()


async def get_pireps(bbox: tuple) -> list[dict]:
    return await _cache.get_or_fetch(bbox)


async def _fetch(bbox: tuple) -> list[dict]:
    lat_s, lon_w, lat_n, lon_e = bbox
    params = {
        "bbox": f"{lat_s},{lon_w},{lat_n},{lon_e}",
        "format": "geojson",
        "age": "2",  # hours
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
            "PIREP fetch failed bbox=%s: %s", bbox, exc,
        )
        return []
    feats = gj.get("features") or []
    return [
        _normalize(f) for f in feats
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _normalize(f: dict) -> dict:
    """GeoJSON Feature → flat PIREP dict.

    ``fltlvl`` is in hundreds of feet (so FL220 = 22);
    keep it in that spec-native form but also expose
    a convenience ``alt_ft`` for renderer code that
    wants raw feet.  Missing fltlvl is left None —
    the reporter didn't include an altitude.
    """
    props = f.get("properties", {}) or {}
    geom = f.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None]
    lon = float(coords[0]) if coords[0] is not None else None
    lat = float(coords[1]) if coords[1] is not None else None
    fltlvl = props.get("fltlvl")
    alt_ft = (
        int(fltlvl) * 100
        if isinstance(fltlvl, (int, float))
        else None
    )
    return {
        "id": (
            f"PIREP-{props.get('receiptTime','')}-"
            f"{props.get('icaoId','?')}-{lat},{lon}"
        ),
        "icao": props.get("icaoId"),
        "lat": lat,
        "lon": lon,
        "fl_100ft": fltlvl,
        "alt_ft": alt_ft,
        "airep_type": props.get("airepType"),
        "ac_type": props.get("acType"),
        "aircraft": props.get("aircraft"),
        "wake": props.get("wake"),
        "fltlvl_type": props.get("fltlvlType"),
        "obs_time": props.get("obsTime"),
        "receipt_time": props.get("receiptTime"),
        "raw": props.get("rawOb"),
    }
