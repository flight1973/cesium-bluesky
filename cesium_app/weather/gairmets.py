"""G-AIRMET fetcher + cache (aviationweather.gov).

G-AIRMETs are the graphical-native AIRMET product —
distinct from the text AIRMETs we read from the
``airsigmet`` feed.  Key differences:

- Forecasters draw polygons directly (not derived from
  ``FROM X to Y`` boundary syntax).
- Time-sliced into 3-hour forecast snapshots
  (``forecastHour`` of 0, 3, 6, 9, or 12).
- Shipped as structured JSON; no text to decode.
- Hazard categories grouped into three products:
  SIERRA (IFR / mt obsc), TANGO (turbulence /
  surface winds / LLWS), ZULU (icing / freezing
  level).

API reference: <https://aviationweather.gov/data/api/>.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://aviationweather.gov/api/data/gairmet"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 300
FETCH_TIMEOUT_SEC = 15.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class GairmetCache:
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


_cache = GairmetCache()


async def get_gairmets() -> list[dict]:
    """Public entry — cached G-AIRMET list."""
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
        logger.warning("gairmet fetch failed: %s", exc)
        return []
    return [_normalize(a) for a in raw if a.get("coords")]


def _parse_alt_ft(v) -> float | None:
    """G-AIRMET top/base come as strings.

    Common values: ``"FL180"``, ``"18000"``, ``""``,
    ``"SFC"``.  Returns feet or None.
    """
    if v is None or v == "":
        return None
    s = str(v).strip().upper()
    if s in ("SFC", "SURFACE"):
        return 0.0
    if s.startswith("FL"):
        try:
            return float(s[2:]) * 100.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize(g: dict) -> dict:
    """G-AIRMET → SIGMET-compatible shape.

    Same keys as the airsigmet normalized entry, so the
    frontend can feed both feeds into one manager.
    ``type`` is ``"G-AIRMET"`` so visibility toggles
    can distinguish.
    """
    coords = [
        (float(c["lat"]), float(c["lon"]))
        for c in (g.get("coords") or [])
        if c.get("lat") not in (None, "")
        and c.get("lon") not in (None, "")
    ]
    top_ft = _parse_alt_ft(g.get("top"))
    base_ft = _parse_alt_ft(g.get("base"))
    bottom = base_ft if base_ft is not None else 0.0
    top = top_ft if top_ft is not None else 60000.0

    gid = (
        f"GAIRMET-{g.get('product', '?')}-"
        f"{g.get('tag', '?')}-"
        f"{g.get('forecastHour', '?')}"
    )

    return {
        "id": gid,
        "type": "G-AIRMET",
        "hazard": g.get("hazard"),
        "severity": g.get("severity") or None,
        # G-AIRMET uses valid_time not from/to; approximate
        # validity as [valid_time, valid_time + 3h] so UIs
        # that use validity bands have something sane.
        "valid_from": g.get("issueTime"),
        "valid_to": g.get("expireTime"),
        "bottom_ft": bottom,
        "top_ft": top,
        "movement_dir": None,
        "movement_spd": None,
        "coords": coords,
        "raw": g.get("due_to") or "",
        "icao": None,
        # Extra G-AIRMET metadata.
        "forecast_hour": g.get("forecastHour"),
        "product": g.get("product"),  # SIERRA/TANGO/ZULU
        "tag": g.get("tag"),
        "due_to": g.get("due_to"),
    }
