"""Unified conflict detection — three operational modes.

Mode A: ASAS-ONLY
  All aircraft injected into bs.traf. BlueSky's ASAS
  handles CD and resolution (MVP/SSD). Our standalone
  conflict_detect.py is not used. Best for sim-heavy
  work where you need resolution maneuvers.

Mode B: STANDALONE
  Our airspace-aware conflict_detect.py runs on the
  API response (live/replay). BlueSky's ASAS is not
  involved. Best for surveillance/monitoring where you
  want detection without resolution.

Mode C: HYBRID
  Both systems run. BlueSky ASAS handles sim aircraft
  (with resolution). Our CD handles observed aircraft
  (detection only). Results are merged and deduplicated.
  Cross-set conflicts (sim vs observed) are detected
  by injecting observed aircraft into bs.traf.

The mode is configurable per-request or globally.
"""
from __future__ import annotations

import logging
from typing import Literal

import bluesky as bs

from cesium_app.surveillance.conflict_detect import (
    detect_conflicts as standalone_detect,
)

logger = logging.getLogger(__name__)

CdMode = Literal['asas', 'standalone', 'hybrid']

_current_mode: CdMode = 'standalone'


def set_mode(mode: CdMode) -> None:
    global _current_mode
    _current_mode = mode
    logger.info("Conflict detection mode: %s", mode)


def get_mode() -> CdMode:
    return _current_mode


def get_asas_conflicts() -> dict:
    """Read current conflicts from BlueSky's ASAS."""
    try:
        cd = bs.traf.cd
        confpairs_flat = list(cd.confpairs)
        lospairs_flat = list(cd.lospairs)
        tcpa = list(cd.tcpa) if hasattr(cd, 'tcpa') else []
        dcpa = list(cd.dcpa) if hasattr(cd, 'dcpa') else []

        confpairs = []
        lospairs = []
        for i in range(0, len(confpairs_flat), 2):
            if i + 1 < len(confpairs_flat):
                confpairs.append([
                    confpairs_flat[i], confpairs_flat[i + 1],
                ])
        for i in range(0, len(lospairs_flat), 2):
            if i + 1 < len(lospairs_flat):
                lospairs.append([
                    lospairs_flat[i], lospairs_flat[i + 1],
                ])

        conf_tcpa = []
        conf_dcpa = []
        for i in range(len(confpairs)):
            idx = i * 2
            if idx < len(tcpa):
                conf_tcpa.append(round(tcpa[idx], 1))
            else:
                conf_tcpa.append(0)
            if idx < len(dcpa):
                conf_dcpa.append(
                    round(dcpa[idx] / 1852, 2))
            else:
                conf_dcpa.append(0)

        return {
            "confpairs": confpairs,
            "lospairs": lospairs,
            "conf_tcpa": conf_tcpa,
            "conf_dcpa": conf_dcpa,
            "nconf_cur": len(confpairs),
            "nlos_cur": len(lospairs),
            "source": "asas",
        }
    except Exception as exc:
        logger.debug("ASAS read failed: %s", exc)
        return _empty("asas")


def detect(
    items: list[dict],
    mode: CdMode | None = None,
) -> dict:
    """Run conflict detection in the specified mode.

    Args:
        items: Aircraft list from live/replay endpoint.
        mode: Override the global mode for this call.

    Returns:
        Unified conflict dict (confpairs, lospairs, etc.)
        with a 'source' field indicating which system(s)
        produced the results.
    """
    m = mode or _current_mode

    if m == 'asas':
        return get_asas_conflicts()

    if m == 'standalone':
        result = standalone_detect(items)
        result['source'] = 'standalone'
        return result

    # Hybrid: run standalone on observed, read ASAS
    # for sim, merge and deduplicate.
    standalone = standalone_detect(items)
    asas = get_asas_conflicts()
    return _merge(standalone, asas)


def _merge(a: dict, b: dict) -> dict:
    """Merge two conflict result sets, deduplicating."""
    seen = set()
    confpairs = []
    lospairs = []
    conf_tcpa = []
    conf_dcpa = []

    for src in [a, b]:
        for i, pair in enumerate(src.get('confpairs', [])):
            key = tuple(sorted(pair))
            if key in seen:
                continue
            seen.add(key)
            confpairs.append(pair)
            tcpa_list = src.get('conf_tcpa', [])
            dcpa_list = src.get('conf_dcpa', [])
            conf_tcpa.append(
                tcpa_list[i] if i < len(tcpa_list) else 0)
            conf_dcpa.append(
                dcpa_list[i] if i < len(dcpa_list) else 0)

    los_seen = set()
    for src in [a, b]:
        for pair in src.get('lospairs', []):
            key = tuple(sorted(pair))
            if key not in los_seen:
                los_seen.add(key)
                lospairs.append(pair)

    return {
        "confpairs": confpairs,
        "lospairs": lospairs,
        "conf_tcpa": conf_tcpa,
        "conf_dcpa": conf_dcpa,
        "nconf_cur": len(confpairs),
        "nlos_cur": len(lospairs),
        "source": "hybrid",
    }


def _empty(source: str) -> dict:
    return {
        "confpairs": [], "lospairs": [],
        "conf_tcpa": [], "conf_dcpa": [],
        "nconf_cur": 0, "nlos_cur": 0,
        "source": source,
    }
