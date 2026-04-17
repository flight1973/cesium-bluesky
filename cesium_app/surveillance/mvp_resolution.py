"""Modified Voltage Potential (MVP) conflict resolution.

Standalone port of BlueSky's MVP algorithm. Computes
velocity vector changes to resolve pairwise conflicts
without requiring aircraft to be in bs.traf.

For each conflict pair, produces a resolution advisory:
recommended heading, speed, and/or vertical speed change
for each aircraft to restore separation.

Reference: Hoekstra, J.M., "Designing for Safety: the
Free Flight Air Traffic Management Concept", 2001.
"""
from __future__ import annotations

import math

NM_TO_M = 1852.0
FT_TO_M = 0.3048
KT_TO_MS = 0.514444
FPM_TO_MS = 0.00508
MS_TO_KT = 1.94384
MS_TO_FPM = 196.85


def _vxy(gs_kt: float, trk_deg: float) -> tuple[float, float]:
    """Ground speed + track → (east, north) m/s components."""
    v = gs_kt * KT_TO_MS
    rad = trk_deg * math.pi / 180
    return v * math.sin(rad), v * math.cos(rad)


def resolve_pair(
    ac1: dict, ac2: dict,
    rpz_m: float,
    hpz_m: float,
    tcpa: float,
    dist_m: float,
    qdr_deg: float,
) -> tuple[dict, dict]:
    """Compute MVP resolution for one conflict pair.

    Returns (advisory1, advisory2) where each advisory is:
    {
        'dhdg_deg': recommended heading change,
        'dspd_kt': recommended speed change,
        'dvs_fpm': recommended vertical speed change,
        'new_hdg': resolved heading,
        'new_spd_kt': resolved speed,
        'new_vs_fpm': resolved vertical speed,
    }
    """
    # Ownship (ac1) state
    gs1 = (ac1.get('gs_kt', 0) or 0) * KT_TO_MS
    trk1 = (ac1.get('trk_deg', 0) or 0) * math.pi / 180
    vs1 = (ac1.get('vs_fpm', 0) or 0) * FPM_TO_MS
    alt1 = (ac1.get('alt_m', 0) or 0)
    ve1 = gs1 * math.sin(trk1)
    vn1 = gs1 * math.cos(trk1)

    # Intruder (ac2) state
    gs2 = (ac2.get('gs_kt', 0) or 0) * KT_TO_MS
    trk2 = (ac2.get('trk_deg', 0) or 0) * math.pi / 180
    vs2 = (ac2.get('vs_fpm', 0) or 0) * FPM_TO_MS
    alt2 = (ac2.get('alt_m', 0) or 0)
    ve2 = gs2 * math.sin(trk2)
    vn2 = gs2 * math.cos(trk2)

    # Relative position (intruder relative to ownship)
    qdr_rad = qdr_deg * math.pi / 180
    dx = math.sin(qdr_rad) * dist_m
    dy = math.cos(qdr_rad) * dist_m
    dz = alt2 - alt1

    # Relative velocity
    dvx = ve2 - ve1
    dvy = vn2 - vn1
    dvz = vs2 - vs1

    # Position at CPA
    t = max(0.01, abs(tcpa))
    cpax = dx + dvx * t
    cpay = dy + dvy * t

    dcpa_h = math.sqrt(cpax * cpax + cpay * cpay)

    # ── Horizontal resolution ──────────────────────
    dv_e = 0.0
    dv_n = 0.0

    if dcpa_h < 10.0:
        # Near head-on — push perpendicular to relative track
        dcpa_h = 10.0
        cpax = dx + 10.0
        cpay = dy

    intrusion_h = rpz_m - dcpa_h
    if intrusion_h > 0 and t > 0.01:
        # Check if intruder is geometrically inside PZ
        if rpz_m >= dist_m and dcpa_h >= dist_m:
            # Outside PZ looking in — apply erratum correction
            arg1 = min(1.0, rpz_m / max(dist_m, 1))
            arg2 = min(1.0, dcpa_h / max(dist_m, 1))
            erratum = math.cos(
                math.asin(arg1) - math.asin(arg2))
            erratum = max(0.01, erratum)
            factor = (rpz_m / erratum - dcpa_h) / (t * dcpa_h)
        else:
            factor = intrusion_h / (t * dcpa_h)

        dv_e = factor * cpax
        dv_n = factor * cpay

    # ── Vertical resolution ────────────────────────
    dv_z = 0.0
    dz_abs = abs(dz)
    dvz_abs = abs(dvz)

    if dz_abs < hpz_m:
        if dvz_abs > 0.01:
            t_solv = dz_abs / dvz_abs
            iv = hpz_m
        else:
            t_solv = t
            iv = hpz_m - dz_abs

        t_solv = max(t_solv, 0.01)
        sign_vz = -1.0 if dvz >= 0 else 1.0
        dv_z = (iv / t_solv) * sign_vz * 0.5

    # ── Split resolution between both aircraft ─────
    # Each aircraft gets half the velocity change
    # (cooperative, equal burden)
    half_dve = dv_e * 0.5
    half_dvn = dv_n * 0.5
    half_dvz = dv_z

    # Advisory for ac1 (ownship maneuvers away)
    new_ve1 = ve1 - half_dve
    new_vn1 = vn1 - half_dvn
    new_vs1 = vs1 + half_dvz

    new_gs1 = math.sqrt(new_ve1 * new_ve1 + new_vn1 * new_vn1)
    new_trk1 = math.atan2(new_ve1, new_vn1) * 180 / math.pi
    new_trk1 = (new_trk1 + 360) % 360

    # Advisory for ac2 (intruder maneuvers away)
    new_ve2 = ve2 + half_dve
    new_vn2 = vn2 + half_dvn
    new_vs2 = vs2 - half_dvz

    new_gs2 = math.sqrt(new_ve2 * new_ve2 + new_vn2 * new_vn2)
    new_trk2 = math.atan2(new_ve2, new_vn2) * 180 / math.pi
    new_trk2 = (new_trk2 + 360) % 360

    trk1_deg = trk1 * 180 / math.pi
    trk2_deg = trk2 * 180 / math.pi

    # Clamp speeds to realistic limits.
    max_gs = max(gs1, gs2) * 1.3
    min_gs = 30 * KT_TO_MS
    new_gs1 = max(min_gs, min(max_gs, new_gs1))
    new_gs2 = max(min_gs, min(max_gs, new_gs2))
    new_vs1 = max(-50, min(50, new_vs1))
    new_vs2 = max(-50, min(50, new_vs2))

    adv1 = {
        'dhdg_deg': round(_wrap180(new_trk1 - trk1_deg), 1),
        'dspd_kt': round((new_gs1 - gs1) * MS_TO_KT, 1),
        'dvs_fpm': round((new_vs1 - vs1) * MS_TO_FPM, 0),
        'new_hdg': round(new_trk1, 1),
        'new_spd_kt': round(new_gs1 * MS_TO_KT, 0),
        'new_vs_fpm': round(new_vs1 * MS_TO_FPM, 0),
    }
    adv2 = {
        'dhdg_deg': round(_wrap180(new_trk2 - trk2_deg), 1),
        'dspd_kt': round((new_gs2 - gs2) * MS_TO_KT, 1),
        'dvs_fpm': round((new_vs2 - vs2) * MS_TO_FPM, 0),
        'new_hdg': round(new_trk2, 1),
        'new_spd_kt': round(new_gs2 * MS_TO_KT, 0),
        'new_vs_fpm': round(new_vs2 * MS_TO_FPM, 0),
    }
    return adv1, adv2


def _wrap180(deg: float) -> float:
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


def resolve_all(
    items: list[dict],
    conflicts: dict,
) -> dict[str, dict]:
    """Compute MVP resolution for all detected conflicts.

    Args:
        items: Aircraft list with lat/lon/alt/gs/trk/vs
        conflicts: Output from detect_conflicts()

    Returns:
        {callsign: advisory_dict} for every aircraft
        involved in at least one conflict. Each advisory
        is the aggregate resolution vector (strongest
        conflict wins).
    """
    from cesium_app.surveillance.conflict_detect import (
        _ll_to_xy, NM_TO_M, FT_TO_M,
    )

    ac_by_id: dict[str, dict] = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    advisories: dict[str, dict] = {}
    confpairs = conflicts.get('confpairs', [])
    conf_tcpa = conflicts.get('conf_tcpa', [])
    conf_dcpa = conflicts.get('conf_dcpa', [])

    n = len(items)
    ref_lat = sum(a.get('lat', 0) for a in items) / max(n, 1)

    for i, pair in enumerate(confpairs):
        id1, id2 = pair
        ac1 = ac_by_id.get(id1)
        ac2 = ac_by_id.get(id2)
        if not ac1 or not ac2:
            continue

        tcpa = conf_tcpa[i] if i < len(conf_tcpa) else 0
        dcpa_nm = conf_dcpa[i] if i < len(conf_dcpa) else 0

        # Compute bearing and distance
        lat1, lon1 = ac1.get('lat', 0), ac1.get('lon', 0)
        lat2, lon2 = ac2.get('lat', 0), ac2.get('lon', 0)
        x1, y1 = _ll_to_xy(lat1, lon1, ref_lat)
        x2, y2 = _ll_to_xy(lat2, lon2, ref_lat)
        dx = x2 - x1
        dy = y2 - y1
        dist_m = math.sqrt(dx * dx + dy * dy)
        qdr_deg = math.atan2(dx, dy) * 180 / math.pi

        # Get per-pair separation from airspace class
        from cesium_app.surveillance.conflict_detect import _SEP_BY_CLASS
        cls1 = ac1.get('airspace_class', 'G')
        cls2 = ac2.get('airspace_class', 'G')
        s1 = _SEP_BY_CLASS.get(cls1, (5.0, 1000.0, 300.0))
        s2 = _SEP_BY_CLASS.get(cls2, (5.0, 1000.0, 300.0))
        rpz_m = min(s1[0], s2[0]) * NM_TO_M
        hpz_m = min(s1[1], s2[1]) * FT_TO_M

        adv1, adv2 = resolve_pair(
            ac1, ac2, rpz_m, hpz_m, tcpa, dist_m, qdr_deg,
        )

        # Keep the strongest advisory per aircraft
        if id1 not in advisories or abs(adv1['dhdg_deg']) > abs(advisories[id1].get('dhdg_deg', 0)):
            advisories[id1] = adv1
        if id2 not in advisories or abs(adv2['dhdg_deg']) > abs(advisories[id2].get('dhdg_deg', 0)):
            advisories[id2] = adv2

    return advisories
