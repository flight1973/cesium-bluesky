"""Class B / C / D / E controlled airspace.

Source: FAA Aeronautical Information Services ArcGIS
FeatureServer — the public endpoint behind the FAA's
published sectionals and IFR charts.

Each feature is one shelf of controlled airspace, with
altitude band carried in ``LOWER_VAL`` / ``UPPER_VAL``
(+ unit-of-measure).  Complex shapes like Class B
"inverted wedding cakes" decompose into multiple
features each representing one shelf.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from cesium_app.airspace.tfrs import _extract_rings
from cesium_app.store import airspace_cache

logger = logging.getLogger(__name__)

# Source tag must match cesium_app.ingest.SOURCE_CLASS.
_DB_SOURCE = "class_airspace"

_FEATURE_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/"
    "arcgis/rest/services/Class_Airspace/FeatureServer/"
    "0/query"
)
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
CACHE_TTL_SEC = 3600  # AIRAC cycle = 56 days; 1 hr is plenty
FETCH_TIMEOUT_SEC = 60.0

# The FeatureServer times out on large single-page
# queries; paginate at 500 records per page to stay
# under the gateway timeout.
PAGE_SIZE = 500


@dataclass
class _CacheEntry:
    fetched_at: float
    items: list[dict]


@dataclass
class ClassAirspaceCache:
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


_cache = ClassAirspaceCache()


async def get_class_airspace(
    classes: set[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """Controlled airspace shelves, optionally filtered.

    * ``classes``: set of single-letter class codes
      {'B','C','D','E'}.  None = all.
    * ``bbox``: ``(lat_s, lon_w, lat_n, lon_e)`` to
      restrict with the DB R-tree.  None = global.

    Prefers the persistent SQLite cache when populated
    (run ``python -m cesium_app.ingest classes`` to
    fill it).  Falls back to the live FAA fetcher with
    an in-memory TTL cache when the DB is empty —
    handy for dev / first-run without an ingest pass.
    """
    wanted = (
        {c.upper() for c in classes} if classes else None
    )
    if await asyncio.to_thread(
        airspace_cache.has_source, _DB_SOURCE,
    ):
        return await asyncio.to_thread(
            airspace_cache.query,
            type_="CLASS",
            subtypes=wanted,
            bbox=bbox,
        )
    # DB empty → live fetch path.
    items = await _cache.get_or_fetch()
    if wanted:
        items = [
            a for a in items
            if (a.get("airspace_class") or "").upper() in wanted
        ]
    if bbox is not None:
        lat_s, lon_w, lat_n, lon_e = bbox
        items = [
            a for a in items
            if _intersects_bbox(
                a.get("rings") or [],
                lat_s, lon_w, lat_n, lon_e,
            )
        ]
    return items


def _intersects_bbox(
    rings: list,
    lat_s: float, lon_w: float,
    lat_n: float, lon_e: float,
) -> bool:
    """Cheap bbox-vs-bbox ring intersection.

    Used only on the live-fetch fallback path; the DB
    path uses an R-tree instead.
    """
    for ring in rings:
        if not ring:
            continue
        lats = [p[0] for p in ring]
        lons = [p[1] for p in ring]
        if (min(lats) <= lat_n and max(lats) >= lat_s
                and min(lons) <= lon_e
                and max(lons) >= lon_w):
            return True
    return False


_PAGE_RETRY_MAX = 4
_PAGE_RETRY_BACKOFF_SEC = (2.0, 5.0, 15.0, 30.0)


async def _fetch_page(
    client: httpx.AsyncClient, offset: int,
) -> list[dict]:
    """Fetch one page; retry on transient 5xx / timeouts.

    The ArcGIS server intermittently returns 504 on
    pages that succeed seconds later — usually a
    backend cache miss.  Retry with exponential
    backoff before giving up.  4xx responses are
    real errors and bubble straight up.
    """
    params = {
        "where": "1=1",
        "outFields": (
            "CLASS,NAME,LOCAL_TYPE,UPPER_VAL,"
            "UPPER_UOM,LOWER_VAL,LOWER_UOM,"
            "IDENT,ICAO_ID"
        ),
        "f": "geojson",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
    }
    last_exc: Exception | None = None
    for attempt in range(_PAGE_RETRY_MAX):
        try:
            res = await client.get(_FEATURE_URL, params=params)
            res.raise_for_status()
            gj = res.json()
            return gj.get("features", []) or []
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # 4xx = caller error, no point retrying.
            if 400 <= status < 500:
                raise
            last_exc = exc
        except (httpx.TimeoutException,
                httpx.TransportError, ValueError) as exc:
            last_exc = exc
        delay = _PAGE_RETRY_BACKOFF_SEC[
            min(attempt, len(_PAGE_RETRY_BACKOFF_SEC) - 1)
        ]
        logger.warning(
            "Class airspace page offset=%d attempt %d/%d "
            "failed (%s); retrying in %.1fs",
            offset, attempt + 1, _PAGE_RETRY_MAX,
            last_exc, delay,
        )
        await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def _fetch() -> list[dict]:
    """Paginated fetch across the ArcGIS FeatureServer.

    The server 504s on single large queries; 500-record
    pages return in a couple seconds each.  Loops until
    a short page signals end of data.  Each page retries
    transient failures so a single hiccup doesn't
    truncate the dataset.
    """
    all_features: list[dict] = []
    offset = 0
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SEC, headers=headers,
    ) as client:
        while True:
            try:
                feats = await _fetch_page(client, offset)
            except Exception as exc:  # noqa: BLE001
                # Exhausted retries — log and stop, but
                # surface what we have rather than wipe.
                logger.error(
                    "Class airspace page at offset=%d "
                    "exhausted retries: %s", offset, exc,
                )
                break
            all_features.extend(feats)
            if len(feats) < PAGE_SIZE:
                break  # last page
            offset += PAGE_SIZE
            if offset > 50_000:
                logger.warning(
                    "Class airspace pagination cap hit",
                )
                break
    logger.info(
        "Class airspace fetch: %d features total",
        len(all_features),
    )
    return [
        _normalize(f) for f in all_features
        if (f.get("geometry") or {}).get("coordinates")
    ]


def _to_ft(val: float | None, uom: str | None) -> float | None:
    """Convert FAA (UPPER|LOWER)_VAL → feet.

    Units observed: FT (feet), FL (flight level × 100 ft).
    Missing / None values become None; caller substitutes
    a safe default (0 surface, 60 000 unlimited).

    Sentinel handling: FAA uses large negative values
    (e.g., -9998) for "not applicable" / "open-ended"
    altitudes.  Treat any negative value as None.
    """
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v < 0:
        # Negative = open-ended sentinel.
        return None
    u = (uom or "FT").upper()
    if u == "FL":
        return v * 100.0
    return v


def _normalize(f: dict) -> dict:
    props = f.get("properties", {}) or {}
    rings = _extract_rings(f.get("geometry") or {})

    cls = (props.get("CLASS") or "").strip().upper() or None
    local_type = (props.get("LOCAL_TYPE") or "").strip()
    name = (props.get("NAME") or "").strip()
    ident = (
        props.get("IDENT") or props.get("ICAO_ID") or ""
    ).strip()

    upper = _to_ft(
        props.get("UPPER_VAL"), props.get("UPPER_UOM"),
    )
    lower = _to_ft(
        props.get("LOWER_VAL"), props.get("LOWER_UOM"),
    )

    # Build a stable id — FAA doesn't expose a clean
    # unique key in the props we queried.  Use name +
    # altitude band to disambiguate shelves.
    aid = (
        f"CLASS-{cls or local_type or 'X'}-"
        f"{ident or name}-"
        f"{int(lower or 0)}-{int(upper or 0)}"
    )

    return {
        "id": aid,
        "type": "CLASS",
        "airspace_class": cls,          # B / C / D / E / None
        "local_type": local_type,       # e.g., MODE C
        "name": name,
        "ident": ident,
        "rings": rings,
        "bottom_ft": lower if lower is not None else 0.0,
        "top_ft": upper if upper is not None else 60000.0,
    }
