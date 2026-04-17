"""REST endpoints for airspace restriction data.

TFRs and SUAs from FAA GeoServer endpoints.  NOTAMs
proper require FAA API credentials and are deferred.
"""
from fastapi import APIRouter, Query

from cesium_app.airspace import classes as classes_mod
from cesium_app.airspace import suas as suas_mod
from cesium_app.airspace import tfrs as tfrs_mod

router = APIRouter(prefix="/api/airspace", tags=["airspace"])


@router.get("/tfrs")
async def list_tfrs() -> dict:
    """Currently active Temporary Flight Restrictions."""
    items = await tfrs_mod.get_tfrs()
    return {"count": len(items), "items": items}


@router.get("/suas")
async def list_suas(
    classes: str = Query(
        "P,R,W,A,M,N",
        description=(
            "Comma-separated single-letter SUA classes "
            "to include.  P=Prohibited, R=Restricted, "
            "W=Warning, A=Alert, M=MOA, N=Nat'l Sec., "
            "T=Training."
        ),
    ),
) -> dict:
    """Special Use Airspace (prohibited, restricted, …)."""
    wanted = {
        c.strip().upper() for c in classes.split(",")
        if c.strip()
    }
    items = await suas_mod.get_suas(wanted)
    return {"count": len(items), "items": items}


@router.get("/classes")
async def list_class_airspace(
    classes: str = Query(
        "B,C,D,E",
        description=(
            "Comma-separated single-letter class codes: "
            "B, C, D, E."
        ),
    ),
    bounds: str | None = Query(
        None,
        description=(
            "Optional 'lat_s,lon_w,lat_n,lon_e' bbox. "
            "Strongly recommended for Class E (4000+ "
            "shelves globally) to keep responses small."
        ),
    ),
) -> dict:
    """Class B/C/D/E controlled airspace shelves.

    Each feature is one shelf (Class B is several
    stacked shelves forming the inverted wedding
    cake; Class E is broad extended coverage).
    """
    wanted = {
        c.strip().upper() for c in classes.split(",")
        if c.strip()
    }
    bbox: tuple[float, float, float, float] | None = None
    if bounds:
        try:
            parts = [float(x) for x in bounds.split(",")]
            if len(parts) == 4:
                bbox = (parts[0], parts[1], parts[2], parts[3])
        except ValueError:
            pass
    items = await classes_mod.get_class_airspace(
        wanted, bbox=bbox,
    )
    return {"count": len(items), "items": items}
