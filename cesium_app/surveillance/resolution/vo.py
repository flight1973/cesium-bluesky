"""Velocity Obstacle (VO) conflict resolution.

For each intruder, constructs a cone-shaped forbidden
region in velocity space. Resolution picks the closest
velocity outside all cones.

Reference: Fiorini & Shiller, "Motion Planning in
Dynamic Environments Using Velocity Obstacles", 1998.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M, FT_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384
MS_TO_FPM = 196.85


def _resolve_single(
    own: dict, intruders: list[dict],
    ref_lat: float,
) -> dict | None:
    """Find closest conflict-free velocity for one aircraft."""
    ve = (own.get('gs_kt', 0) or 0) * KT_TO_MS
    trk = (own.get('trk_deg', 0) or 0) * math.pi / 180
    oe = ve * math.sin(trk)
    on = ve * math.cos(trk)
    gs = math.sqrt(oe * oe + on * on)

    ox, oy = _ll_to_xy(own['lat'], own['lon'], ref_lat)

    best_de = 0.0
    best_dn = 0.0
    best_cost = 0.0

    for intr in intruders:
        cls_own = own.get('airspace_class', 'G')
        cls_intr = intr.get('airspace_class', 'G')
        s1 = _SEP_BY_CLASS.get(cls_own, (5.0, 1000.0, 300.0))
        s2 = _SEP_BY_CLASS.get(cls_intr, (5.0, 1000.0, 300.0))
        rpz = min(s1[0], s2[0]) * NM_TO_M

        ix, iy = _ll_to_xy(intr['lat'], intr['lon'], ref_lat)
        dx = ix - ox
        dy = iy - oy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            continue

        iv = (intr.get('gs_kt', 0) or 0) * KT_TO_MS
        it = (intr.get('trk_deg', 0) or 0) * math.pi / 180
        ie = iv * math.sin(it)
        ino = iv * math.cos(it)

        # Relative velocity
        rel_e = oe - ie
        rel_n = on - ino

        # Check if current velocity is inside the VO cone
        # VO apex is at intruder velocity
        # Half-angle of cone
        if dist <= rpz:
            alpha = math.pi / 2
        else:
            alpha = math.asin(min(1.0, rpz / dist))

        # Bearing from own to intruder
        theta = math.atan2(dx, dy)

        # Angle of relative velocity from cone axis
        rel_angle = math.atan2(rel_e, rel_n)
        diff = rel_angle - theta
        while diff > math.pi: diff -= 2 * math.pi
        while diff < -math.pi: diff += 2 * math.pi

        if abs(diff) >= alpha:
            continue  # Not in this VO

        # Push velocity to nearest cone boundary
        if diff >= 0:
            target_angle = theta + alpha + 0.05
        else:
            target_angle = theta - alpha - 0.05

        # New relative velocity along boundary
        rel_speed = math.sqrt(rel_e * rel_e + rel_n * rel_n)
        new_rel_e = rel_speed * math.sin(target_angle)
        new_rel_n = rel_speed * math.cos(target_angle)

        de = (new_rel_e - rel_e) * 0.5
        dn = (new_rel_n - rel_n) * 0.5
        cost = de * de + dn * dn

        if cost > best_cost:
            best_de = de
            best_dn = dn
            best_cost = cost

    if best_cost < 0.01:
        return None

    new_e = oe + best_de
    new_n = on + best_dn
    new_gs = math.sqrt(new_e * new_e + new_n * new_n)
    new_gs = max(30 * KT_TO_MS, min(gs * 1.3, new_gs))
    new_trk = math.atan2(new_e, new_n) * 180 / math.pi
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
    """VO resolution for all conflicting aircraft."""
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

    advisories = {}
    for cid in in_conflict:
        ac = ac_by_id.get(cid)
        if not ac or ac.get('on_ground'):
            continue
        intruders = [
            ac_by_id[p[1]] if p[0] == cid else ac_by_id[p[0]]
            for p in conflicts.get('confpairs', [])
            if (p[0] == cid or p[1] == cid) and
               (p[1] if p[0] == cid else p[0]) in ac_by_id
        ]
        adv = _resolve_single(ac, intruders, ref_lat)
        if adv:
            advisories[cid] = adv

    return advisories
