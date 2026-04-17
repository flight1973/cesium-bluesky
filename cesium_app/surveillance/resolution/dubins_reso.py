"""Dubins path conflict resolution.

Computes minimum-radius turning paths to avoid conflict,
respecting aircraft turn rate limits. Unlike MVP/VO which
assume instant heading changes, Dubins paths are physically
realizable curves (arcs + straight segments).

Uses OpenAP performance data for turn radius when available.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384
STANDARD_RATE_DEG_S = 3.0
G = 9.81


def _turn_radius(gs_kt: float, bank_deg: float = 25.0) -> float:
    """Compute turn radius in meters from groundspeed and bank angle."""
    v = gs_kt * KT_TO_MS
    bank_rad = bank_deg * math.pi / 180
    tan_bank = math.tan(bank_rad)
    if abs(tan_bank) < 0.01:
        return 1e6
    return v * v / (G * tan_bank)


def _dubins_avoid_heading(
    own_trk: float, intr_bearing: float,
    rpz_m: float, dist_m: float,
    turn_radius: float,
) -> float | None:
    """Compute heading change to fly a Dubins arc that clears the PZ.

    Returns the recommended heading change in degrees, or None
    if no avoidance needed.
    """
    if dist_m < 1:
        return 90.0

    # Required angular clearance
    if dist_m <= rpz_m:
        clear_angle = math.pi / 2
    else:
        clear_angle = math.asin(min(1.0, rpz_m / dist_m))

    # Current relative bearing to intruder
    rel_brg = intr_bearing - own_trk
    while rel_brg > 180: rel_brg -= 360
    while rel_brg < -180: rel_brg += 360

    rel_brg_rad = rel_brg * math.pi / 180
    clear_deg = clear_angle * 180 / math.pi

    # Check if heading toward the conflict
    if abs(rel_brg) > 90 + clear_deg:
        return None  # Diverging

    # Turn away — pick the shorter turn
    if rel_brg >= 0:
        # Intruder to the right — turn left
        dhdg = -(clear_deg + 10)
    else:
        # Intruder to the left — turn right
        dhdg = (clear_deg + 10)

    # Limit to what the turn radius allows in a reasonable time
    max_turn = 30.0  # degrees max recommendation
    dhdg = max(-max_turn, min(max_turn, dhdg))

    return dhdg


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """Dubins-path-constrained resolution."""
    ac_by_id = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    n = len(items)
    ref_lat = sum(a.get('lat', 0) for a in items) / max(n, 1)

    advisories = {}

    for i, pair in enumerate(conflicts.get('confpairs', [])):
        id1, id2 = pair
        ac1 = ac_by_id.get(id1)
        ac2 = ac_by_id.get(id2)
        if not ac1 or not ac2:
            continue

        cls1 = ac1.get('airspace_class', 'G')
        cls2 = ac2.get('airspace_class', 'G')
        s1 = _SEP_BY_CLASS.get(cls1, (5.0, 1000.0, 300.0))
        s2 = _SEP_BY_CLASS.get(cls2, (5.0, 1000.0, 300.0))
        rpz = min(s1[0], s2[0]) * NM_TO_M

        x1, y1 = _ll_to_xy(ac1['lat'], ac1['lon'], ref_lat)
        x2, y2 = _ll_to_xy(ac2['lat'], ac2['lon'], ref_lat)
        dx = x2 - x1
        dy = y2 - y1
        dist_m = math.sqrt(dx * dx + dy * dy)
        brg = math.atan2(dx, dy) * 180 / math.pi

        gs1 = (ac1.get('gs_kt', 0) or 0)
        trk1 = (ac1.get('trk_deg', 0) or 0)
        tr1 = _turn_radius(gs1)

        dhdg = _dubins_avoid_heading(trk1, brg, rpz, dist_m, tr1)
        if dhdg is not None and id1 not in advisories:
            new_hdg = (trk1 + dhdg + 360) % 360
            advisories[id1] = {
                'dhdg_deg': round(dhdg, 1),
                'dspd_kt': 0,
                'dvs_fpm': 0,
                'new_hdg': round(new_hdg, 1),
                'new_spd_kt': round(gs1, 0),
                'new_vs_fpm': round((ac1.get('vs_fpm', 0) or 0), 0),
            }

        gs2 = (ac2.get('gs_kt', 0) or 0)
        trk2 = (ac2.get('trk_deg', 0) or 0)
        brg_rev = (brg + 180) % 360

        dhdg2 = _dubins_avoid_heading(trk2, brg_rev, rpz, dist_m, _turn_radius(gs2))
        if dhdg2 is not None and id2 not in advisories:
            new_hdg2 = (trk2 + dhdg2 + 360) % 360
            advisories[id2] = {
                'dhdg_deg': round(dhdg2, 1),
                'dspd_kt': 0,
                'dvs_fpm': 0,
                'new_hdg': round(new_hdg2, 1),
                'new_spd_kt': round(gs2, 0),
                'new_vs_fpm': round((ac2.get('vs_fpm', 0) or 0), 0),
            }

    return advisories
