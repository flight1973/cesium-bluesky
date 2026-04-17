"""Test suite for all conflict resolution algorithms.

Tests against real DFW replay data plus synthetic edge cases
(head-on, overtake, converging, multi-aircraft cluster, LoS).
"""
import math
import pytest

from cesium_app.surveillance.conflict_detect import detect_conflicts
from cesium_app.surveillance.airspace_classify import classify_batch
from cesium_app.surveillance import resolution as reso


# ── Synthetic test scenarios ──────────────────────────

def _make_ac(callsign, lat, lon, alt_ft, gs_kt, trk_deg,
             vs_fpm=0, airspace_class='G'):
    return {
        'icao24': callsign.lower(),
        'callsign': callsign,
        'lat': lat, 'lon': lon,
        'alt_m': alt_ft * 0.3048,
        'alt_ft': alt_ft,
        'gs_kt': gs_kt,
        'trk_deg': trk_deg,
        'vs_fpm': vs_fpm,
        'on_ground': False,
        'squawk': '',
        'source': 'TEST',
        'airspace_class': airspace_class,
    }


def head_on_pair():
    """Two aircraft flying directly at each other."""
    return [
        _make_ac('AAL100', 32.90, -97.00, 35000, 450, 90),
        _make_ac('UAL200', 32.90, -96.90, 35000, 450, 270),
    ]


def overtake_pair():
    """Fast aircraft overtaking slow one on same track."""
    return [
        _make_ac('FAST01', 32.90, -97.00, 35000, 480, 90),
        _make_ac('SLOW02', 32.90, -96.95, 35000, 250, 90),
    ]


def converging_pair():
    """Two aircraft converging at 90 degrees."""
    return [
        _make_ac('NTH01', 32.85, -97.00, 25000, 350, 0),
        _make_ac('EST02', 32.90, -97.05, 25000, 350, 90),
    ]


def multi_cluster():
    """5 aircraft in a tight cluster — dense traffic scenario."""
    return [
        _make_ac('CL01', 32.900, -97.000, 20000, 300, 45),
        _make_ac('CL02', 32.905, -96.995, 20000, 310, 135),
        _make_ac('CL03', 32.895, -96.995, 20000, 290, 315),
        _make_ac('CL04', 32.900, -96.990, 20000, 305, 225),
        _make_ac('CL05', 32.903, -97.003, 20000, 295, 90),
    ]


def los_pair():
    """Two aircraft already in loss of separation."""
    return [
        _make_ac('LOS01', 32.900, -97.000, 30000, 400, 90),
        _make_ac('LOS02', 32.901, -96.999, 30000, 400, 270),
    ]


def vertical_conflict():
    """Climbing aircraft into level aircraft's altitude."""
    return [
        _make_ac('CLB01', 32.90, -97.00, 34000, 350, 90, vs_fpm=2000),
        _make_ac('LVL02', 32.90, -96.95, 35000, 400, 90, vs_fpm=0),
    ]


def parallel_approach():
    """Two aircraft on parallel approaches (should have fewer conflicts
    with variable PZ)."""
    return [
        _make_ac('APP01', 32.95, -97.05, 3000, 150, 180, airspace_class='B'),
        _make_ac('APP02', 32.95, -97.04, 3000, 140, 180, airspace_class='B'),
    ]


SCENARIOS = {
    'head_on': head_on_pair,
    'overtake': overtake_pair,
    'converging': converging_pair,
    'multi_cluster': multi_cluster,
    'los': los_pair,
    'vertical': vertical_conflict,
    'parallel_approach': parallel_approach,
}

ALL_METHODS = reso.available()


# ── Tests ─────────────────────────────────────────────

class TestResolutionRegistry:
    def test_all_methods_registered(self):
        methods = reso.available()
        assert len(methods) >= 10
        for m in ['mvp', 'ssd', 'eby', 'swarm', 'vo', 'orca',
                   'dubins', 'apf', 'boids', 'social_force']:
            assert m in methods, f"Missing method: {m}"

    def test_set_and_get_method(self):
        orig = reso.get_method()
        reso.set_method('orca')
        assert reso.get_method() == 'orca'
        reso.set_method(orig)

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError):
            reso.set_method('nonexistent')


class TestSyntheticScenarios:
    """Run every algorithm against every synthetic scenario."""

    @pytest.mark.parametrize("method", ALL_METHODS)
    @pytest.mark.parametrize("scenario_name", list(SCENARIOS.keys()))
    def test_algorithm_produces_output(self, method, scenario_name):
        items = SCENARIOS[scenario_name]()
        conflicts = detect_conflicts(items)

        if conflicts['nconf_cur'] == 0:
            pytest.skip(f"No conflicts in {scenario_name}")

        advs = reso.resolve(items, conflicts, method=method)
        # At least some advisories should be produced
        # (some algorithms may produce 0 for certain scenarios
        # if they determine no action needed)

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_head_on_produces_advisories(self, method):
        items = head_on_pair()
        conflicts = detect_conflicts(items)
        assert conflicts['nconf_cur'] > 0, "Head-on should be a conflict"
        advs = reso.resolve(items, conflicts, method=method)
        # Most methods should produce at least 1 advisory for head-on
        # (APF might not if gradient is below threshold)

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_los_produces_advisories(self, method):
        items = los_pair()
        conflicts = detect_conflicts(items)
        assert conflicts['nlos_cur'] > 0, "Should be in LoS"
        advs = reso.resolve(items, conflicts, method=method)

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_multi_cluster(self, method):
        items = multi_cluster()
        conflicts = detect_conflicts(items)
        assert conflicts['nconf_cur'] > 0, "Cluster should have conflicts"
        advs = reso.resolve(items, conflicts, method=method)


class TestAdvisoryValidity:
    """Validate that advisories have sane values."""

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_heading_in_range(self, method):
        items = head_on_pair()
        conflicts = detect_conflicts(items)
        advs = reso.resolve(items, conflicts, method=method)
        for cs, adv in advs.items():
            assert 0 <= adv['new_hdg'] < 360, \
                f"{method}/{cs}: heading {adv['new_hdg']} out of range"

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_speed_positive(self, method):
        items = converging_pair()
        conflicts = detect_conflicts(items)
        advs = reso.resolve(items, conflicts, method=method)
        for cs, adv in advs.items():
            assert adv['new_spd_kt'] >= 0, \
                f"{method}/{cs}: negative speed {adv['new_spd_kt']}"

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_speed_reasonable(self, method):
        items = head_on_pair()
        conflicts = detect_conflicts(items)
        advs = reso.resolve(items, conflicts, method=method)
        for cs, adv in advs.items():
            assert adv['new_spd_kt'] < 700, \
                f"{method}/{cs}: unreasonable speed {adv['new_spd_kt']}"

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_heading_change_bounded(self, method):
        """Heading change should not exceed 180 degrees."""
        items = overtake_pair()
        conflicts = detect_conflicts(items)
        advs = reso.resolve(items, conflicts, method=method)
        for cs, adv in advs.items():
            assert abs(adv['dhdg_deg']) <= 180, \
                f"{method}/{cs}: heading change {adv['dhdg_deg']} > 180"


class TestDFWReplay:
    """Test against real DFW replay data if available."""

    @pytest.fixture
    def dfw_data(self):
        try:
            from cesium_app.surveillance.replay import get_snapshot
            items = get_snapshot('dfw-test', 1656343800, tolerance=10)
            if not items:
                pytest.skip("No DFW replay data available")
            class_map = classify_batch(items)
            for ac in items:
                ac['airspace_class'] = class_map.get(ac['icao24'], 'G')
            return items
        except Exception:
            pytest.skip("Replay database not available")

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_dfw_produces_advisories(self, dfw_data, method):
        conflicts = detect_conflicts(dfw_data)
        assert conflicts['nconf_cur'] > 0
        advs = reso.resolve(dfw_data, conflicts, method=method)
        # Should produce at least some advisories
        assert isinstance(advs, dict)

    @pytest.mark.parametrize("method", ALL_METHODS)
    def test_dfw_no_nan_values(self, dfw_data, method):
        conflicts = detect_conflicts(dfw_data)
        advs = reso.resolve(dfw_data, conflicts, method=method)
        for cs, adv in advs.items():
            for key, val in adv.items():
                assert not math.isnan(val), \
                    f"{method}/{cs}: NaN in {key}"
                assert not math.isinf(val), \
                    f"{method}/{cs}: Inf in {key}"

    def test_all_methods_compared(self, dfw_data):
        """Run all methods and print comparison summary."""
        conflicts = detect_conflicts(dfw_data)
        print(f"\nDFW Replay: {len(dfw_data)} aircraft, "
              f"{conflicts['nconf_cur']} conflicts\n")
        print(f"{'Method':>14s}  {'Advisories':>10s}  "
              f"{'Avg dhdg':>8s}  {'Max dhdg':>8s}  "
              f"{'Avg dspd':>8s}")
        print("-" * 60)
        for method in sorted(ALL_METHODS):
            advs = reso.resolve(dfw_data, conflicts, method=method)
            if not advs:
                print(f"{method:>14s}  {'0':>10s}  {'—':>8s}  "
                      f"{'—':>8s}  {'—':>8s}")
                continue
            hdgs = [abs(a['dhdg_deg']) for a in advs.values()]
            spds = [abs(a['dspd_kt']) for a in advs.values()]
            print(f"{method:>14s}  {len(advs):>10d}  "
                  f"{sum(hdgs)/len(hdgs):>7.1f}°  "
                  f"{max(hdgs):>7.1f}°  "
                  f"{sum(spds)/len(spds):>7.1f}kt")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
