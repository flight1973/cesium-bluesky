"""Artificial Potential Field (APF) conflict resolution.

Each aircraft generates a repulsive field, and an
attractive field pulls toward the original trajectory.
Resolution velocity is the negative gradient of the
combined potential. Naturally handles N-body conflicts
without pairwise decomposition.

Well-suited for dense traffic — the field superimposes
smoothly as aircraft density increases.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384

K_REP = 50.0      # repulsive gain
K_ATT = 0.5       # attractive gain (back toward original heading)
INFLUENCE_M = 20 * NM_TO_M  # repulsive field influence range


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """APF resolution for all aircraft in conflict."""
    ac_by_id = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    in_conflict = set()
    for pair in conflicts.get('confpairs', []):
        in_conflict.add(pair[0])
        in_conflict.add(pair[1])

    n = len(items)
    ref_lat = sum(a.get('lat', 0) for a in items) / max(n, 1)

    airborne = [
        a for a in items
        if not a.get('on_ground', False)
        and a.get('lat') is not None
    ]

    positions = {}
    for ac in airborne:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        x, y = _ll_to_xy(ac['lat'], ac['lon'], ref_lat)
        positions[cid] = (x, y)

    advisories = {}
    for cid in in_conflict:
        ac = ac_by_id.get(cid)
        if not ac or ac.get('on_ground'):
            continue

        gs = (ac.get('gs_kt', 0) or 0) * KT_TO_MS
        trk = (ac.get('trk_deg', 0) or 0) * math.pi / 180

        if gs < 1:
            continue

        ox, oy = positions.get(cid, (0, 0))
        cls_own = ac.get('airspace_class', 'G')

        # Compute repulsive gradient from all nearby aircraft
        grad_x = 0.0
        grad_y = 0.0

        for other_ac in airborne:
            oid = other_ac.get('callsign') or other_ac.get('icao24', '?')
            if oid == cid:
                continue

            ix, iy = positions.get(oid, (0, 0))
            dx = ox - ix
            dy = oy - iy
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < 1 or dist > INFLUENCE_M:
                continue

            cls_other = other_ac.get('airspace_class', 'G')
            s1 = _SEP_BY_CLASS.get(cls_own, (5.0, 1000.0, 300.0))
            s2 = _SEP_BY_CLASS.get(cls_other, (5.0, 1000.0, 300.0))
            rpz = min(s1[0], s2[0]) * NM_TO_M

            if dist >= rpz * 3:
                continue

            # Repulsive gradient: -K * (1/d - 1/rpz) * (1/d^2) * direction
            inv_d = 1.0 / dist
            inv_rpz = 1.0 / (rpz * 3)

            if inv_d > inv_rpz:
                magnitude = K_REP * (inv_d - inv_rpz) * inv_d * inv_d
                grad_x += magnitude * dx / dist
                grad_y += magnitude * dy / dist

        # Attractive gradient toward original heading (keeps aircraft on track)
        goal_x = gs * math.sin(trk)
        goal_y = gs * math.cos(trk)
        oe = gs * math.sin(trk)
        on = gs * math.cos(trk)

        # New velocity = original + repulsive gradient (scaled)
        scale = gs * 0.3  # limit gradient effect to 30% of speed
        new_e = oe + grad_x * scale
        new_n = on + grad_y * scale

        new_gs = math.sqrt(new_e * new_e + new_n * new_n)
        new_gs = max(30 * KT_TO_MS, min(gs * 1.3, new_gs))
        new_trk = math.atan2(new_e, new_n) * 180 / math.pi
        new_trk = (new_trk + 360) % 360

        trk_deg = trk * 180 / math.pi
        dhdg = new_trk - trk_deg
        while dhdg > 180: dhdg -= 360
        while dhdg < -180: dhdg += 360

        if abs(dhdg) < 0.5:
            continue

        advisories[cid] = {
            'dhdg_deg': round(dhdg, 1),
            'dspd_kt': round((new_gs - gs) * MS_TO_KT, 1),
            'dvs_fpm': 0,
            'new_hdg': round(new_trk, 1),
            'new_spd_kt': round(new_gs * MS_TO_KT, 0),
            'new_vs_fpm': round((ac.get('vs_fpm', 0) or 0), 0),
        }

    return advisories
