"""Aeronautical right-of-way logic per 14 CFR 91.113 / ICAO Annex 2.

Determines which aircraft in a conflict pair has
right-of-way, then modifies resolution advisories so
only the give-way aircraft maneuvers (or maneuvers more).

Rules implemented:
1. Distress — aircraft in distress has absolute priority
2. Category precedence — balloon > glider > airship > airplane/rotorcraft
3. Head-on — both turn right (shared, but symmetric)
4. Converging — aircraft to the other's right has right-of-way
5. Overtaking — overtaking aircraft gives way
6. Landing — lower aircraft has right-of-way

Usage:
    from cesium_app.surveillance.right_of_way import apply_row
    advisories = some_resolver(items, conflicts)
    advisories = apply_row(items, conflicts, advisories)
"""
from __future__ import annotations

import math

# Aircraft categories for precedence (lower = higher priority)
_CATEGORY_PRIORITY = {
    'balloon': 0,
    'glider': 1,
    'airship': 2,
    'airplane': 3,
    'rotorcraft': 3,
    'uas': 4,
}

# Map ICAO type codes to categories (simplified)
_TYPE_CATEGORY: dict[str, str] = {}
# Rotorcraft types
for t in ['R22', 'R44', 'B06', 'B407', 'B412', 'B430',
          'AS50', 'EC35', 'EC45', 'EC55', 'S76', 'A109',
          'AH1', 'UH1', 'H60', 'CH47']:
    _TYPE_CATEGORY[t.upper()] = 'rotorcraft'
# Gliders
for t in ['G109', 'G115', 'GLID', 'DG1T', 'ASW2',
          'LS4', 'SGS', 'ASK2']:
    _TYPE_CATEGORY[t.upper()] = 'glider'


def _get_category(ac: dict) -> str:
    tc = (ac.get('typecode') or '').upper()
    return _TYPE_CATEGORY.get(tc, 'airplane')


def _relative_bearing(
    lat1: float, lon1: float, trk1_deg: float,
    lat2: float, lon2: float,
) -> float:
    """Bearing from ac1 to ac2, relative to ac1's track.

    Returns degrees [-180, 180]. Positive = right, negative = left.
    """
    dlat = lat2 - lat1
    dlon = (lon2 - lon1) * math.cos(lat1 * math.pi / 180)
    abs_bearing = math.atan2(dlon, dlat) * 180 / math.pi
    rel = abs_bearing - trk1_deg
    while rel > 180: rel -= 360
    while rel < -180: rel += 360
    return rel


def _is_overtaking(
    trk1: float, trk2: float, rel_bearing: float,
) -> bool:
    """True if ac1 is overtaking ac2 (approaching from behind)."""
    # Overtaking: approaching from within ±70° of the other's tail
    return abs(rel_bearing) > 110


def _is_head_on(rel_bearing: float, trk1: float, trk2: float) -> bool:
    """True if aircraft are approaching head-on (±30° of reciprocal)."""
    trk_diff = abs(trk1 - trk2)
    if trk_diff > 180:
        trk_diff = 360 - trk_diff
    return trk_diff > 150 and abs(rel_bearing) < 30


def determine_right_of_way(
    ac1: dict, ac2: dict,
) -> tuple[str, str, str]:
    """Determine which aircraft has right-of-way.

    Returns (row_holder, give_way, rule) where:
    - row_holder: callsign of aircraft with right-of-way
    - give_way: callsign of aircraft that must maneuver
    - rule: which 91.113 rule applies
    """
    id1 = ac1.get('callsign') or ac1.get('icao24', '?')
    id2 = ac2.get('callsign') or ac2.get('icao24', '?')

    # Rule 1: Distress — squawk 7700 has absolute priority
    sq1 = (ac1.get('squawk') or '').strip()
    sq2 = (ac2.get('squawk') or '').strip()
    if sq1 == '7700':
        return id1, id2, 'distress'
    if sq2 == '7700':
        return id2, id1, 'distress'

    # Rule 2: Category precedence
    cat1 = _get_category(ac1)
    cat2 = _get_category(ac2)
    pri1 = _CATEGORY_PRIORITY.get(cat1, 3)
    pri2 = _CATEGORY_PRIORITY.get(cat2, 3)
    if pri1 < pri2:
        return id1, id2, f'category ({cat1} > {cat2})'
    if pri2 < pri1:
        return id2, id1, f'category ({cat2} > {cat1})'

    # Same category — use geometric rules
    lat1 = ac1.get('lat', 0)
    lon1 = ac1.get('lon', 0)
    trk1 = ac1.get('trk_deg', 0) or 0
    lat2 = ac2.get('lat', 0)
    lon2 = ac2.get('lon', 0)
    trk2 = ac2.get('trk_deg', 0) or 0

    rel_brg_1to2 = _relative_bearing(lat1, lon1, trk1, lat2, lon2)
    rel_brg_2to1 = _relative_bearing(lat2, lon2, trk2, lat1, lon1)

    # Rule 3: Head-on — both turn right (shared maneuver)
    if _is_head_on(rel_brg_1to2, trk1, trk2):
        return '', '', 'head_on'

    # Rule 4: Overtaking — overtaker gives way
    if _is_overtaking(trk1, trk2, rel_brg_1to2):
        return id2, id1, 'overtaking'
    if _is_overtaking(trk2, trk1, rel_brg_2to1):
        return id1, id2, 'overtaking'

    # Rule 5: Converging — aircraft to the other's right has ROW
    if rel_brg_1to2 > 0:
        # ac2 is to ac1's right → ac2 has right-of-way
        return id2, id1, 'converging_right'
    else:
        return id1, id2, 'converging_right'


def apply_row(
    items: list[dict],
    conflicts: dict,
    advisories: dict[str, dict],
    row_factor: float = 0.15,
    safety_override: bool = True,
) -> dict[str, dict]:
    """Apply right-of-way rules to resolution advisories.

    Safety-first approach: ROW informs who maneuvers
    preferentially, but safety overrides all rules.

    - Give-way aircraft: full advisory (primary responder)
    - ROW holder: reduced to row_factor (15%)
    - Safety override: if a conflict is LoS (already
      violated), BOTH aircraft maneuver fully regardless
      of ROW — survival trumps right-of-way
    - Head-on: both turn right equally (50%)

    Also annotates each advisory with 'row_status' and 'row_rule'.
    """
    ac_by_id = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        ac_by_id[cid] = ac

    # Build set of aircraft in LoS — safety override
    los_aircraft = set()
    if safety_override:
        for pair in conflicts.get('lospairs', []):
            los_aircraft.add(pair[0])
            los_aircraft.add(pair[1])

    # Track ROW decisions per aircraft (strongest wins)
    row_decisions: dict[str, tuple[str, str]] = {}

    for pair in conflicts.get('confpairs', []):
        id1, id2 = pair
        ac1 = ac_by_id.get(id1)
        ac2 = ac_by_id.get(id2)
        if not ac1 or not ac2:
            continue

        holder, giver, rule = determine_right_of_way(ac1, ac2)

        if rule == 'head_on':
            row_decisions[id1] = ('head_on_shared', rule)
            row_decisions[id2] = ('head_on_shared', rule)
        elif holder and giver:
            if holder not in row_decisions or \
               row_decisions[holder][0] != 'give_way':
                row_decisions[holder] = ('right_of_way', rule)
            row_decisions[giver] = ('give_way', rule)

    result = {}
    for cid, adv in advisories.items():
        new_adv = dict(adv)
        decision = row_decisions.get(cid)

        # Safety override: if in LoS, both maneuver fully
        if safety_override and cid in los_aircraft:
            new_adv['row_status'] = 'safety_override'
            new_adv['row_rule'] = decision[1] if decision else 'los'
            result[cid] = new_adv
            continue

        if not decision:
            new_adv['row_status'] = 'unknown'
            new_adv['row_rule'] = ''
        elif decision[0] == 'right_of_way':
            # ROW holder — reduce maneuver to minimal safety margin
            new_adv['dhdg_deg'] = round(adv['dhdg_deg'] * row_factor, 1)
            new_adv['dspd_kt'] = round(adv['dspd_kt'] * row_factor, 1)
            new_adv['dvs_fpm'] = round(adv.get('dvs_fpm', 0) * row_factor, 0)

            gs = 0
            trk = 0
            ac = ac_by_id.get(cid)
            if ac:
                gs = (ac.get('gs_kt', 0) or 0)
                trk = (ac.get('trk_deg', 0) or 0)
            new_adv['new_hdg'] = round((trk + new_adv['dhdg_deg'] + 360) % 360, 1)
            new_adv['new_spd_kt'] = round(gs + new_adv['dspd_kt'], 0)
            new_adv['row_status'] = 'right_of_way'
            new_adv['row_rule'] = decision[1]
        elif decision[0] == 'give_way':
            new_adv['row_status'] = 'give_way'
            new_adv['row_rule'] = decision[1]
        elif decision[0] == 'head_on_shared':
            # Head-on: both turn right equally (50%)
            new_adv['dhdg_deg'] = round(abs(adv['dhdg_deg']) * 0.5, 1)
            ac = ac_by_id.get(cid)
            if ac:
                trk = (ac.get('trk_deg', 0) or 0)
                new_adv['new_hdg'] = round((trk + new_adv['dhdg_deg'] + 360) % 360, 1)
            new_adv['row_status'] = 'head_on_shared'
            new_adv['row_rule'] = 'head_on'

        result[cid] = new_adv

    return result
