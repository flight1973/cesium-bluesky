"""ORCA — Optimal Reciprocal Collision Avoidance.

Each aircraft pair shares responsibility by computing
half-plane constraints. The resolution finds the closest
velocity to the current one that satisfies all constraints.
Guaranteed deadlock-free for any number of agents.

Reference: van den Berg et al., "Reciprocal n-Body
Collision Avoidance", 2011.
"""
from __future__ import annotations

import math

from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M, FT_TO_M,
)

KT_TO_MS = 0.514444
MS_TO_KT = 1.94384


def _orca_halfplane(
    own_pos: tuple, own_vel: tuple,
    intr_pos: tuple, intr_vel: tuple,
    rpz: float, tau: float,
) -> tuple[tuple, tuple] | None:
    """Compute ORCA half-plane for one intruder.

    Returns (point, normal) defining the constraint
    half-plane, or None if no constraint needed.
    """
    dx = intr_pos[0] - own_pos[0]
    dy = intr_pos[1] - own_pos[1]
    dvx = own_vel[0] - intr_vel[0]
    dvy = own_vel[1] - intr_vel[1]

    dist_sq = dx * dx + dy * dy
    rpz_sq = rpz * rpz

    if dist_sq <= rpz_sq:
        # Already in collision — push directly away
        dist = math.sqrt(dist_sq) or 0.01
        nx = -dx / dist
        ny = -dy / dist
        w_mag = rpz - dist
        return ((dvx + nx * w_mag * 0.5, dvy + ny * w_mag * 0.5), (nx, ny))

    # Truncated VO — check if relative velocity points
    # into the truncated cone
    # Center of truncation circle
    cx = dx / tau
    cy = dy / tau
    cut_r = rpz / tau

    wx = dvx - cx
    wy = dvy - cy
    w_sq = wx * wx + wy * wy

    if w_sq <= cut_r * cut_r:
        # Inside truncation circle — project out
        w_len = math.sqrt(w_sq) or 0.01
        nx = wx / w_len
        ny = wy / w_len
        u_mag = cut_r - w_len
        return ((dvx + nx * u_mag * 0.5, dvy + ny * u_mag * 0.5), (nx, ny))

    # Check if on the leg of the cone
    dot = wx * dx + wy * dy
    if dot < 0:
        return None  # Behind the cone — no constraint

    # Project onto the nearest leg
    leg_sq = dist_sq - rpz_sq
    if leg_sq <= 0:
        return None
    leg = math.sqrt(leg_sq)

    # Left or right leg
    if dx * wy - dy * wx > 0:
        # Left leg
        nx = dx * leg + dy * rpz
        ny = -dx * rpz + dy * leg
    else:
        # Right leg
        nx = dx * leg - dy * rpz
        ny = dx * rpz + dy * leg

    n_len = math.sqrt(nx * nx + ny * ny) or 1
    nx /= n_len
    ny /= n_len

    dot_w_n = wx * nx + wy * ny
    if dot_w_n >= 0:
        return None

    u_mag = -dot_w_n
    return ((dvx + nx * u_mag * 0.5, dvy + ny * u_mag * 0.5), (nx, ny))


def _solve_constraints(
    pref_vx: float, pref_vy: float,
    constraints: list[tuple[tuple, tuple]],
    max_speed: float,
) -> tuple[float, float]:
    """Find closest velocity to preferred that satisfies
    all half-plane constraints."""
    vx, vy = pref_vx, pref_vy

    for point, normal in constraints:
        # Check if current velocity violates this constraint
        dx = vx - point[0]
        dy = vy - point[1]
        dot = dx * normal[0] + dy * normal[1]

        if dot < 0:
            # Violated — project onto the half-plane boundary
            vx -= dot * normal[0]
            vy -= dot * normal[1]

    # Clamp to max speed
    speed = math.sqrt(vx * vx + vy * vy)
    if speed > max_speed:
        vx *= max_speed / speed
        vy *= max_speed / speed

    return vx, vy


def resolve_all(
    items: list[dict], conflicts: dict,
) -> dict[str, dict]:
    """ORCA resolution for all conflicting aircraft."""
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
    tau = 30.0  # time horizon

    advisories = {}
    for cid in in_conflict:
        ac = ac_by_id.get(cid)
        if not ac or ac.get('on_ground'):
            continue

        gs = (ac.get('gs_kt', 0) or 0) * KT_TO_MS
        trk = (ac.get('trk_deg', 0) or 0) * math.pi / 180
        own_e = gs * math.sin(trk)
        own_n = gs * math.cos(trk)
        ox, oy = _ll_to_xy(ac['lat'], ac['lon'], ref_lat)

        constraints = []
        for nid in neighbors.get(cid, []):
            intr = ac_by_id.get(nid)
            if not intr:
                continue

            cls1 = ac.get('airspace_class', 'G')
            cls2 = intr.get('airspace_class', 'G')
            s1 = _SEP_BY_CLASS.get(cls1, (5.0, 1000.0, 300.0))
            s2 = _SEP_BY_CLASS.get(cls2, (5.0, 1000.0, 300.0))
            rpz = min(s1[0], s2[0]) * NM_TO_M

            igs = (intr.get('gs_kt', 0) or 0) * KT_TO_MS
            itrk = (intr.get('trk_deg', 0) or 0) * math.pi / 180
            ie = igs * math.sin(itrk)
            ino = igs * math.cos(itrk)
            ix, iy = _ll_to_xy(intr['lat'], intr['lon'], ref_lat)

            hp = _orca_halfplane(
                (ox, oy), (own_e, own_n),
                (ix, iy), (ie, ino),
                rpz, tau,
            )
            if hp:
                constraints.append(hp)

        if not constraints:
            continue

        max_speed = gs * 1.3
        new_e, new_n = _solve_constraints(
            own_e, own_n, constraints, max_speed,
        )

        new_gs = math.sqrt(new_e * new_e + new_n * new_n)
        new_gs = max(30 * KT_TO_MS, new_gs)
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
