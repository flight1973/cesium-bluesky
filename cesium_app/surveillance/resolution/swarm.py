"""Swarm conflict resolution — layered MVP.

Extends MVP with three concentric repulsion zones at
7.5 NM, 5 NM, and 2.5 NM with weighted priorities
(10:3:1). Produces smoother behavior in dense traffic
by applying graduated force before the PZ boundary.

Port of BlueSky's Swarm plugin.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M, FT_TO_M,
)
from cesium_app.surveillance.mvp_resolution import (
    resolve_pair, KT_TO_MS, MS_TO_KT,
)

SWARM_LAYERS = [
    (7.5, 10.0),  # outer ring: 7.5 NM, weight 10
    (5.0, 3.0),   # middle ring: 5 NM, weight 3
    (2.5, 1.0),   # inner ring: 2.5 NM, weight 1
]


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """Swarm resolution — layered weighted MVP."""
    ac_by_id = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    n = len(items)
    ref_lat = sum(a.get('lat', 0) for a in items) / max(n, 1)

    dv_accum: dict[str, list[float]] = {}

    for i, pair in enumerate(conflicts.get('confpairs', [])):
        id1, id2 = pair
        ac1 = ac_by_id.get(id1)
        ac2 = ac_by_id.get(id2)
        if not ac1 or not ac2:
            continue

        tcpa = conflicts.get('conf_tcpa', [])[i] if i < len(conflicts.get('conf_tcpa', [])) else 0

        x1, y1 = _ll_to_xy(ac1['lat'], ac1['lon'], ref_lat)
        x2, y2 = _ll_to_xy(ac2['lat'], ac2['lon'], ref_lat)
        dx = x2 - x1
        dy = y2 - y1
        dist_m = math.sqrt(dx * dx + dy * dy)
        qdr_deg = math.atan2(dx, dy) * 180 / math.pi

        cls1 = ac1.get('airspace_class', 'G')
        cls2 = ac2.get('airspace_class', 'G')
        s1 = _SEP_BY_CLASS.get(cls1, (5.0, 1000.0, 300.0))
        s2 = _SEP_BY_CLASS.get(cls2, (5.0, 1000.0, 300.0))
        base_hpz = min(s1[1], s2[1]) * FT_TO_M

        for layer_nm, weight in SWARM_LAYERS:
            layer_rpz = layer_nm * NM_TO_M
            if dist_m > layer_rpz * 1.5:
                continue

            adv1, adv2 = resolve_pair(
                ac1, ac2, layer_rpz, base_hpz,
                tcpa, dist_m, qdr_deg,
            )

            w = 1.0 / weight

            for cid, adv, sign in [(id1, adv1, 1), (id2, adv2, -1)]:
                if cid not in dv_accum:
                    dv_accum[cid] = [0.0, 0.0, 0.0]
                dv_accum[cid][0] += adv['dhdg_deg'] * w
                dv_accum[cid][1] += adv['dspd_kt'] * w
                dv_accum[cid][2] += adv.get('dvs_fpm', 0) * w

    advisories = {}
    for cid, (dhdg, dspd, dvs) in dv_accum.items():
        ac = ac_by_id.get(cid)
        if not ac:
            continue

        gs = (ac.get('gs_kt', 0) or 0)
        trk = (ac.get('trk_deg', 0) or 0)

        new_hdg = (trk + dhdg + 360) % 360
        new_spd = max(30, min(gs * 1.3, gs + dspd))
        new_vs = (ac.get('vs_fpm', 0) or 0) + dvs

        advisories[cid] = {
            'dhdg_deg': round(dhdg, 1),
            'dspd_kt': round(dspd, 1),
            'dvs_fpm': round(dvs, 0),
            'new_hdg': round(new_hdg, 1),
            'new_spd_kt': round(new_spd, 0),
            'new_vs_fpm': round(new_vs, 0),
        }

    return advisories
