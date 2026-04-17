"""REST endpoints for formation / platoon management."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from cesium_app.cooperative.formation import (
    FormationManager, FormationType,
)
from cesium_app.cooperative.cooperative_cd import (
    compute_wake_offset,
)

router = APIRouter(
    prefix="/api/formations", tags=["formations"],
)

_mgr = FormationManager()


def get_manager() -> FormationManager:
    return _mgr


class CreateFormationRequest(BaseModel):
    formation_id: str
    leader: str
    followers: list[str]
    formation_type: str = 'trail'
    spacing_nm: float = 1.0


@router.get("")
async def list_formations() -> dict:
    return {"formations": _mgr.list_all()}


@router.post("")
async def create_formation(req: CreateFormationRequest) -> dict:
    try:
        ft = FormationType(req.formation_type)
    except ValueError:
        raise HTTPException(
            400,
            f"Unknown type '{req.formation_type}'. "
            f"Options: {[t.value for t in FormationType]}",
        )
    f = _mgr.create(
        req.formation_id, req.leader, req.followers,
        ft, req.spacing_nm,
    )
    return {
        "id": f.id,
        "leader": f.leader,
        "followers": f.followers,
        "type": f.formation_type.value,
        "size": f.size,
        "slots": {
            k: {"forward_m": v.forward_m, "right_m": v.right_m, "up_m": v.up_m}
            for k, v in f.slots.items()
        },
    }


@router.delete("/{formation_id}")
async def dissolve_formation(formation_id: str) -> dict:
    if not _mgr.dissolve(formation_id):
        raise HTTPException(404, "Formation not found")
    return {"dissolved": formation_id}


@router.post("/{formation_id}/join")
async def join_formation(
    formation_id: str,
    callsign: str = Query(...),
) -> dict:
    if not _mgr.join(formation_id, callsign):
        raise HTTPException(400, "Could not join formation")
    f = _mgr.get(formation_id)
    return {"formation": formation_id, "joined": callsign, "size": f.size if f else 0}


@router.post("/{formation_id}/leave")
async def leave_formation(
    formation_id: str,
    callsign: str = Query(...),
) -> dict:
    if not _mgr.leave(formation_id, callsign):
        raise HTTPException(400, "Could not leave formation")
    return {"formation": formation_id, "left": callsign}


@router.get("/wake-offset")
async def wake_offset(
    leader_type: str = Query(..., description="Leader ICAO type (e.g. B738)"),
    follower_type: str = Query(..., description="Follower ICAO type"),
) -> dict:
    """Compute optimal wake-surfing formation offset."""
    return compute_wake_offset(leader_type, follower_type)


@router.get("/types")
async def formation_types() -> dict:
    return {
        "types": [
            {"id": t.value, "label": t.name.replace('_', ' ').title()}
            for t in FormationType
        ],
    }
