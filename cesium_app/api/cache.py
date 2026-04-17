"""REST endpoints for cache freshness / FAA layer status.

Exposes the ``cache_source`` tracking table so the
frontend can show per-layer freshness (last fetched,
next AIRAC refresh, row count, error state).
"""
from fastapi import APIRouter

from cesium_app.ingest import register_all_sources
from cesium_app.store import airspace_cache

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("/sources")
async def list_cache_sources() -> dict:
    """FAA data sources with their current cache state.

    Each entry includes ``last_fetched_at`` (unix
    seconds), ``age_sec``, ``cadence_days`` (expected
    AIRAC cycle), ``next_refresh_at``, a ``stale`` flag,
    and any ``last_error`` message.
    """
    # Ensure the registry is populated even on a fresh
    # DB (first-run friendliness).
    register_all_sources()
    return {"items": airspace_cache.list_sources()}
