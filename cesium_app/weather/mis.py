"""Meteorological Impact Statement (MIS) fetcher.

Issued infrequently by NWS forecasters when
weather is expected to significantly affect ATM
operations.  Free-form text bulletins; no
GeoJSON output is offered upstream — only
``format=raw`` text.

Each MIS reads like:

    MISBOS
    NWS BOSTON MA  ISSUED BY MELLOR
    100815 191300

    SIG WX FORECAST FOR ZBW...

We pass the raw bodies through unchanged plus a
parsed-by-line index so the UI can render
formatted text without losing the source
phrasing.

API: ``aviationweather.gov/api/data/mis?format=raw&age=24``
Currently returns 204 most of the time (MISes
are rare).  Refresh hourly; the ``age`` window
captures any issued in the last 24 hours.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://aviationweather.gov/api/data/mis"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 1800  # 30 min — MISes aren't time-sensitive
FETCH_TIMEOUT_SEC = 15.0
_AGE_HOURS = 24


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class MisCache:
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


_cache = MisCache()


async def get_mises() -> list[dict]:
    return await _cache.get_or_fetch()


async def _fetch() -> list[dict]:
    params = {"format": "raw", "age": str(_AGE_HOURS)}
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
            body = res.text
    except httpx.HTTPError as exc:
        logger.warning("MIS fetch failed: %s", exc)
        return []
    return _split_bulletins(body)


# Bulletins are separated by a blank line +
# ``MIS<icao>`` header pattern.  The split below
# keeps each bulletin self-contained and tries to
# extract the issuing CWSU + issue time.
_HDR_RE = re.compile(
    r"^MIS([A-Z]{3,4})\s*$", re.MULTILINE,
)


def _split_bulletins(body: str) -> list[dict]:
    if not body.strip():
        return []
    # Find header positions, slice between them.
    positions = [
        (m.start(), m.group(1))
        for m in _HDR_RE.finditer(body)
    ]
    out: list[dict] = []
    if not positions:
        # Fallback: single bulletin without recognized
        # header.  Ship as-is.
        return [{
            "id": f"MIS-{int(time.time())}",
            "cwsu": None,
            "issued": None,
            "raw": body.strip(),
        }]
    for i, (start, cwsu) in enumerate(positions):
        end = (
            positions[i + 1][0]
            if i + 1 < len(positions)
            else len(body)
        )
        chunk = body[start:end].strip()
        out.append({
            "id": f"MIS-{cwsu}-{_first_time(chunk)}",
            "cwsu": cwsu,
            "issued": _first_time(chunk),
            "raw": chunk,
        })
    return out


_TIME_RE = re.compile(r"\b(\d{6})\b")


def _first_time(chunk: str) -> str | None:
    """Extract the first ``DDHHMM`` timestamp."""
    m = _TIME_RE.search(chunk)
    return m.group(1) if m else None
