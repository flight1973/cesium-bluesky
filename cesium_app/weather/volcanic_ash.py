"""Volcanic ash advisory aggregator.

Combines two sources:
1. AWC ISIGMETs with ``hazard='VA'`` — already
   ingested via ``isigmets.py``.  Polygon boundaries
   with movement vectors.
2. NOAA VAAC (Volcanic Ash Advisory Centers) text
   advisories — scraped for eruption metadata
   (volcano name, ash cloud altitude, forecast
   positions).

The frontend renders VA polygons via the existing
``SigmetManager`` (ISIGMETs with hazard=VA use the
vivid-orange style from the AWC GFA palette).
This module adds the VAAC text detail so the
weather panel can surface eruption narratives.

No credentials required — both sources are public.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

from cesium_app.weather import isigmets as isigmets_mod

logger = logging.getLogger(__name__)

# NOAA VAAC products page — lists current advisories.
_VAAC_URL = (
    "https://www.ssd.noaa.gov/VAAC/messages.html"
)
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 1800  # 30 min
FETCH_TIMEOUT_SEC = 15.0


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class VaCache:
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
        items = await _fetch_combined()
        async with self._lock:
            self._entry = _CacheEntry(
                fetched_at=now, items=items,
            )
        return items


_cache = VaCache()


async def get_volcanic_ash() -> list[dict]:
    """All current volcanic ash advisories from
    AWC ISIGMETs + NOAA VAAC text."""
    return await _cache.get_or_fetch()


async def _fetch_combined() -> list[dict]:
    """Merge AWC ISIGMET VA entries with VAAC text
    advisories for a unified view."""
    # 1. AWC ISIGMETs with VA hazard (already normalized
    #    with rings, altitude, movement).
    isigmets = await isigmets_mod.get_isigmets()
    va_isigmets = [
        s for s in isigmets
        if (s.get("hazard") or "").upper() == "VA"
    ]

    # 2. NOAA VAAC text advisories (best-effort scrape;
    #    fails gracefully to empty list if VAAC page
    #    is down or format changes).
    vaac_texts = await _fetch_vaac_texts()

    # Combine: ISIGMET entries carry geometry; VAAC
    # texts carry eruption narrative.  Cross-ref by
    # volcano name when both mention the same event.
    combined = list(va_isigmets)
    for vt in vaac_texts:
        # Check if an ISIGMET already covers this volcano.
        volcano = vt.get("volcano", "").upper()
        match = next(
            (s for s in va_isigmets
             if volcano and volcano in
             (s.get("qualifier") or "").upper()),
            None,
        )
        if match:
            # Enrich the ISIGMET entry with VAAC text.
            match["vaac_text"] = vt.get("raw")
            match["volcano"] = vt.get("volcano")
        else:
            # Standalone VAAC advisory (no matching
            # ISIGMET polygon — display as text only).
            combined.append(vt)
    return combined


async def _fetch_vaac_texts() -> list[dict]:
    """Scrape current VAAC text advisories from NOAA."""
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SEC,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            res = await client.get(_VAAC_URL)
            res.raise_for_status()
            return _parse_vaac_page(res.text)
    except (httpx.HTTPError, Exception) as exc:
        logger.debug("VAAC scrape failed: %s", exc)
        return []


_VOLCANO_RE = re.compile(
    r"VOLCANO:\s*(.+?)(?:\n|$)", re.IGNORECASE,
)
_DTG_RE = re.compile(
    r"DTG:\s*(\d{8}/\d{4}Z)", re.IGNORECASE,
)


def _parse_vaac_page(html: str) -> list[dict]:
    """Extract VAAC advisory blocks from the NOAA
    messages page.  Format is unstable — defensive
    parsing only."""
    # VAAC advisories appear as <pre> blocks.
    blocks = re.findall(
        r"<pre[^>]*>(.*?)</pre>",
        html, re.DOTALL | re.IGNORECASE,
    )
    out: list[dict] = []
    for block in blocks:
        text = block.strip()
        if "VOLCANO:" not in text.upper():
            continue
        volcano_m = _VOLCANO_RE.search(text)
        dtg_m = _DTG_RE.search(text)
        out.append({
            "id": f"VAAC-{(volcano_m.group(1) if volcano_m else 'UNK').strip()[:20]}",
            "type": "VAAC",
            "hazard": "VA",
            "volcano": (
                volcano_m.group(1).strip()
                if volcano_m else None
            ),
            "dtg": dtg_m.group(1) if dtg_m else None,
            "raw": text[:500],
        })
    return out
