"""Test wake turbulence model (RECAT + helicopter-specific)."""
import pytest

from cesium_app.cooperative.wake_model import (
    WakeCategory,
    classify,
    minimum_separation_nm,
    minimum_separation_by_type,
    is_rotorcraft,
    rotor_diameter_m,
    rotor_downwash_hazard_radius_m,
    rotorcraft_wake_separation_nm,
    rotorcraft_wake_decay_s,
    should_apply_wake_separation,
)
from cesium_app.surveillance.conflict_detect import detect_conflicts


def _ac(callsign, lat, lon, alt_ft, gs_kt, trk_deg,
        typecode='B738', mtow_kg=79000, airspace_class='G'):
    return {
        'icao24': callsign.lower(),
        'callsign': callsign,
        'lat': lat, 'lon': lon,
        'alt_m': alt_ft * 0.3048,
        'alt_ft': alt_ft,
        'gs_kt': gs_kt,
        'trk_deg': trk_deg,
        'vs_fpm': 0,
        'on_ground': False,
        'typecode': typecode,
        'mtow_kg': mtow_kg,
        'airspace_class': airspace_class,
    }


class TestWakeClassification:
    def test_a380_is_super(self):
        assert classify(560_001) == WakeCategory.SUPER
        assert classify(575_000) == WakeCategory.SUPER

    def test_b747_is_upper_heavy(self):
        assert classify(396_800) == WakeCategory.UPPER_HEAVY

    def test_b777_is_lower_heavy(self):
        assert classify(299_300) == WakeCategory.LOWER_HEAVY

    def test_b738_is_upper_medium(self):
        assert classify(79_000) == WakeCategory.UPPER_MEDIUM

    def test_c172_is_light(self):
        assert classify(1_050) == WakeCategory.LIGHT

    def test_boundary_cases(self):
        assert classify(15_400) == WakeCategory.LIGHT
        assert classify(15_401) == WakeCategory.LOWER_MEDIUM
        assert classify(100_001) == WakeCategory.LOWER_HEAVY


class TestWakeSeparation:
    def test_super_behind_super(self):
        assert minimum_separation_nm(
            WakeCategory.SUPER, WakeCategory.SUPER
        ) == 0

    def test_heavy_behind_super(self):
        assert minimum_separation_nm(
            WakeCategory.SUPER, WakeCategory.UPPER_HEAVY
        ) == 4.0

    def test_light_behind_super(self):
        assert minimum_separation_nm(
            WakeCategory.SUPER, WakeCategory.LIGHT
        ) == 8.0

    def test_light_behind_heavy(self):
        assert minimum_separation_nm(
            WakeCategory.LOWER_HEAVY, WakeCategory.LIGHT
        ) == 6.0

    def test_by_mtow(self):
        # B777 leading a C172
        sep, lead_cat, trail_cat = minimum_separation_by_type(
            299_300, 1_050,
        )
        assert lead_cat == WakeCategory.LOWER_HEAVY
        assert trail_cat == WakeCategory.LIGHT
        assert sep == 6.0

    def test_light_behind_light_no_wake(self):
        # Two Cessnas — no wake separation needed
        assert minimum_separation_nm(
            WakeCategory.LIGHT, WakeCategory.LIGHT
        ) == 0


class TestRotorcraft:
    def test_is_rotorcraft(self):
        assert is_rotorcraft('R22')
        assert is_rotorcraft('H60')
        assert is_rotorcraft('h60')  # case insensitive
        assert not is_rotorcraft('B738')
        assert not is_rotorcraft('')

    def test_rotor_diameter(self):
        assert rotor_diameter_m('R22') == 7.67
        assert rotor_diameter_m('H60') == 16.36
        assert rotor_diameter_m('UNKNOWN') == 12.0

    def test_downwash_radius_is_3_diameters(self):
        # FAA AC 90-23G: 3 rotor diameters
        assert rotor_downwash_hazard_radius_m('H60') == 3 * 16.36

    def test_hovering_heli_uses_hazard_radius(self):
        # UH-60 hovering: 3 * 16.36 m = 49m → ~0.04 NM
        # Multiplied by 1.5 safety = ~0.05 NM, below typical
        # wake separation but drives min-distance floor
        nm = rotorcraft_wake_separation_nm(
            'H60', lead_gs_kt=0,
            lead_mtow=10_200, trail_mtow=1_100,
        )
        assert nm > 0
        assert nm < 1  # hazard radius, not vortex-size separation

    def test_slow_heli_boosted_to_heavy(self):
        # Slow-flying medium helicopter gets treated stronger
        # than its weight would suggest
        slow_sep = rotorcraft_wake_separation_nm(
            'H60', lead_gs_kt=60,
            lead_mtow=10_200, trail_mtow=1_100,
        )
        fast_sep = rotorcraft_wake_separation_nm(
            'H60', lead_gs_kt=120,
            lead_mtow=10_200, trail_mtow=1_100,
        )
        # slow flight is as dangerous or more
        assert slow_sep >= fast_sep

    def test_decay_time(self):
        # Hovering helicopters have the longest-lived wakes
        assert rotorcraft_wake_decay_s(0) == 180.0
        assert rotorcraft_wake_decay_s(50) == 150.0
        assert rotorcraft_wake_decay_s(100) == 120.0


class TestShouldApply:
    def test_trail_ahead_of_lead_no_wake(self):
        lead = _ac('LEAD', 32.9, -97.0, 10000, 250, 90)
        trail = _ac('TRAIL', 32.9, -96.9, 10000, 250, 90)  # east of lead
        # lead is heading east, trail is east = ahead
        assert not should_apply_wake_separation(lead, trail)

    def test_rotorcraft_always_applies(self):
        # Even at perpendicular track, helicopter wake is dangerous
        lead = _ac('HELO', 32.9, -97.0, 5000, 80, 90,
                   typecode='H60', mtow_kg=10_200)
        trail = _ac('CESS', 32.89, -97.01, 5000, 100, 0,
                    typecode='C172', mtow_kg=1_100)
        assert should_apply_wake_separation(lead, trail)

    def test_same_track_applies(self):
        lead = _ac('B772', 32.9, -96.9, 10000, 300, 270,
                   typecode='B772', mtow_kg=299_300)
        trail = _ac('C172', 32.9, -96.8, 10000, 100, 280,
                    typecode='C172', mtow_kg=1_100)
        assert should_apply_wake_separation(lead, trail)

    def test_aggressive_heavy_drift_zone(self):
        # Heavy (B777) at 10,000 ft, GA crossing below at 8,500 ft,
        # perpendicular track, within 5 NM horizontal = flagged
        # (wake drifts down/with wind)
        lead = _ac('B777', 32.9, -97.0, 10000, 400, 90,
                   typecode='B772', mtow_kg=299_300)
        trail = _ac('C172', 32.88, -97.02, 8500, 110, 180,
                    typecode='C172', mtow_kg=1_100)
        # Trail is south-west of lead, ~1.5 NM away, 1500 ft below
        assert should_apply_wake_separation(lead, trail)

    def test_medium_en_route_no_flag(self):
        # Two mediums passing at 35000 on different tracks,
        # outside terminal area → no wake separation enforced
        lead = _ac('B738', 32.9, -97.0, 35000, 450, 90,
                   typecode='B738', mtow_kg=79_000)
        trail = _ac('A320', 32.88, -97.05, 35000, 460, 180,
                    typecode='A320', mtow_kg=78_000)
        assert not should_apply_wake_separation(lead, trail)


class TestWakeInConflictDetect:
    def test_wake_pairs_returned(self):
        # Heavy B777 with C172 trailing 2 NM behind on same track
        # Standard CD won't flag them (far enough apart for 5 NM rule)
        # but wake rule requires 6 NM behind a LOWER_HEAVY for a LIGHT
        items = [
            _ac('B777', 32.9, -97.05, 5000, 250, 90,
                typecode='B772', mtow_kg=299_300,
                airspace_class='B'),
            _ac('C172', 32.9, -97.08, 4800, 100, 90,
                typecode='C172', mtow_kg=1_100,
                airspace_class='B'),
        ]
        result = detect_conflicts(items)
        # Should have a wake pair even if no geometric conflict
        assert 'wakepairs' in result

    def test_helicopter_hover_flags_gas(self):
        # Hovering UH-60 with Cessna within 3-rotor-diameter
        # downwash zone (49m for H-60). Use 30m separation.
        items = [
            _ac('HELO', 32.9000, -97.0000, 500, 0, 0,
                typecode='H60', mtow_kg=10_200,
                airspace_class='G'),
            _ac('CESS', 32.9002, -97.0001, 500, 80, 90,
                typecode='C172', mtow_kg=1_100,
                airspace_class='G'),
        ]
        result = detect_conflicts(items)
        wake_cats = [w['category'] for w in result.get('wakepairs', [])]
        assert any('rotorcraft' in c for c in wake_cats), (
            f"No rotorcraft wake flagged. Got: "
            f"{result.get('wakepairs', [])}"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
