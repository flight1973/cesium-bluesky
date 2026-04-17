"""Eby geometric conflict resolution.

Computes the minimum velocity change along the relative
velocity vector to clear the PZ boundary. Produces the
smallest possible deviation from the original trajectory.

Port of BlueSky's Eby plugin.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M, FT_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """Eby resolution — minimal deviation along relative velocity."""
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
        if abs(tcpa) < 0.01:
            tcpa = 0.01

        cls1 = ac1.get('airspace_class', 'G')
        cls2 = ac2.get('airspace_class', 'G')
        s1 = _SEP_BY_CLASS.get(cls1, (5.0, 1000.0, 300.0))
        s2 = _SEP_BY_CLASS.get(cls2, (5.0, 1000.0, 300.0))
        rpz = min(s1[0], s2[0]) * NM_TO_M

        x1, y1 = _ll_to_xy(ac1['lat'], ac1['lon'], ref_lat)
        x2, y2 = _ll_to_xy(ac2['lat'], ac2['lon'], ref_lat)

        gs1 = (ac1.get('gs_kt', 0) or 0) * KT_TO_MS
        trk1 = (ac1.get('trk_deg', 0) or 0) * math.pi / 180
        gs2 = (ac2.get('gs_kt', 0) or 0) * KT_TO_MS
        trk2 = (ac2.get('trk_deg', 0) or 0) * math.pi / 180

        ve1 = gs1 * math.sin(trk1)
        vn1 = gs1 * math.cos(trk1)
        ve2 = gs2 * math.sin(trk2)
        vn2 = gs2 * math.cos(trk2)

        dx = x2 - x1
        dy = y2 - y1
        dvx = ve2 - ve1
        dvy = vn2 - vn1

        # Position at CPA
        cpax = dx + dvx * tcpa
        cpay = dy + dvy * tcpa
        dcpa = math.sqrt(cpax * cpax + cpay * cpay)

        if dcpa >= rpz or dcpa < 0.01:
            continue

        # Eby: push along the CPA direction to clear PZ
        intrusion = rpz - dcpa
        ux = cpax / dcpa
        uy = cpay / dcpa

        # Velocity change magnitude
        dv_mag = intrusion / tcpa

        # Split equally
        half = dv_mag * 0.5
        dve = ux * half
        dvn = uy * half

        if id1 not in dv_accum:
            dv_accum[id1] = [0.0, 0.0]
        dv_accum[id1][0] -= dve
        dv_accum[id1][1] -= dvn

        if id2 not in dv_accum:
            dv_accum[id2] = [0.0, 0.0]
        dv_accum[id2][0] += dve
        dv_accum[id2][1] += dvn

    advisories = {}
    for cid, (de, dn) in dv_accum.items():
        ac = ac_by_id.get(cid)
        if not ac:
            continue

        gs = (ac.get('gs_kt', 0) or 0) * KT_TO_MS
        trk = (ac.get('trk_deg', 0) or 0) * math.pi / 180
        oe = gs * math.sin(trk)
        on = gs * math.cos(trk)

        new_e = oe + de
        new_n = on + dn
        new_gs = math.sqrt(new_e * new_e + new_n * new_n)
        new_gs = max(30 * KT_TO_MS, min(gs * 1.3, new_gs))
        new_trk = math.atan2(new_e, new_n) * 180 / math.pi
        new_trk = (new_trk + 360) % 360

        trk_deg = trk * 180 / math.pi
        dhdg = new_trk - trk_deg
        while dhdg > 180: dhdg -= 360
        while dhdg < -180: dhdg += 360

        advisories[cid] = {
            'dhdg_deg': round(dhdg, 1),
            'dspd_kt': round((new_gs - gs) * MS_TO_KT, 1),
            'dvs_fpm': 0,
            'new_hdg': round(new_trk, 1),
            'new_spd_kt': round(new_gs * MS_TO_KT, 0),
            'new_vs_fpm': round((ac.get('vs_fpm', 0) or 0), 0),
        }

    return advisories
