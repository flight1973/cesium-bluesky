"""BlueSky ASAS plugin adapter for cesium-bluesky resolution algorithms.

Wraps our standalone resolution algorithms (VO, ORCA, APF, Boids,
Social Force, Dubins, Eby, SSD) as BlueSky ConflictResolution plugins.
This lets BlueSky's ASAS framework use our algorithms for sim aircraft
with full autopilot integration.

Usage in BlueSky:
    RESO ORCA
    RESO APF
    RESO BOIDS
    RESO SOCIALFORCE
    RESO DUBINS_CR

Install by copying to bluesky/plugins/asas/ or adding to plugin path.
"""
import numpy as np
from bluesky.traffic.asas import ConflictResolution


def init_plugin():
    config = {
        'plugin_name': 'RESO_ADAPTER',
        'plugin_type': 'sim',
    }
    return config


class _StandaloneAdapter(ConflictResolution):
    """Base adapter: converts BlueSky arrays to our dict format,
    calls our standalone resolver, converts back."""

    def __init__(self):
        super().__init__()
        self._method_name = 'mvp'

    def _to_items(self, ownship):
        """Convert BlueSky ownship arrays to list[dict]."""
        items = []
        for i in range(ownship.ntraf):
            items.append({
                'icao24': ownship.id[i],
                'callsign': ownship.id[i],
                'lat': float(ownship.lat[i]),
                'lon': float(ownship.lon[i]),
                'alt_m': float(ownship.alt[i]),
                'alt_ft': float(ownship.alt[i] * 3.28084),
                'gs_kt': float(ownship.gs[i] / 0.514444),
                'trk_deg': float(ownship.hdg[i]),
                'vs_fpm': float(ownship.vs[i] / 0.00508),
                'on_ground': False,
                'airspace_class': 'G',
            })
        return items

    def _to_conflicts(self, conf):
        """Convert BlueSky conf object to our conflict dict."""
        confpairs = []
        for i in range(0, len(conf.confpairs), 2):
            if i + 1 < len(conf.confpairs):
                confpairs.append([conf.confpairs[i], conf.confpairs[i+1]])
        lospairs = []
        for i in range(0, len(conf.lospairs), 2):
            if i + 1 < len(conf.lospairs):
                lospairs.append([conf.lospairs[i], conf.lospairs[i+1]])

        tcpa = list(conf.tcpa) if hasattr(conf, 'tcpa') else []
        dcpa = list(conf.dcpa) if hasattr(conf, 'dcpa') else []

        return {
            'confpairs': confpairs,
            'lospairs': lospairs,
            'conf_tcpa': tcpa[::2] if tcpa else [],
            'conf_dcpa': [d/1852 for d in dcpa[::2]] if dcpa else [],
            'nconf_cur': len(confpairs),
            'nlos_cur': len(lospairs),
        }

    def resolve(self, conf, ownship, intruder):
        items = self._to_items(ownship)
        conflicts = self._to_conflicts(conf)

        from cesium_app.surveillance import resolution as reso
        advisories = reso.resolve(items, conflicts, method=self._method_name)

        newtrack = np.copy(ownship.hdg)
        newgs = np.copy(ownship.gs)
        newvs = np.copy(ownship.vs)
        newalt = ownship.selalt.copy() if hasattr(ownship, 'selalt') else ownship.alt.copy()

        for i in range(ownship.ntraf):
            acid = ownship.id[i]
            adv = advisories.get(acid)
            if adv:
                newtrack[i] = adv['new_hdg']
                newgs[i] = adv['new_spd_kt'] * 0.514444
                if adv.get('new_vs_fpm', 0) != 0:
                    newvs[i] = adv['new_vs_fpm'] * 0.00508

        # Clamp to performance limits
        newgs = np.maximum(ownship.perf.vmin, np.minimum(ownship.perf.vmax, newgs))

        return newtrack, newgs, newvs, newalt


class ORCA_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'orca'


class VO_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'vo'


class APF_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'apf'


class Boids_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'boids'


class SocialForce_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'social_force'


class Dubins_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'dubins'


class SSD_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'ssd'


class Eby_CR(_StandaloneAdapter):
    def __init__(self):
        super().__init__()
        self._method_name = 'eby'
