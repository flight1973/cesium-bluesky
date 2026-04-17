"""Boids flocking-based conflict resolution.

Three rules from Reynolds' Boids model adapted for ATM:
1. Separation — steer away from nearby aircraft
2. Alignment — match heading with neighbors (optional)
3. Cohesion — steer toward flow center (optional)

Ideal for very dense traffic (UAM corridors, drone swarms)
where aircraft should flow together rather than scatter.
Weights control the balance between safety and flow.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384

W_SEPARATION = 3.0
W_ALIGNMENT = 0.5
W_COHESION = 0.2
NEIGHBOR_RANGE_M = 15 * NM_TO_M


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """Boids-based resolution — separation-dominant flocking."""
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

    # Pre-compute positions and velocities
    states = {}
    for ac in airborne:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        x, y = _ll_to_xy(ac['lat'], ac['lon'], ref_lat)
        gs = (ac.get('gs_kt', 0) or 0) * KT_TO_MS
        trk = (ac.get('trk_deg', 0) or 0) * math.pi / 180
        states[cid] = {
            'x': x, 'y': y,
            've': gs * math.sin(trk),
            'vn': gs * math.cos(trk),
            'gs': gs, 'trk': trk,
            'cls': ac.get('airspace_class', 'G'),
        }

    advisories = {}
    for cid in in_conflict:
        ac = ac_by_id.get(cid)
        if not ac or cid not in states:
            continue

        own = states[cid]
        if own['gs'] < 1:
            continue

        sep_e = 0.0
        sep_n = 0.0
        align_e = 0.0
        align_n = 0.0
        coh_x = 0.0
        coh_y = 0.0
        neighbor_count = 0

        for oid, other in states.items():
            if oid == cid:
                continue

            dx = own['x'] - other['x']
            dy = own['y'] - other['y']
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < 1 or dist > NEIGHBOR_RANGE_M:
                continue

            s1 = _SEP_BY_CLASS.get(own['cls'], (5.0, 1000.0, 300.0))
            s2 = _SEP_BY_CLASS.get(other['cls'], (5.0, 1000.0, 300.0))
            rpz = min(s1[0], s2[0]) * NM_TO_M

            neighbor_count += 1

            # Separation: push away, stronger when closer
            if dist < rpz * 2:
                strength = (rpz * 2 - dist) / (rpz * 2)
                sep_e += (dx / dist) * strength
                sep_n += (dy / dist) * strength

            # Alignment: match neighbor heading
            align_e += other['ve']
            align_n += other['vn']

            # Cohesion: steer toward center of neighbors
            coh_x += other['x']
            coh_y += other['y']

        if neighbor_count == 0:
            continue

        align_e /= neighbor_count
        align_n /= neighbor_count
        coh_x = coh_x / neighbor_count - own['x']
        coh_y = coh_y / neighbor_count - own['y']

        # Combine forces
        steer_e = (
            W_SEPARATION * sep_e +
            W_ALIGNMENT * (align_e - own['ve']) +
            W_COHESION * coh_x * 0.001
        )
        steer_n = (
            W_SEPARATION * sep_n +
            W_ALIGNMENT * (align_n - own['vn']) +
            W_COHESION * coh_y * 0.001
        )

        # Apply steering to velocity
        scale = own['gs'] * 0.25
        new_e = own['ve'] + steer_e * scale
        new_n = own['vn'] + steer_n * scale

        new_gs = math.sqrt(new_e * new_e + new_n * new_n)
        new_gs = max(30 * KT_TO_MS, min(own['gs'] * 1.3, new_gs))
        new_trk = math.atan2(new_e, new_n) * 180 / math.pi
        new_trk = (new_trk + 360) % 360

        trk_deg = own['trk'] * 180 / math.pi
        dhdg = new_trk - trk_deg
        while dhdg > 180: dhdg -= 360
        while dhdg < -180: dhdg += 360

        if abs(dhdg) < 0.5:
            continue

        advisories[cid] = {
            'dhdg_deg': round(dhdg, 1),
            'dspd_kt': round((new_gs - own['gs']) * MS_TO_KT, 1),
            'dvs_fpm': 0,
            'new_hdg': round(new_trk, 1),
            'new_spd_kt': round(new_gs * MS_TO_KT, 0),
            'new_vs_fpm': round((ac.get('vs_fpm', 0) or 0), 0),
        }

    return advisories
