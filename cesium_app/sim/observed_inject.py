"""Inject observed (live/replay) aircraft into bs.traf.

This makes BlueSky's ASAS (MVP/SSD) see live and replay
aircraft alongside simulated ones, enabling conflict
detection AND resolution across the full traffic picture.

Observed aircraft are marked with a per-aircraft flag
so ASAS detects conflicts involving them but only
commands sim aircraft to maneuver — live aircraft are
treated as immovable truth (right-of-way).

Usage from the sim bridge:
    injector = ObservedInjector()
    injector.update(items)   # called periodically
    injector.clear()         # remove all injected aircraft
"""
from __future__ import annotations

import logging
import time

import bluesky as bs

logger = logging.getLogger(__name__)

_INJECT_PREFIX = "OBS_"
_STALE_TIMEOUT_S = 60


class ObservedInjector:
    """Manages lifecycle of observed aircraft in bs.traf."""

    def __init__(self):
        self._active: dict[str, float] = {}
        self._ensure_observed_flag()

    def _ensure_observed_flag(self):
        """Add is_observed array to bs.traf if missing."""
        if not hasattr(bs.traf, 'is_observed'):
            bs.traf.is_observed = []

    def _sync_flag_size(self):
        """Keep is_observed array in sync with traf size."""
        n = bs.traf.ntraf
        obs = bs.traf.is_observed
        if len(obs) < n:
            bs.traf.is_observed = obs + [False] * (n - len(obs))
        elif len(obs) > n:
            bs.traf.is_observed = obs[:n]

    def _acid(self, item: dict) -> str:
        cs = (item.get('callsign') or '').strip()
        if cs:
            return f"{_INJECT_PREFIX}{cs}"
        return f"{_INJECT_PREFIX}{item['icao24'].upper()}"

    def update(self, items: list[dict]) -> int:
        """Update bs.traf with observed aircraft positions.

        Creates new aircraft, moves existing ones, removes
        stale ones. Returns count of active injected aircraft.
        """
        self._ensure_observed_flag()
        now = time.time()
        seen = set()

        for item in items:
            if item.get('on_ground', False):
                continue
            lat = item.get('lat')
            lon = item.get('lon')
            if lat is None or lon is None:
                continue

            acid = self._acid(item)
            seen.add(acid)
            self._active[acid] = now

            alt_ft = item.get('alt_ft', 0) or 0
            gs_kt = item.get('gs_kt', 0) or 0
            trk = item.get('trk_deg', 0) or 0
            vs_fpm = item.get('vs_fpm', 0) or 0
            typecode = item.get('typecode', 'B738') or 'B738'

            idx = bs.traf.id2idx(acid)
            if idx < 0:
                bs.stack.stack(
                    f"CRE {acid} {typecode} "
                    f"{lat:.5f} {lon:.5f} "
                    f"{trk:.0f} {alt_ft:.0f} {gs_kt:.0f}"
                )
                self._sync_flag_size()
                new_idx = bs.traf.id2idx(acid)
                if new_idx >= 0 and new_idx < len(bs.traf.is_observed):
                    bs.traf.is_observed[new_idx] = True
            else:
                bs.traf.move(
                    idx, lat, lon,
                    alt=alt_ft * 0.3048,
                    hdg=trk,
                    casmach=gs_kt * 0.514444,
                    vspd=vs_fpm * 0.00508,
                )

        # Remove stale aircraft.
        stale = [
            acid for acid, t in self._active.items()
            if acid not in seen and (now - t) > _STALE_TIMEOUT_S
        ]
        for acid in stale:
            idx = bs.traf.id2idx(acid)
            if idx >= 0:
                bs.stack.stack(f"DEL {acid}")
            del self._active[acid]

        self._sync_flag_size()
        return len(self._active)

    def clear(self):
        """Remove all injected observed aircraft."""
        for acid in list(self._active.keys()):
            idx = bs.traf.id2idx(acid)
            if idx >= 0:
                bs.stack.stack(f"DEL {acid}")
        self._active.clear()

    @property
    def count(self) -> int:
        return len(self._active)

    @property
    def active_acids(self) -> list[str]:
        return list(self._active.keys())
