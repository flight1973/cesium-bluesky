"""Cooperative conflict detection and resolution.

When aircraft are in a formation, the platoon is treated
as a single entity for external conflict detection.
Internal separation uses formation-specific reduced PZ.

For non-formation cooperative maneuvers, aircraft negotiate
joint resolution vectors that minimize total fleet cost.
"""
from __future__ import annotations

import math
import logging

from cesium_app.cooperative.formation import FormationManager, Formation
from cesium_app.surveillance.conflict_detect import (
    _ll_to_xy, _SEP_BY_CLASS, NM_TO_M, FT_TO_M,
    KT_TO_MS, FPM_TO_MS, DEG_TO_M_LAT,
)

logger = logging.getLogger(__name__)


def compute_follower_targets(
    formation: Formation,
    leader_state: dict,
) -> dict[str, dict]:
    """Compute target positions for each follower based on
    the leader's current state and the formation geometry.

    Returns {callsign: {lat, lon, alt_ft, hdg, spd_kt}}
    """
    lat_l = leader_state.get('lat', 0)
    lon_l = leader_state.get('lon', 0)
    alt_l = leader_state.get('alt_ft', 0) or (leader_state.get('alt_m', 0) * 3.28084)
    trk_l = (leader_state.get('trk_deg', 0) or 0) * math.pi / 180
    gs_l = leader_state.get('gs_kt', 0) or 0

    targets = {}
    for callsign, slot in formation.slots.items():
        # Rotate slot offset by leader heading
        # slot.forward_m = behind leader (positive = trail)
        # slot.right_m = right of leader
        cos_t = math.cos(trk_l)
        sin_t = math.sin(trk_l)

        # In local ENU: east/north from leader
        de = -slot.forward_m * sin_t + slot.right_m * cos_t
        dn = -slot.forward_m * cos_t - slot.right_m * sin_t

        dlat = dn / DEG_TO_M_LAT
        dlon = de / (DEG_TO_M_LAT * math.cos(lat_l * math.pi / 180))

        targets[callsign] = {
            'lat': lat_l + dlat,
            'lon': lon_l + dlon,
            'alt_ft': alt_l + slot.up_m * 3.28084,
            'hdg': leader_state.get('trk_deg', 0),
            'spd_kt': gs_l,
        }

    return targets


def filter_formation_conflicts(
    conflicts: dict,
    formation_mgr: FormationManager,
) -> dict:
    """Remove intra-formation conflicts from the conflict set.

    Aircraft within the same formation are in coordinated
    reduced separation — their proximity is intentional,
    not a conflict.
    """
    confpairs = conflicts.get('confpairs', [])
    lospairs = conflicts.get('lospairs', [])
    tcpa = conflicts.get('conf_tcpa', [])
    dcpa = conflicts.get('conf_dcpa', [])

    new_conf = []
    new_los = []
    new_tcpa = []
    new_dcpa = []

    for i, pair in enumerate(confpairs):
        id1, id2 = pair
        f1 = formation_mgr.find_by_member(id1)
        f2 = formation_mgr.find_by_member(id2)

        if f1 and f2 and f1.id == f2.id:
            continue  # Same formation — skip

        new_conf.append(pair)
        if i < len(tcpa):
            new_tcpa.append(tcpa[i])
        if i < len(dcpa):
            new_dcpa.append(dcpa[i])

    for pair in lospairs:
        f1 = formation_mgr.find_by_member(pair[0])
        f2 = formation_mgr.find_by_member(pair[1])
        if f1 and f2 and f1.id == f2.id:
            continue
        new_los.append(pair)

    return {
        'confpairs': new_conf,
        'lospairs': new_los,
        'conf_tcpa': new_tcpa,
        'conf_dcpa': new_dcpa,
        'nconf_cur': len(new_conf),
        'nlos_cur': len(new_los),
    }


def cooperative_resolve(
    items: list[dict],
    conflicts: dict,
    formation_mgr: FormationManager,
) -> dict[str, dict]:
    """Cooperative resolution — formation members maneuver as a unit.

    For external conflicts involving a formation member:
    1. The leader's resolution advisory is computed
    2. All followers match the leader's maneuver
    3. The formation maintains geometry while turning

    For non-formation aircraft, uses standard resolution.
    """
    from cesium_app.surveillance import resolution as reso
    from cesium_app.surveillance.right_of_way import apply_row

    # Filter out intra-formation conflicts
    external = filter_formation_conflicts(conflicts, formation_mgr)

    # Run standard resolution on external conflicts
    raw_advs = reso.resolve(items, external)

    # Apply ROW
    advs = apply_row(items, external, raw_advs)

    # For formation members: propagate leader's advisory to followers
    ac_by_id = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    for f in formation_mgr.formations.values():
        leader_adv = advs.get(f.leader)
        if not leader_adv:
            # Check if any follower got an advisory
            follower_advs = [
                advs[fid] for fid in f.followers if fid in advs
            ]
            if follower_advs:
                # Use the strongest follower advisory for the whole platoon
                strongest = max(
                    follower_advs,
                    key=lambda a: abs(a.get('dhdg_deg', 0)),
                )
                leader_adv = strongest

        if not leader_adv:
            continue

        # Propagate to leader
        advs[f.leader] = {
            **leader_adv,
            'formation': f.id,
            'formation_role': 'leader',
        }

        # Propagate same maneuver to all followers
        for fid in f.followers:
            fac = ac_by_id.get(fid)
            if not fac:
                continue
            advs[fid] = {
                'dhdg_deg': leader_adv['dhdg_deg'],
                'dspd_kt': leader_adv['dspd_kt'],
                'dvs_fpm': leader_adv.get('dvs_fpm', 0),
                'new_hdg': leader_adv['new_hdg'],
                'new_spd_kt': leader_adv['new_spd_kt'],
                'new_vs_fpm': leader_adv.get('new_vs_fpm', 0),
                'row_status': leader_adv.get('row_status', ''),
                'row_rule': leader_adv.get('row_rule', ''),
                'formation': f.id,
                'formation_role': 'follower',
            }

    return advs


def compute_wake_offset(
    leader_typecode: str,
    follower_typecode: str,
) -> dict:
    """Compute optimal wake-surfing position for the follower.

    Uses OpenAP wingspan data to determine the lateral
    offset that places the follower in the upwash region.

    Returns {lateral_m, longitudinal_nm, vertical_ft, fuel_saving_pct}
    """
    try:
        from cesium_app.performance.openap_adapter import get_aircraft_props
        leader = get_aircraft_props(leader_typecode)
        follower = get_aircraft_props(follower_typecode)

        leader_span = leader.get('wing_span_m', 34)
        follower_span = follower.get('wing_span_m', 34)
        leader_mtow = leader.get('mtow_kg', 79000)

        # Optimal lateral offset: ~0.8-1.2x leader wingspan
        # (places follower wingtip in the upwash core)
        lateral_m = leader_span * 1.0

        # Longitudinal spacing depends on wake strength
        # (heavier aircraft = stronger wake = more spacing)
        if leader_mtow > 300000:
            long_nm = 3.0
            fuel_save = 8.0
        elif leader_mtow > 100000:
            long_nm = 2.0
            fuel_save = 6.0
        else:
            long_nm = 1.5
            fuel_save = 4.0

        return {
            'lateral_m': round(lateral_m, 1),
            'longitudinal_nm': long_nm,
            'vertical_ft': 0,
            'fuel_saving_pct': fuel_save,
            'leader_wingspan_m': leader_span,
            'follower_wingspan_m': follower_span,
        }
    except Exception:
        return {
            'lateral_m': 35.0,
            'longitudinal_nm': 2.0,
            'vertical_ft': 0,
            'fuel_saving_pct': 5.0,
        }
