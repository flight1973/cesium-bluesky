"""Conflict resolution algorithm suite.

Each algorithm implements the same interface:

    resolve(items: list[dict], conflicts: dict) -> dict[str, dict]

Returns {callsign: advisory} where advisory contains:
    dhdg_deg, dspd_kt, dvs_fpm: recommended changes
    new_hdg, new_spd_kt, new_vs_fpm: resolved values

Available methods:
    mvp     - Modified Voltage Potential (reactive, fast)
    ssd     - State-Space Diagram (velocity obstacles, optimal)
    eby     - Eby geometric (minimal deviation)
    swarm   - Layered MVP (dense traffic)
    vo      - Velocity Obstacle (cone-based)
    orca    - Optimal Reciprocal Collision Avoidance
    dubins  - Turn-radius-constrained paths
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

ResolveFunc = Callable[[list[dict], dict], dict[str, dict]]

_METHODS: dict[str, ResolveFunc] = {}
_current_method = 'mvp'


def register(name: str, func: ResolveFunc) -> None:
    _METHODS[name] = func


def available() -> list[str]:
    return sorted(_METHODS.keys())


def set_method(name: str) -> None:
    global _current_method
    if name not in _METHODS:
        raise ValueError(
            f"Unknown method '{name}'. Available: {available()}"
        )
    _current_method = name
    logger.info("Resolution method: %s", name)


def get_method() -> str:
    return _current_method


def resolve(
    items: list[dict],
    conflicts: dict,
    method: str | None = None,
) -> dict[str, dict]:
    m = method or _current_method
    func = _METHODS.get(m)
    if not func:
        return {}
    return func(items, conflicts)


# Auto-register all built-in methods on import.
def _autoregister():
    from cesium_app.surveillance.mvp_resolution import resolve_all as mvp
    register('mvp', mvp)

    try:
        from cesium_app.surveillance.resolution.ssd import resolve_all as ssd
        register('ssd', ssd)
    except ImportError:
        pass

    try:
        from cesium_app.surveillance.resolution.eby import resolve_all as eby
        register('eby', eby)
    except ImportError:
        pass

    try:
        from cesium_app.surveillance.resolution.swarm import resolve_all as swarm
        register('swarm', swarm)
    except ImportError:
        pass

    try:
        from cesium_app.surveillance.resolution.vo import resolve_all as vo
        register('vo', vo)
    except ImportError:
        pass

    try:
        from cesium_app.surveillance.resolution.orca import resolve_all as orca
        register('orca', orca)
    except ImportError:
        pass

    try:
        from cesium_app.surveillance.resolution.dubins_reso import resolve_all as dubins
        register('dubins', dubins)
    except ImportError:
        pass


_autoregister()
