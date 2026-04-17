"""Social Force Model conflict resolution.

Adapted from Helbing & Molnar's pedestrian dynamics
model. Each aircraft experiences:
1. Desired force — toward its intended trajectory
2. Repulsive force — exponential decay from neighbors
3. Boundary force — from airspace boundaries (optional)

The exponential repulsion produces smooth, natural-looking
separation behavior that scales gracefully with density.
Used successfully in pedestrian, vehicle, and drone swarm
simulation.

Reference: Helbing & Molnar, "Social force model for
pedestrian dynamics", 1995.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384

TAU = 0.5          # relaxation time (lower = faster response)
A_REP = 2000.0     # repulsion amplitude [m/s^2 equivalent]
B_REP = 3000.0     # repulsion range [m] (decay constant)
RANGE_M = 20 * NM_TO_M


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """Social Force resolution for all conflicting aircraft."""
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

        # Desired velocity = current (maintain trajectory)
        desired_e = own['ve']
        desired_n = own['vn']

        # Driving force (toward desired velocity)
        f_drive_e = (desired_e - own['ve']) / TAU
        f_drive_n = (desired_n - own['vn']) / TAU

        # Repulsive force from neighbors (exponential)
        f_rep_e = 0.0
        f_rep_n = 0.0

        for oid, other in states.items():
            if oid == cid:
                continue

            dx = own['x'] - other['x']
            dy = own['y'] - other['y']
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < 1 or dist > RANGE_M:
                continue

            s1 = _SEP_BY_CLASS.get(own['cls'], (5.0, 1000.0, 300.0))
            s2 = _SEP_BY_CLASS.get(other['cls'], (5.0, 1000.0, 300.0))
            rpz = min(s1[0], s2[0]) * NM_TO_M

            # Exponential repulsion: F = A * exp((rpz - d) / B) * n_hat
            # Stronger when closer to PZ
            exp_arg = (rpz - dist) / B_REP
            if exp_arg > 10:
                exp_arg = 10
            magnitude = A_REP * math.exp(exp_arg)

            n_x = dx / dist
            n_y = dy / dist
            f_rep_e += magnitude * n_x
            f_rep_n += magnitude * n_y

        # Total force → velocity change
        total_e = f_drive_e + f_rep_e
        total_n = f_drive_n + f_rep_n

        # Apply as velocity change (dt = ~1 second equivalent)
        dt = 1.0
        scale = min(1.0, own['gs'] * 0.3 / (math.sqrt(total_e**2 + total_n**2) or 1))
        new_e = own['ve'] + total_e * dt * scale
        new_n = own['vn'] + total_n * dt * scale

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
