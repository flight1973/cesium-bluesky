"""REST endpoints for the flight path builder.

Composes ranked SID → airway → STAR routes and
surfaces the airway-graph primitives underneath.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from cesium_app.navdata import route_builder
from cesium_app.store import airways_cache, graph_db

router = APIRouter(prefix="/api/navdata/routes", tags=["routes"])


@router.get("/airway/{name}")
async def get_airway(name: str) -> dict:
    """Ordered fix list for a named airway."""
    rows = await asyncio.to_thread(
        airways_cache.get_airway, name,
    )
    if rows is None:
        raise HTTPException(404, f"Airway {name} not found")
    return {"name": name.upper(), "fixes": rows}


@router.get("/airways-through/{fix_id}")
async def airways_through(fix_id: str) -> dict:
    """Every airway that touches a given fix."""
    rows = await asyncio.to_thread(
        airways_cache.airways_through, fix_id,
    )
    return {"fix_id": fix_id.upper(), "airways": rows}


@router.get("/build")
async def build(
    dep: str = Query(..., min_length=3, max_length=4),
    arr: str = Query(..., min_length=3, max_length=4),
    dep_runway: str = Query(
        "",
        description=(
            "Optional departure runway (e.g., '17R' or "
            "'RW17R').  When set, runway-transition SID "
            "is looked up."
        ),
    ),
    arr_runway: str = Query(
        "",
        description=(
            "Optional arrival runway.  When set, the "
            "runway-transition STAR and candidate IAPs "
            "are included in each route."
        ),
    ),
    max_options: int = Query(5, ge=1, le=20),
) -> dict:
    """Top N SID/airway/STAR combinations dep → arr."""
    routes = await asyncio.to_thread(
        route_builder.build_routes,
        dep, arr,
        dep_runway=dep_runway,
        arr_runway=arr_runway,
        max_options=max_options,
    )
    return {
        "dep": dep.upper(),
        "arr": arr.upper(),
        "count": len(routes),
        "routes": routes,
    }


@router.get("/graph-info")
async def graph_info() -> dict:
    """Neo4j graph size — useful diagnostic."""
    nodes = await asyncio.to_thread(graph_db.node_counts)
    rels = await asyncio.to_thread(graph_db.rel_counts)
    return {"nodes": nodes, "relationships": rels}
