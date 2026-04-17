"""REST endpoint for backend state flags.

Returns the state of various BlueSky toggles so the frontend
can keep its buttons in sync with what the sim is actually
doing — regardless of who changed the state (console, other
client, scenario file, etc.).
"""
from fastapi import APIRouter, Request

import bluesky as bs

router = APIRouter(prefix="/api/state", tags=["state"])


def _cd_state() -> tuple[str, list[str]]:
    """Current conflict detection method + available options.

    Returns a tuple of (selected_name, available_names).
    ``selected_name`` is ``'OFF'`` when no detection is
    active (base class is selected).  ``available_names``
    always includes ``'OFF'`` plus every registered
    subclass of ``ConflictDetection``.
    """
    from bluesky.traffic.asas.detection import (
        ConflictDetection,
    )
    methods = ConflictDetection.derived()
    names = [
        'OFF' if n == 'CONFLICTDETECTION' else n
        for n in methods
    ]
    sel_cls = ConflictDetection.selected()
    selected = (
        'OFF' if sel_cls is ConflictDetection
        else sel_cls.__name__.upper()
    )
    return selected, names


# RESO-providing plugins shipped with BlueSky.  Their
# init_plugin() registers a ConflictResolution subclass on
# load, adding to RESO's method list.  If more plugins ship
# later, extend this set.
_KNOWN_RESO_PLUGINS: frozenset[str] = frozenset({
    "EBY",
    "SSD",
})


def _reso_plugins_available() -> list[str]:
    """RESO plugin names known to us that aren't loaded."""
    try:
        from bluesky.core.plugin import Plugin
        loaded = {
            n.upper() for n in Plugin.loaded_plugins
        }
        return sorted(_KNOWN_RESO_PLUGINS - loaded)
    except (ImportError, AttributeError):
        return []


def _cr_state() -> tuple[str, list[str]]:
    """Current conflict resolution method + options."""
    from bluesky.traffic.asas.resolution import (
        ConflictResolution,
    )
    methods = ConflictResolution.derived()
    names = [
        'OFF' if n == 'CONFLICTRESOLUTION' else n
        for n in methods
    ]
    sel_cls = ConflictResolution.selected()
    selected = (
        'OFF' if sel_cls is ConflictResolution
        else sel_cls.__name__.upper()
    )
    return selected, names


@router.get("")
async def get_state(request: Request) -> dict:
    """Return current backend toggle state.

    Returns:
        Dict with keys:
            trails_active: Whether trail recording is on.
            area_active: Name of active deletion area or null.
            asas_method: Name of active CD method ('OFF' if
                disabled).
            asas_methods: Available CD method names (always
                includes 'OFF').
            reso_method: Name of active CR method ('OFF' if
                disabled).
            reso_methods: Available CR method names (always
                includes 'OFF').
    """
    trails_active = False
    try:
        trails_active = bool(bs.traf.trails.active)
    except AttributeError:
        pass

    area_active: str | None = None
    try:
        from bluesky.plugins.area import Area
        inst = Area._instance
        if inst and inst.active:
            area_active = inst.delarea or None
    except (ImportError, AttributeError):
        pass

    try:
        asas_method, asas_methods = _cd_state()
    except (ImportError, AttributeError):
        asas_method, asas_methods = "OFF", ["OFF"]

    try:
        reso_method, reso_methods = _cr_state()
    except (ImportError, AttributeError):
        reso_method, reso_methods = "OFF", ["OFF"]

    return {
        "trails_active": trails_active,
        "area_active": area_active,
        "asas_method": asas_method,
        "asas_methods": asas_methods,
        "reso_method": reso_method,
        "reso_methods": reso_methods,
        "reso_plugins_available": _reso_plugins_available(),
    }
