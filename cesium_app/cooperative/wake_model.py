"""Wake turbulence modeling.

Two levels of fidelity:

1. Static wake separation rules (RECAT / FAA weight classes)
   - Lookup table: (lead_cat, trail_cat) → minimum separation
   - Used in CD to flag wake-separation violations
   - Applied to approach, departure, and en route trail

2. Dynamic wake vortex physics (Burnham-Hallock core model)
   - Computes actual vortex position as a function of time
   - Decay via Sarpkaya empirical model (atmospheric turbulence)
   - Drifts with crosswind, sinks at ~1-2 m/s initially
   - Enables dynamic pair-based separation (NASA ATD-2 style)

For now we only need the static rules to reject unsafe
pair spacings in CD. Dynamic physics can be added when
we want to render wake vortices or do ATD-2-style dynamic
separation reduction.
"""
from __future__ import annotations

from enum import Enum


class WakeCategory(str, Enum):
    """ICAO RECAT-EU categories. More nuanced than legacy H/M/L."""
    SUPER = 'J'     # A380, AN225 (>560,000 kg)
    UPPER_HEAVY = 'B'  # B744, B748, A340-500/600, A380 family
    LOWER_HEAVY = 'C'  # B777, A330, A350, B787, B767
    UPPER_MEDIUM = 'D' # B737-800/900, A320/321, E190/195
    LOWER_MEDIUM = 'E' # B737-600/700, A319, E170/175, CRJ
    LIGHT = 'F'      # C208, BE20, PC12, SF34 (< 15,400 kg)


# RECAT-EU separation minima (nautical miles, distance-based).
# Zero = no wake minimum (use regular 2.5/3 NM radar separation).
_RECAT_DISTANCE_NM: dict[tuple[str, str], float] = {
    # Lead = SUPER
    ('J', 'J'): 0.0, ('J', 'B'): 4.0, ('J', 'C'): 5.0,
    ('J', 'D'): 5.0, ('J', 'E'): 6.0, ('J', 'F'): 8.0,
    # Lead = UPPER_HEAVY
    ('B', 'B'): 0.0, ('B', 'C'): 3.0, ('B', 'D'): 4.0,
    ('B', 'E'): 5.0, ('B', 'F'): 7.0,
    # Lead = LOWER_HEAVY
    ('C', 'C'): 0.0, ('C', 'D'): 3.0, ('C', 'E'): 4.0,
    ('C', 'F'): 6.0,
    # Lead = UPPER_MEDIUM
    ('D', 'E'): 0.0, ('D', 'F'): 5.0,
    # Lead = LOWER_MEDIUM
    ('E', 'F'): 4.0,
    # Lead = LIGHT — no wake separation
    ('F', 'F'): 0.0,
}


def classify(mtow_kg: float) -> WakeCategory:
    """Map maximum takeoff weight to RECAT-EU category.

    Simplified bin boundaries — real RECAT also considers
    wing characteristics. Good enough for CD purposes.
    """
    if mtow_kg > 560_000:
        return WakeCategory.SUPER
    elif mtow_kg > 300_000:
        return WakeCategory.UPPER_HEAVY
    elif mtow_kg > 100_000:
        return WakeCategory.LOWER_HEAVY
    elif mtow_kg > 50_000:
        return WakeCategory.UPPER_MEDIUM
    elif mtow_kg > 15_400:
        return WakeCategory.LOWER_MEDIUM
    else:
        return WakeCategory.LIGHT


def minimum_separation_nm(
    lead: WakeCategory, trail: WakeCategory,
) -> float:
    """RECAT-EU wake separation minimum between successive aircraft.

    Returns 0 if no wake minimum applies — then the caller
    should fall back to normal radar separation (2.5/3 NM).
    """
    key = (lead.value, trail.value)
    return _RECAT_DISTANCE_NM.get(key, 0.0)


def minimum_separation_by_type(
    lead_type_mtow: float, trail_type_mtow: float,
) -> tuple[float, WakeCategory, WakeCategory]:
    """Convenience wrapper: take MTOW directly, return NM + categories."""
    lead = classify(lead_type_mtow)
    trail = classify(trail_type_mtow)
    return minimum_separation_nm(lead, trail), lead, trail


# ── Rotorcraft / helicopter wake handling ────────────
#
# Helicopters are MORE dangerous than equivalent-weight
# fixed-wing in several regimes:
#
# 1. HOVER / HOVER-TAXI / SLOW FORWARD FLIGHT:
#    Downwash field extends 3 rotor diameters from hub.
#    Tangential surface wind 30+ kt for a Black Hawk.
#    FAA AC 90-23G: "avoid taxiing or flying within
#    3 rotor diameters of a helicopter hovering or in
#    a slow hover taxi". Small aircraft at same altitude
#    downwind of hover: maintain at least 500 ft separation.
#
# 2. FORWARD FLIGHT:
#    Trailing vortex pair analogous to wing-tip vortices.
#    SLOWER forward speed = STRONGER vortex (same lift,
#    less airflow = more circulation per ft). This is the
#    opposite of fixed-wing intuition.
#
# 3. TRANSITION (takeoff / landing):
#    Combined downwash + vortex. Most dangerous phase.
#    Multiple student-pilot fatalities following 23-30s
#    behind UH-60 in Cessna 120 / Cirrus SR20 / DA20.
#
# Decay time: up to 3 minutes vs ~2 minutes for fixed-wing
# at same weight. Rule-of-thumb: "wait a full minute" is
# often too short.

# Typical rotor diameters by type (meters)
_ROTOR_DIAMETER_M: dict[str, float] = {
    'R22': 7.67,
    'R44': 10.06,
    'R66': 10.06,
    'B06': 10.16,   # Bell JetRanger
    'B407': 10.67,  # Bell 407
    'B412': 14.02,
    'B429': 10.97,
    'B430': 12.80,
    'AS50': 10.70,  # AS350 Squirrel / H125
    'EC30': 10.70,
    'EC35': 10.20,
    'EC45': 11.00,
    'EC55': 10.69,
    'S76': 13.41,
    'S92': 17.17,
    'A109': 11.00,
    'A119': 10.83,
    'AW39': 13.80,  # AW139
    'AW69': 14.60,  # AW169
    'AW89': 15.00,  # AW189
    'AH1': 14.63,   # AH-1 Cobra
    'UH1': 14.63,   # UH-1 Huey
    'H60': 16.36,   # UH-60 Black Hawk
    'CH47': 18.29,  # Chinook (per rotor)
    'CH53': 24.08,
    'V22': 11.58,   # V-22 tiltrotor (per rotor)
}


def is_rotorcraft(typecode: str) -> bool:
    tc = (typecode or '').upper()
    return tc in _ROTOR_DIAMETER_M


def rotor_diameter_m(typecode: str) -> float:
    return _ROTOR_DIAMETER_M.get(
        (typecode or '').upper(), 12.0,
    )


def rotor_downwash_hazard_radius_m(typecode: str) -> float:
    """3 rotor diameters per FAA AC 90-23G."""
    return 3 * rotor_diameter_m(typecode)


def rotorcraft_wake_separation_nm(
    lead_typecode: str,
    lead_gs_kt: float,
    lead_mtow: float,
    trail_mtow: float,
) -> float:
    """Wake separation for rotorcraft generator.

    Rotorcraft wakes are phase-dependent:
    - Hover / slow (<40 kt): downwash dominates, use hazard radius
    - Forward flight: vortex pair, often STRONGER than fixed-wing
      at same weight due to low airspeed.
    """
    trail_cat = classify(trail_mtow)

    # Hover / hover-taxi: 3 rotor diameters → NM
    if lead_gs_kt < 40:
        return rotor_downwash_hazard_radius_m(lead_typecode) / 1852.0 * 1.5

    # Slow forward flight: vortex stronger than cruise
    # Apply one category tighter than fixed-wing rules would suggest
    if lead_gs_kt < 80:
        # Treat a medium helicopter as heavy
        lead_cat_boosted = classify(lead_mtow * 2.0)
        base = minimum_separation_nm(lead_cat_boosted, trail_cat)
        # And add a 25% safety margin for the slower-is-worse effect
        return base * 1.25

    # Faster forward flight: use standard wake rules
    lead_cat = classify(lead_mtow)
    return minimum_separation_nm(lead_cat, trail_cat)


def rotorcraft_wake_decay_s(lead_gs_kt: float) -> float:
    """Time for rotorcraft wake to decay below hazardous levels.

    Observed: up to 180 s for slow/hovering helicopters.
    Industry rule-of-thumb "wait a full minute" is often
    too short. NASA research suggests 2-3 min at low speeds.
    """
    if lead_gs_kt < 20:
        return 180.0   # hover / hover-taxi
    if lead_gs_kt < 60:
        return 150.0   # slow forward
    return 120.0       # fast forward (similar to fixed-wing)


def should_apply_wake_separation(
    lead: dict,
    trail: dict,
) -> bool:
    """Decide whether wake separation applies between two aircraft.

    Uses a blended approach:
    - Rotorcraft always apply (they're unusually hazardous)
    - Same-track geometry (±30 deg): yes
    - Terminal area (below 18000 ft, same airspace class): yes
    - En route passing traffic on different tracks: no
    """
    import math
    lat1 = lead.get('lat', 0)
    lon1 = lead.get('lon', 0)
    lat2 = trail.get('lat', 0)
    lon2 = trail.get('lon', 0)

    # Rotorcraft always apply — the downwash/vortex hazard
    # is severe and omnidirectional when hovering.
    # (Evaluate before the along-track filter — a hovering
    # helicopter has no meaningful "behind.")
    if is_rotorcraft(lead.get('typecode', '')):
        return True

    # Trail must be behind lead along lead's track
    trk1 = (lead.get('trk_deg', 0) or 0) * math.pi / 180
    dy = (lat2 - lat1) * 111_320
    dx = (lon2 - lon1) * 111_320 * math.cos(lat1 * math.pi / 180)
    along_track = dx * math.sin(trk1) + dy * math.cos(trk1)
    if along_track >= 0:
        return False  # trail is ahead of lead, not behind

    # Same-track geometry (±30 deg): apply
    trk2 = (trail.get('trk_deg', 0) or 0)
    trk_diff = abs((lead.get('trk_deg', 0) or 0) - trk2)
    if trk_diff > 180:
        trk_diff = 360 - trk_diff
    if trk_diff <= 30:
        return True

    # Terminal area (below FL180) with any same-airspace context
    alt1 = lead.get('alt_ft', 0) or 0
    alt2 = trail.get('alt_ft', 0) or 0
    if alt1 < 18000 and alt2 < 18000:
        cls1 = lead.get('airspace_class', 'G')
        cls2 = trail.get('airspace_class', 'G')
        if cls1 == cls2 and cls1 in ('B', 'C', 'D'):
            return True

    # Aggressive: Heavy / Super generate wake that sinks 400-800 ft
    # in 2 min and drifts with wind up to a few NM. Flag any Heavy+
    # lead with a trail aircraft in the drift zone (below + nearby),
    # regardless of track alignment.
    lead_mtow = lead.get('mtow_kg', 0) or 0
    if lead_mtow == 0:
        try:
            from cesium_app.performance.openap_adapter import (
                get_aircraft_props,
            )
            props = get_aircraft_props(lead.get('typecode', ''))
            lead_mtow = props.get('mtow_kg', 0)
        except Exception:
            pass

    if lead_mtow > 100_000:  # Heavy / Super (RECAT C/B/J)
        horiz_m = math.sqrt(dx * dx + dy * dy)
        if horiz_m < 5 * 1852:  # within 5 NM horizontally
            # Trail must be at or below lead (wake sinks)
            alt_delta_ft = alt1 - alt2
            if -200 <= alt_delta_ft <= 2500:
                return True

    return False


# ── TODO: dynamic wake vortex physics ────────────────
#
# The Burnham-Hallock model describes the tangential
# velocity in a wake vortex core:
#
#   v_theta(r) = (Gamma / 2*pi) * r / (r^2 + r_c^2)
#
# where:
#   Gamma = circulation = (M * g) / (rho * V * b * pi / 4)
#   M = aircraft mass
#   V = airspeed
#   b = wingspan
#   rho = air density
#   r_c = core radius (typically ~0.05 * b)
#
# Vortex pair descent rate in still air:
#   w_descent = Gamma / (2*pi * b_0)
#   where b_0 = pi/4 * wingspan (vortex pair spacing)
#
# Sarpkaya decay model provides circulation vs time
# with atmospheric turbulence parameter.
#
# This would let us:
#   - Render actual vortex regions behind heavy aircraft
#   - Compute if a following aircraft's flight path
#     intersects the wake envelope
#   - Support ATD-2 dynamic pair separation reduction
#     when wake has drifted out of the approach path
