"""State-Space Diagram (SSD) conflict resolution.

Constructs velocity obstacles (VO cones) for each
intruder in speed-heading space, then finds the closest
conflict-free velocity by sampling the allowable
velocity region boundary.

Simplified standalone port — the full BlueSky SSD uses
pyclipper for exact polygon clipping. This version uses
angular sampling which is faster and dependency-free
but slightly less optimal for dense multi-aircraft cases.

Reference: Hoekstra, van Gent, Ruigrok, "Designing
for Safety: the Free Flight Air Traffic Management
Concept", NLR-TP-2002-100.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384
N_ANGLES = 72


def _is_in_vo(
    ve: float, vn: float,
    intr_ve: float, intr_vn: float,
    dx: float, dy: float,
    rpz: float, dist: float,
) -> bool:
    """Check if a velocity (ve, vn) falls inside a VO cone."""
    if dist < 1:
        return True

    rel_e = ve - intr_ve
    rel_n = vn - intr_vn

    # VO half-angle
    alpha = math.asin(min(0.999, rpz / max(dist, rpz)))

    # Bearing to intruder
    theta = math.atan2(dx, dy)

    # Angle of relative velocity
    rv_angle = math.atan2(rel_e, rel_n)

    diff = rv_angle - theta
    while diff > math.pi: diff -= 2 * math.pi
    while diff < -math.pi: diff += 2 * math.pi

    return abs(diff) < alpha


def _resolve_single(
    own: dict, intruders: list[tuple[dict, float]],
    ref_lat: float,
) -> dict | None:
    """Find closest safe velocity via angular sampling."""
    gs = (own.get('gs_kt', 0) or 0) * KT_TO_MS
    trk = (own.get('trk_deg', 0) or 0) * math.pi / 180
    own_e = gs * math.sin(trk)
    own_n = gs * math.cos(trk)
    ox, oy = _ll_to_xy(own['lat'], own['lon'], ref_lat)

    if gs < 1:
        return None

    vmin = gs * 0.7
    vmax = gs * 1.3

    # Build list of VO parameters
    vos = []
    for intr, rpz in intruders:
        ix, iy = _ll_to_xy(intr['lat'], intr['lon'], ref_lat)
        dx = ix - ox
        dy = iy - oy
        dist = math.sqrt(dx * dx + dy * dy)
        igs = (intr.get('gs_kt', 0) or 0) * KT_TO_MS
        itrk = (intr.get('trk_deg', 0) or 0) * math.pi / 180
        ie = igs * math.sin(itrk)
        ino = igs * math.cos(itrk)
        vos.append((ie, ino, dx, dy, rpz, dist))

    # Check if current velocity is safe
    in_any_vo = False
    for ie, ino, dx, dy, rpz, dist in vos:
        if _is_in_vo(own_e, own_n, ie, ino, dx, dy, rpz, dist):
            in_any_vo = True
            break

    if not in_any_vo:
        return None

    # Sample candidate velocities and find closest safe one
    best_ve = own_e
    best_vn = own_n
    best_cost = float('inf')

    for ai in range(N_ANGLES):
        angle = ai * 2 * math.pi / N_ANGLES
        for speed_frac in [0.7, 0.85, 1.0, 1.15, 1.3]:
            spd = gs * speed_frac
            if spd < vmin * 0.5 or spd > vmax:
                continue
            ce = spd * math.sin(angle)
            cn = spd * math.cos(angle)

            safe = True
            for ie, ino, dx, dy, rpz, dist in vos:
                if _is_in_vo(ce, cn, ie, ino, dx, dy, rpz, dist):
                    safe = False
                    break

            if safe:
                de = ce - own_e
                dn = cn - own_n
                cost = de * de + dn * dn
                if cost < best_cost:
                    best_cost = cost
                    best_ve = ce
                    best_vn = cn

    if best_cost == float('inf'):
        return None

    new_gs = math.sqrt(best_ve * best_ve + best_vn * best_vn)
    new_gs = max(30 * KT_TO_MS, new_gs)
    new_trk = math.atan2(best_ve, best_vn) * 180 / math.pi
    new_trk = (new_trk + 360) % 360

    trk_deg = trk * 180 / math.pi
    dhdg = new_trk - trk_deg
    while dhdg > 180: dhdg -= 360
    while dhdg < -180: dhdg += 360

    return {
        'dhdg_deg': round(dhdg, 1),
        'dspd_kt': round((new_gs - gs) * MS_TO_KT, 1),
        'dvs_fpm': 0,
        'new_hdg': round(new_trk, 1),
        'new_spd_kt': round(new_gs * MS_TO_KT, 0),
        'new_vs_fpm': round((own.get('vs_fpm', 0) or 0), 0),
    }


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """SSD resolution for all conflicting aircraft."""
    ac_by_id = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    in_conflict = set()
    neighbors: dict[str, list[str]] = {}
    for pair in conflicts.get('confpairs', []):
        in_conflict.add(pair[0])
        in_conflict.add(pair[1])
        neighbors.setdefault(pair[0], []).append(pair[1])
        neighbors.setdefault(pair[1], []).append(pair[0])

    n = len(items)
    ref_lat = sum(a.get('lat', 0) for a in items) / max(n, 1)

    advisories = {}
    for cid in in_conflict:
        ac = ac_by_id.get(cid)
        if not ac or ac.get('on_ground'):
            continue

        cls_own = ac.get('airspace_class', 'G')

        intruders = []
        for nid in neighbors.get(cid, []):
            intr = ac_by_id.get(nid)
            if not intr:
                continue
            cls_intr = intr.get('airspace_class', 'G')
            s1 = _SEP_BY_CLASS.get(cls_own, (5.0, 1000.0, 300.0))
            s2 = _SEP_BY_CLASS.get(cls_intr, (5.0, 1000.0, 300.0))
            rpz = min(s1[0], s2[0]) * NM_TO_M
            intruders.append((intr, rpz))

        adv = _resolve_single(ac, intruders, ref_lat)
        if adv:
            advisories[cid] = adv

    return advisories
