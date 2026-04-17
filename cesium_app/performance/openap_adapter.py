"""OpenAP integration for aircraft performance queries.

Wraps openap's Thrust, Drag, FuelFlow, Emission, WRAP,
and prop modules into a unified service that:

  - Caches model instances per aircraft type
  - Maps ICAO type codes to OpenAP's lowercase codes
  - Falls back to a default type (B738) for unsupported aircraft
  - Provides a REST-friendly summary dict per type

Covers 36 aircraft types natively (A318-A388, B734-B789,
E145/E170/E190/E195/E75L, C550, GLF6, plus MAX/NEO variants).
"""
from __future__ import annotations

import logging
from functools import lru_cache

import openap

logger = logging.getLogger(__name__)

_AVAILABLE = set(openap.prop.available_aircraft())
_DEFAULT = 'b738'


def _resolve(icao_type: str) -> str:
    """Map ICAO type code to OpenAP key."""
    key = icao_type.strip().lower()
    if key in _AVAILABLE:
        return key
    aliases: dict[str, str] = {
        'b73g': 'b737', 'b73h': 'b738', 'b73j': 'b739',
        'b74s': 'b744', 'b74f': 'b748',
        'b75w': 'b752', 'b76w': 'b763',
        'b77l': 'b772', 'b77e': 'b77w',
        'b78x': 'b789',
        'a318': 'a318', 'a319': 'a319',
        'a20n': 'a20n', 'a21n': 'a21n',
        'a332': 'a332', 'a333': 'a333',
        'a342': 'a343', 'a343': 'a343',
        'a35k': 'a359',
        'a380': 'a388',
        'e135': 'e145', 'e140': 'e145',
        'e75s': 'e75l', 'e75n': 'e75l',
        'e290': 'e195',
        'crj9': 'e170', 'crj7': 'e170',
        'c56x': 'c550', 'c560': 'c550', 'c25a': 'c550',
        'cl60': 'glf6', 'cl65': 'e145',
        'glex': 'glf6', 'gl5t': 'glf6',
    }
    resolved = aliases.get(key)
    if resolved and resolved in _AVAILABLE:
        return resolved
    return _DEFAULT


def is_supported(icao_type: str) -> bool:
    return _resolve(icao_type) != _DEFAULT or icao_type.strip().lower() == _DEFAULT


def available_types() -> list[str]:
    return sorted(_AVAILABLE)


@lru_cache(maxsize=64)
def _thrust(key: str) -> openap.Thrust:
    return openap.Thrust(key)

@lru_cache(maxsize=64)
def _drag(key: str) -> openap.Drag:
    return openap.Drag(key)

@lru_cache(maxsize=64)
def _fuel(key: str) -> openap.FuelFlow:
    return openap.FuelFlow(key)

@lru_cache(maxsize=64)
def _emission(key: str) -> openap.Emission:
    return openap.Emission(key)

@lru_cache(maxsize=64)
def _wrap(key: str) -> openap.WRAP:
    return openap.WRAP(key)


def get_aircraft_props(icao_type: str) -> dict:
    key = _resolve(icao_type)
    ac = openap.prop.aircraft(key)
    return {
        "openap_key": key,
        "name": ac.get("aircraft", ""),
        "mtow_kg": ac.get("mtow", 0),
        "mlw_kg": ac.get("mlw", 0),
        "oew_kg": ac.get("oew", 0),
        "mfc_kg": ac.get("mfc", 0),
        "ceiling_m": ac.get("ceiling", 0),
        "vmo_kt": ac.get("vmo", 0),
        "mmo": ac.get("mmo", 0),
        "cruise_mach": ac.get("cruise", {}).get("mach", 0),
        "cruise_alt_m": ac.get("cruise", {}).get("height", 0),
        "wing_area_m2": ac.get("wing", {}).get("area", 0),
        "wing_span_m": ac.get("wing", {}).get("span", 0),
        "pax_max": ac.get("pax", {}).get("max", 0),
        "engine_count": ac.get("engine", {}).get("number", 0),
        "engine_name": ac.get("engine", {}).get("default", ""),
        "cd0": ac.get("drag", {}).get("cd0", 0),
        "oswald_e": ac.get("drag", {}).get("e", 0),
        "supported": key != _DEFAULT or icao_type.strip().lower() == _DEFAULT,
    }


def get_engine_props(icao_type: str) -> dict:
    key = _resolve(icao_type)
    ac = openap.prop.aircraft(key)
    eng_name = ac.get("engine", {}).get("default", "")
    if not eng_name:
        return {}
    eng = openap.prop.engine(eng_name)
    return {
        "name": eng.get("name", ""),
        "manufacturer": eng.get("manufacturer", ""),
        "bpr": eng.get("bpr", 0),
        "max_thrust_n": eng.get("max_thrust", 0),
        "ff_takeoff_kgs": eng.get("ff_to", 0),
        "ff_cruise_kgs": eng.get("ff_co", 0),
        "ff_approach_kgs": eng.get("ff_app", 0),
        "ff_idle_kgs": eng.get("ff_idl", 0),
    }


def get_kinematic_envelope(icao_type: str) -> dict:
    key = _resolve(icao_type)
    w = _wrap(key)
    return {
        "openap_key": key,
        "takeoff_speed_kt": w.takeoff_speed(),
        "initclimb_cas_kt": w.initclimb_vcas(),
        "initclimb_vs_ms": w.initclimb_vs(),
        "climb_cas_kt": w.climb_const_vcas(),
        "climb_mach": w.climb_const_mach(),
        "climb_vs_concas_ms": w.climb_vs_concas(),
        "climb_vs_conmach_ms": w.climb_vs_conmach(),
        "cruise_alt_km": w.cruise_alt(),
        "cruise_mach": w.cruise_mach(),
        "descent_cas_kt": w.descent_const_vcas(),
        "descent_mach": w.descent_const_mach(),
        "descent_vs_concas_ms": w.descent_vs_concas(),
        "finalapp_cas_kt": w.finalapp_vcas(),
        "finalapp_vs_ms": w.finalapp_vs(),
        "landing_speed_kt": w.landing_speed(),
    }


def compute_thrust(
    icao_type: str, phase: str,
    tas_kt: float, alt_ft: float,
    mass_kg: float | None = None,
    roc_fpm: float = 0,
) -> float:
    key = _resolve(icao_type)
    t = _thrust(key)
    if phase == 'climb':
        return float(t.climb(tas=tas_kt, alt=alt_ft, roc=roc_fpm))
    elif phase == 'cruise':
        return float(t.cruise(tas=tas_kt, alt=alt_ft))
    elif phase == 'descent':
        return float(t.descent_idle(tas=tas_kt, alt=alt_ft))
    elif phase == 'takeoff':
        return float(t.takeoff())
    return 0.0


def compute_drag(
    icao_type: str, mass_kg: float,
    tas_kt: float, alt_ft: float,
    flap_angle: float = 0,
    gear_down: bool = False,
) -> float:
    key = _resolve(icao_type)
    d = _drag(key)
    if flap_angle > 0 or gear_down:
        return float(d.nonclean(
            mass=mass_kg, tas=tas_kt, alt=alt_ft,
            flap_angle=flap_angle,
            landing_gear=gear_down,
        ))
    return float(d.clean(mass=mass_kg, tas=tas_kt, alt=alt_ft))


def compute_fuel_flow(
    icao_type: str, phase: str,
    mass_kg: float | None = None,
    tas_kt: float = 0, alt_ft: float = 0,
    roc_fpm: float = 0,
) -> float:
    key = _resolve(icao_type)
    f = _fuel(key)
    if phase == 'takeoff':
        return float(f.takeoff())
    elif phase == 'climb':
        return float(f.enroute(
            mass=mass_kg or 60000, tas=tas_kt, alt=alt_ft,
        ))
    elif phase == 'cruise':
        return float(f.enroute(
            mass=mass_kg or 60000, tas=tas_kt, alt=alt_ft,
        ))
    elif phase == 'descent':
        return float(f.enroute(
            mass=mass_kg or 60000, tas=tas_kt, alt=alt_ft,
        ))
    return 0.0


# ── Aero / Atmosphere ──────────────────────────────────

from openap import aero as _aero


def atmosphere(alt_ft: float) -> dict:
    """ISA atmospheric properties at altitude."""
    h = alt_ft * _aero.ft
    return {
        "alt_ft": alt_ft,
        "alt_m": h,
        "temperature_k": float(_aero.temperature(h)),
        "temperature_c": float(_aero.temperature(h) - 273.15),
        "pressure_pa": float(_aero.pressure(h)),
        "pressure_hpa": float(_aero.pressure(h) / 100),
        "density_kgm3": float(_aero.density(h)),
        "speed_of_sound_ms": float(_aero.vsound(h)),
        "speed_of_sound_kt": float(_aero.vsound(h) / _aero.kts),
    }


def convert_speed(
    value: float, from_unit: str, alt_ft: float = 0,
) -> dict:
    """Convert between CAS, TAS, Mach at a given altitude."""
    h = alt_ft * _aero.ft
    result: dict = {"alt_ft": alt_ft}
    if from_unit == 'cas_kt':
        cas_ms = value * _aero.kts
        tas_ms = _aero.cas2tas(cas_ms, h)
        result["cas_kt"] = value
        result["tas_kt"] = float(tas_ms / _aero.kts)
        result["mach"] = float(_aero.tas2mach(tas_ms, h))
    elif from_unit == 'tas_kt':
        tas_ms = value * _aero.kts
        result["tas_kt"] = value
        result["cas_kt"] = float(_aero.tas2cas(tas_ms, h) / _aero.kts)
        result["mach"] = float(_aero.tas2mach(tas_ms, h))
    elif from_unit == 'mach':
        tas_ms = _aero.mach2tas(value, h)
        result["mach"] = value
        result["tas_kt"] = float(tas_ms / _aero.kts)
        result["cas_kt"] = float(_aero.tas2cas(tas_ms, h) / _aero.kts)
    return result


def crossover_altitude(cas_kt: float, mach: float) -> float:
    """Altitude where CAS and Mach schedules intersect."""
    return float(
        _aero.crossover_alt(cas_kt * _aero.kts, mach) / _aero.ft
    )


# ── Geodesic ──────────────────────────────────────────


def geodesic_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> dict:
    d = _aero.distance(lat1, lon1, lat2, lon2)
    b = _aero.bearing(lat1, lon1, lat2, lon2)
    return {
        "distance_m": float(d),
        "distance_km": float(d / 1000),
        "distance_nm": float(d / _aero.nm),
        "distance_mi": float(d / 1609.344),
        "bearing_deg": float(b),
    }


# ── Flight Phase Detection ────────────────────────────


def detect_flight_phases(
    timestamps: list[float],
    altitudes_ft: list[float],
    speeds_kt: list[float],
    vertical_rates_fpm: list[float],
) -> list[str]:
    """Detect flight phases from state vectors.

    Returns one label per point: GND, CL, CR, DE, LVL, NA.
    """
    import numpy as np
    fp = openap.FlightPhase()
    fp.set_trajectory(
        np.array(timestamps),
        np.array(altitudes_ft) * _aero.ft,
        np.array(speeds_kt) * _aero.kts,
        np.array(vertical_rates_fpm) * _aero.fpm,
    )
    return list(fp.phaselabel())


# ── Flight Generator ──────────────────────────────────


def generate_trajectory(
    icao_type: str,
    dt_seconds: int = 30,
    mass_fraction: float = 0.85,
) -> list[dict]:
    """Generate a complete climb-cruise-descent trajectory.

    Returns list of waypoints with t, alt_ft, gs_kt, vs_fpm.
    """
    key = _resolve(icao_type)
    gen = openap.FlightGenerator(ac=key)
    traj = gen.complete(dt=dt_seconds, m0=mass_fraction)
    result = []
    for _, row in traj.iterrows():
        result.append({
            "t": float(row["t"]),
            "alt_ft": float(row["altitude"]),
            "alt_m": float(row["h"]),
            "gs_kt": float(row["groundspeed"]),
            "vs_fpm": float(row["vertical_rate"]),
            "speed_ms": float(row["v"]),
            "distance_m": float(row["s"]),
        })
    return result


def compute_emissions(
    icao_type: str, fuel_flow_kgs: float,
    tas_kt: float = 0, alt_ft: float = 0,
) -> dict:
    key = _resolve(icao_type)
    e = _emission(key)
    return {
        "co2_kgs": float(e.co2(fuel_flow_kgs)),
        "h2o_kgs": float(e.h2o(fuel_flow_kgs)),
        "nox_kgs": float(e.nox(fuel_flow_kgs, tas=tas_kt, alt=alt_ft)),
        "co_kgs": float(e.co(fuel_flow_kgs, tas=tas_kt, alt=alt_ft)),
        "hc_kgs": float(e.hc(fuel_flow_kgs, tas=tas_kt, alt=alt_ft)),
    }
