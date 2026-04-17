"""REST endpoints for cached CIFP procedures.

Serves data from :mod:`cesium_app.store.procedures_cache`,
populated by ``python -m cesium_app.ingest procedures``.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from cesium_app.navdata.pbn import (
    PbnSpec, aircraft_pbn, pbn_label,
    procedure_pbn_requirement,
)
from cesium_app.store import procedures_cache

router = APIRouter(
    prefix="/api/navdata/procedures", tags=["procedures"],
)


@router.get("")
async def list_procedures(
    airport: str = Query(
        ...,
        description="ICAO airport code (e.g., KDFW)",
        min_length=3, max_length=4,
    ),
    proc_type: str | None = Query(
        None,
        description="Filter to one of SID / STAR / IAP",
    ),
    ac_type: str | None = Query(
        None,
        description=(
            "ICAO aircraft type (e.g., B738).  When set, "
            "each procedure is annotated with "
            "``pbn_flyable`` — whether the aircraft's "
            "PBN capability meets the procedure's "
            "requirement.  Procedures the aircraft "
            "can't fly are still returned (for "
            "informational display) but flagged."
        ),
    ),
) -> dict:
    """Procedures for an airport with PBN annotation.

    Each entry includes ``pbn_requirement`` (the
    tightest RNP across the procedure's legs) and,
    when ``ac_type`` is provided, ``pbn_flyable``
    (whether the aircraft can fly it).
    """
    items = await asyncio.to_thread(
        procedures_cache.list_for_airport,
        airport, proc_type=proc_type,
    )
    ac_pbn = aircraft_pbn(ac_type) if ac_type else None
    result_items = []
    for p in items:
        proc_id = p["id"]
        req = await asyncio.to_thread(
            procedure_pbn_requirement, proc_id,
        )
        entry = {
            "id": proc_id,
            "proc_type": p["proc_type"],
            "name": p["name"],
            "transition": p.get("transition"),
            "n_legs": len(p.get("legs", [])),
            "pbn_requirement": pbn_label(req),
            "pbn_rnp_nm": req / 100.0 if req < 99999 else None,
        }
        if ac_pbn is not None:
            entry["pbn_flyable"] = ac_pbn <= req
        result_items.append(entry)
    return {
        "airport": airport.upper(),
        "count": len(result_items),
        "ac_type": ac_type,
        "ac_pbn": pbn_label(ac_pbn) if ac_pbn else None,
        "items": result_items,
    }


@router.get("/{procedure_id:path}")
async def get_procedure_geom(procedure_id: str) -> dict:
    """Compiled polyline + per-fix annotations.

    Returns ``polyline`` as
    ``[[lat, lon, alt_hae_m, alt_msl_ft], …]`` with
    curved legs already sampled, so the frontend just
    renders a Cesium polyline without geometry math.
    """
    geom = await asyncio.to_thread(
        procedures_cache.get_geom, procedure_id,
    )
    if geom is None:
        # Fall back to the raw legs if compilation
        # didn't produce geometry — useful for
        # debugging unhandled leg types.
        proc = await asyncio.to_thread(
            procedures_cache.get_procedure, procedure_id,
        )
        if proc is None:
            raise HTTPException(404, "Procedure not found")
        return {
            "id": procedure_id,
            "compiled": False,
            "raw": proc,
        }
    return {
        "id": procedure_id,
        "compiled": True,
        **geom,
    }
