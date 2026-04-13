"""REST endpoints for navigation data (airports, waypoints)."""
import numpy as np

from fastapi import APIRouter, Query, Request

import bluesky as bs

router = APIRouter(prefix="/api/navdata", tags=["navdata"])


@router.get("/airports")
async def get_airports(
    request: Request,
    lat1: float = Query(..., description="South bound"),
    lon1: float = Query(..., description="West bound"),
    lat2: float = Query(..., description="North bound"),
    lon2: float = Query(..., description="East bound"),
    zoom: float = Query(1.0, description="Zoom level"),
) -> list[dict]:
    """Return airports within a bounding box.

    Filters by airport type based on zoom level:
      zoom < 0.5  → large airports only (aptype=1)
      zoom < 3    → large + medium (aptype<=2)
      zoom >= 3   → all airports
    """
    ndb = bs.navdb

    # Filter by type based on zoom.
    if zoom < 0.5:
        type_mask = ndb.aptype == 1
    elif zoom < 3:
        type_mask = ndb.aptype <= 2
    else:
        type_mask = np.ones(len(ndb.aptlat), dtype=bool)

    # Filter by bounding box.
    bbox_mask = (
        (ndb.aptlat >= lat1)
        & (ndb.aptlat <= lat2)
        & (ndb.aptlon >= lon1)
        & (ndb.aptlon <= lon2)
    )
    mask = type_mask & bbox_mask
    indices = np.where(mask)[0]

    # Cap results to avoid huge payloads.
    if len(indices) > 500:
        indices = indices[:500]

    result = []
    rwy_data = ndb.rwythresholds
    for i in indices:
        apt_id = ndb.aptid[i]
        entry = {
            "id": apt_id,
            "lat": float(ndb.aptlat[i]),
            "lon": float(ndb.aptlon[i]),
            "type": int(ndb.aptype[i]),
        }
        # Include runway data if available.
        if apt_id in rwy_data:
            runways = []
            rwys = rwy_data[apt_id]
            seen = set()
            for rname, rinfo in rwys.items():
                pair_key = tuple(sorted([
                    rname,
                    _reciprocal_rwy(rname),
                ]))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                recip = _reciprocal_rwy(rname)
                if recip in rwys:
                    runways.append({
                        "end1": {
                            "name": rname,
                            "lat": rinfo[0],
                            "lon": rinfo[1],
                        },
                        "end2": {
                            "name": recip,
                            "lat": rwys[recip][0],
                            "lon": rwys[recip][1],
                        },
                    })
            entry["runways"] = runways
        result.append(entry)
    return result


@router.get("/waypoints")
async def get_waypoints(
    request: Request,
    lat1: float = Query(..., description="South bound"),
    lon1: float = Query(..., description="West bound"),
    lat2: float = Query(..., description="North bound"),
    lon2: float = Query(..., description="East bound"),
) -> list[dict]:
    """Return waypoints within a bounding box.

    Capped at 1000 results.
    """
    ndb = bs.navdb
    mask = (
        (ndb.wplat >= lat1)
        & (ndb.wplat <= lat2)
        & (ndb.wplon >= lon1)
        & (ndb.wplon <= lon2)
    )
    indices = np.where(mask)[0]
    if len(indices) > 1000:
        indices = indices[:1000]

    return [
        {
            "id": ndb.wpid[i],
            "lat": float(ndb.wplat[i]),
            "lon": float(ndb.wplon[i]),
        }
        for i in indices
    ]


@router.get("/search")
async def search_navdata(
    request: Request,
    q: str = Query(..., description="Search query"),
) -> list[dict]:
    """Search airports and waypoints by ID prefix."""
    q_upper = q.upper()
    results: list[dict] = []
    ndb = bs.navdb

    # Search airports.
    for i, apt_id in enumerate(ndb.aptid):
        if apt_id.startswith(q_upper):
            results.append({
                "id": apt_id,
                "lat": float(ndb.aptlat[i]),
                "lon": float(ndb.aptlon[i]),
                "kind": "airport",
            })
        if len(results) >= 20:
            break

    # Search waypoints.
    for i, wp_id in enumerate(ndb.wpid):
        if wp_id.startswith(q_upper):
            results.append({
                "id": wp_id,
                "lat": float(ndb.wplat[i]),
                "lon": float(ndb.wplon[i]),
                "kind": "waypoint",
            })
        if len(results) >= 40:
            break

    return results


def _reciprocal_rwy(name: str) -> str:
    """Compute the reciprocal runway designator."""
    # Strip any L/R/C suffix.
    suffix = ""
    base = name
    if name and name[-1] in "LRC":
        suffix = name[-1]
        base = name[:-1]
        # Flip L<->R, C stays C.
        suffix = {"L": "R", "R": "L", "C": "C"}[suffix]
    try:
        num = int(base)
        recip_num = (num + 18) % 36
        if recip_num == 0:
            recip_num = 36
        return f"{recip_num:02d}{suffix}"
    except ValueError:
        return name
