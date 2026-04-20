"""Pairwise conflict detection for observed/replay traffic.

Implements the same geometric CD logic as BlueSky's ASAS
but operates on the ObservedAircraft dict list from the
live or replay endpoints.

Separation minimums vary by airspace class:
  Class B terminal: 3 NM / 1000 ft / 180 s
  Class C terminal: 3 NM / 1000 ft / 180 s
  Class D tower:    1.5 NM / 500 ft / 120 s
  En route (E/G):   5 NM / 1000 ft / 300 s
"""
from __future__ import annotations

import math

NM_TO_M = 1852.0
FT_TO_M = 0.3048
KT_TO_MS = 0.514444
FPM_TO_MS = 0.00508

DEG_TO_M_LAT = 111_320.0

# Per-airspace-class separation standards:
# (rpz_nm, hpz_ft, tlook_s)
_SEP_BY_CLASS: dict[str, tuple[float, float, float]] = {
    'B': (3.0, 1000.0, 180.0),
    'C': (3.0, 1000.0, 180.0),
    'D': (1.5, 500.0, 120.0),
    'E': (5.0, 1000.0, 300.0),
    'G': (5.0, 1000.0, 300.0),
}

# Defaults for aircraft without airspace_class field
RPZ_NM = 5.0
HPZ_FT = 1000.0
TLOOK_S = 300.0


def _ll_to_xy(
    lat: float, lon: float, ref_lat: float,
) -> tuple[float, float]:
    x = (lon * math.pi / 180) * DEG_TO_M_LAT * math.cos(
        ref_lat * math.pi / 180)
    y = lat * DEG_TO_M_LAT
    return x, y


def _vxy(
    gs_kt: float, trk_deg: float,
) -> tuple[float, float]:
    v = gs_kt * KT_TO_MS
    rad = trk_deg * math.pi / 180
    return v * math.sin(rad), v * math.cos(rad)


def detect_conflicts(
    items: list[dict],
    rpz_nm: float = RPZ_NM,
    hpz_ft: float = HPZ_FT,
    tlook_s: float = TLOOK_S,
) -> dict:
    """Run pairwise conflict detection.

    Returns a dict with:
      confpairs:  [[id1, id2], ...]
      lospairs:   [[id1, id2], ...]
      conf_tcpa:  [seconds, ...]
      conf_dcpa:  [nm, ...]
      nconf_cur:  int
      nlos_cur:   int
    """
    rpz = rpz_nm * NM_TO_M
    hpz = hpz_ft * FT_TO_M

    airborne = [
        a for a in items
        if not a.get('on_ground', False)
        and a.get('lat') is not None
        and a.get('lon') is not None
    ]
    n = len(airborne)

    if n < 2:
        return _empty()

    ref_lat = sum(a['lat'] for a in airborne) / n

    pos = []
    for a in airborne:
        x, y = _ll_to_xy(a['lat'], a['lon'], ref_lat)
        alt = a.get('alt_m', 0) or 0
        vx, vy = _vxy(
            a.get('gs_kt', 0) or 0,
            a.get('trk_deg', 0) or 0,
        )
        vs = (a.get('vs_fpm', 0) or 0) * FPM_TO_MS
        cid = a.get('callsign') or a.get('icao24', '?')
        ac_class = a.get('airspace_class', 'G')
        pos.append((x, y, alt, vx, vy, vs, cid, ac_class))

    confpairs: list[list[str]] = []
    lospairs: list[list[str]] = []
    conf_tcpa: list[float] = []
    conf_dcpa: list[float] = []

    for i in range(n):
        x1, y1, z1, vx1, vy1, vz1, id1, cls1 = pos[i]
        for j in range(i + 1, n):
            x2, y2, z2, vx2, vy2, vz2, id2, cls2 = pos[j]

            # Use the more restrictive (tighter) separation
            # standard of the two aircraft's airspace classes.
            s1 = _SEP_BY_CLASS.get(cls1, (RPZ_NM, HPZ_FT, TLOOK_S))
            s2 = _SEP_BY_CLASS.get(cls2, (RPZ_NM, HPZ_FT, TLOOK_S))
            pair_rpz = min(s1[0], s2[0]) * NM_TO_M
            pair_hpz = min(s1[1], s2[1]) * FT_TO_M
            pair_tlook = min(s1[2], s2[2])

            dx = x2 - x1
            dy = y2 - y1
            dz = z2 - z1
            dvx = vx2 - vx1
            dvy = vy2 - vy1
            dvz = vz2 - vz1

            dh = math.sqrt(dx * dx + dy * dy)
            dv = abs(dz)

            is_los = dh < pair_rpz and dv < pair_hpz

            dvh2 = dvx * dvx + dvy * dvy
            if dvh2 < 1e-6:
                tcpa = 0.0
                dcpa_m = dh
            else:
                tcpa = -(dx * dvx + dy * dvy) / dvh2
                if tcpa < 0:
                    tcpa = 0.0
                px = dx + dvx * tcpa
                py = dy + dvy * tcpa
                dcpa_m = math.sqrt(px * px + py * py)

            dz_at_cpa = abs(dz + dvz * tcpa)

            is_conf = (
                dcpa_m < pair_rpz
                and dz_at_cpa < pair_hpz
                and 0 <= tcpa <= pair_tlook
            )

            if is_los:
                lospairs.append([id1, id2])
                confpairs.append([id1, id2])
                conf_tcpa.append(round(tcpa, 1))
                conf_dcpa.append(
                    round(dcpa_m / NM_TO_M, 2))
            elif is_conf:
                confpairs.append([id1, id2])
                conf_tcpa.append(round(tcpa, 1))
                conf_dcpa.append(
                    round(dcpa_m / NM_TO_M, 2))

    wake_pairs = _detect_wake_violations(airborne)

    return {
        "confpairs": confpairs,
        "lospairs": lospairs,
        "conf_tcpa": conf_tcpa,
        "conf_dcpa": conf_dcpa,
        "wakepairs": wake_pairs,
        "nconf_cur": len(confpairs),
        "nlos_cur": len(lospairs),
        "nwake_cur": len(wake_pairs),
    }


def _detect_wake_violations(
    items: list[dict],
) -> list[dict]:
    """Flag aircraft pairs violating wake separation.

    Runs after geometric CD. Augments the conflict set with
    wake-specific hazards (following too close behind a heavy,
    flying below/through a helicopter's rotor wash zone, etc.)
    that geometric CD alone might miss.
    """
    try:
        from cesium_app.cooperative.wake_model import (
            should_apply_wake_separation,
            rotorcraft_wake_separation_nm,
            minimum_separation_by_type,
            is_rotorcraft,
        )
        from cesium_app.performance.openap_adapter import (
            get_aircraft_props,
        )
    except ImportError:
        return []

    # Emit all wake violations — even if the pair is
    # already flagged by geometric CD, the wake
    # categorization adds useful context.
    wake_pairs: list[dict] = []

    for i in range(len(items)):
        a = items[i]
        if a.get('on_ground', False):
            continue
        a_type = a.get('typecode', '') or ''

        for j in range(len(items)):
            if i == j:
                continue
            b = items[j]
            if b.get('on_ground', False):
                continue

            if not should_apply_wake_separation(a, b):
                continue

            a_mtow = a.get('mtow_kg', 0) or 0
            b_mtow = b.get('mtow_kg', 0) or 0
            if a_mtow == 0 or b_mtow == 0:
                try:
                    if a_mtow == 0:
                        a_mtow = get_aircraft_props(a_type).get('mtow_kg', 70000)
                    if b_mtow == 0:
                        b_mtow = get_aircraft_props(
                            b.get('typecode', '') or ''
                        ).get('mtow_kg', 70000)
                except Exception:
                    continue

            if is_rotorcraft(a_type):
                min_nm = rotorcraft_wake_separation_nm(
                    a_type, a.get('gs_kt', 0) or 0,
                    a_mtow, b_mtow,
                )
                category = 'rotorcraft_wake'
            else:
                min_nm, lead_cat, trail_cat = minimum_separation_by_type(
                    a_mtow, b_mtow,
                )
                category = f'recat_{lead_cat.value}_{trail_cat.value}'
                if min_nm <= 0:
                    continue

            dy_m = (b.get('lat', 0) - a.get('lat', 0)) * DEG_TO_M_LAT
            dx_m = (b.get('lon', 0) - a.get('lon', 0)) * DEG_TO_M_LAT \
                * math.cos(a.get('lat', 0) * math.pi / 180)
            dist_nm = math.sqrt(dx_m * dx_m + dy_m * dy_m) / NM_TO_M

            if dist_nm >= min_nm:
                continue

            id1 = a.get('callsign') or a.get('icao24', '?')
            id2 = b.get('callsign') or b.get('icao24', '?')

            wake_pairs.append({
                "lead": id1,
                "trail": id2,
                "distance_nm": round(dist_nm, 2),
                "required_nm": round(min_nm, 2),
                "category": category,
            })

    return wake_pairs


def _empty() -> dict:
    return {
        "confpairs": [],
        "lospairs": [],
        "conf_tcpa": [],
        "conf_dcpa": [],
        "wakepairs": [],
        "nconf_cur": 0,
        "nlos_cur": 0,
        "nwake_cur": 0,
    }
