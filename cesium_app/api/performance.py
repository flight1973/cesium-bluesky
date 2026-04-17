"""REST endpoints for aircraft performance queries."""
from __future__ import annotations

from fastapi import APIRouter, Query

from cesium_app.performance import openap_adapter as perf
from cesium_app.performance import jsbsim_adapter
from cesium_app.performance import unified

router = APIRouter(
    prefix="/api/performance", tags=["performance"],
)


@router.get("/types")
async def list_types() -> dict:
    """All aircraft types across all performance sources."""
    openap_types = perf.available_types()
    jsb_models = jsbsim_adapter.available_models()
    return {
        "openap_count": len(openap_types),
        "openap_types": openap_types,
        "jsbsim_count": len(jsb_models),
        "jsbsim_models": jsb_models,
        "total": len(set(openap_types) | set(jsb_models)),
    }


@router.get("/lookup/{icao_type}")
async def unified_lookup(icao_type: str) -> dict:
    """Unified lookup — best available data from any source."""
    return unified.lookup(icao_type)


@router.get("/coverage")
async def coverage() -> dict:
    """Coverage report across all performance sources."""
    return unified.coverage_report()


@router.get("/aircraft/{icao_type}")
async def aircraft_props(icao_type: str) -> dict:
    """Full aircraft specifications + drag polar."""
    return perf.get_aircraft_props(icao_type)


@router.get("/engine/{icao_type}")
async def engine_props(icao_type: str) -> dict:
    """Engine specifications for an aircraft type."""
    return perf.get_engine_props(icao_type)


@router.get("/envelope/{icao_type}")
async def kinematic_envelope(icao_type: str) -> dict:
    """Kinematic envelope — speed/altitude/climb/descent
    limits with statistical distributions from real
    flight data."""
    return perf.get_kinematic_envelope(icao_type)


@router.get("/thrust/{icao_type}")
async def thrust(
    icao_type: str,
    phase: str = Query(..., description="climb, cruise, descent, takeoff"),
    tas_kt: float = Query(250),
    alt_ft: float = Query(10000),
    roc_fpm: float = Query(0),
) -> dict:
    """Compute thrust for a given flight condition."""
    t = perf.compute_thrust(icao_type, phase, tas_kt, alt_ft, roc_fpm=roc_fpm)
    return {"thrust_n": t, "thrust_lbf": t * 0.22481}


@router.get("/drag/{icao_type}")
async def drag(
    icao_type: str,
    mass_kg: float = Query(60000),
    tas_kt: float = Query(250),
    alt_ft: float = Query(10000),
    flap_angle: float = Query(0),
    gear_down: bool = Query(False),
) -> dict:
    """Compute aerodynamic drag."""
    d = perf.compute_drag(
        icao_type, mass_kg, tas_kt, alt_ft,
        flap_angle, gear_down,
    )
    return {"drag_n": d, "drag_lbf": d * 0.22481}


@router.get("/fuelflow/{icao_type}")
async def fuel_flow(
    icao_type: str,
    phase: str = Query("cruise"),
    mass_kg: float = Query(60000),
    tas_kt: float = Query(250),
    alt_ft: float = Query(35000),
) -> dict:
    """Compute fuel flow rate."""
    ff = perf.compute_fuel_flow(
        icao_type, phase, mass_kg, tas_kt, alt_ft,
    )
    return {
        "fuel_flow_kgs": ff,
        "fuel_flow_kgh": ff * 3600,
        "fuel_flow_lbh": ff * 3600 * 2.20462,
    }


@router.get("/emissions/{icao_type}")
async def emissions(
    icao_type: str,
    fuel_flow_kgs: float = Query(0.7),
    tas_kt: float = Query(460),
    alt_ft: float = Query(35000),
) -> dict:
    """Compute emissions (CO2, H2O, NOx, CO, HC)."""
    return perf.compute_emissions(
        icao_type, fuel_flow_kgs, tas_kt, alt_ft,
    )


@router.get("/atmosphere")
async def atmosphere(
    alt_ft: float = Query(35000),
) -> dict:
    """ISA atmospheric properties at altitude."""
    return perf.atmosphere(alt_ft)


@router.get("/speed-convert")
async def speed_convert(
    value: float = Query(...),
    from_unit: str = Query(..., description="cas_kt, tas_kt, or mach"),
    alt_ft: float = Query(35000),
) -> dict:
    """Convert between CAS, TAS, and Mach at altitude."""
    return perf.convert_speed(value, from_unit, alt_ft)


@router.get("/crossover")
async def crossover(
    cas_kt: float = Query(250),
    mach: float = Query(0.78),
) -> dict:
    """CAS/Mach crossover altitude."""
    alt = perf.crossover_altitude(cas_kt, mach)
    return {"crossover_alt_ft": alt}


@router.get("/distance")
async def distance(
    lat1: float = Query(...), lon1: float = Query(...),
    lat2: float = Query(...), lon2: float = Query(...),
) -> dict:
    """Geodesic distance and bearing between two points."""
    return perf.geodesic_distance(lat1, lon1, lat2, lon2)


@router.get("/trajectory/{icao_type}")
async def trajectory(
    icao_type: str,
    dt: int = Query(30, description="Time step in seconds"),
    mass_fraction: float = Query(0.85),
) -> dict:
    """Generate a complete climb-cruise-descent trajectory."""
    pts = perf.generate_trajectory(icao_type, dt, mass_fraction)
    return {"count": len(pts), "points": pts}
