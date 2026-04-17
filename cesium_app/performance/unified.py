"""Unified aircraft performance adapter.

Cascades through available performance data sources
in priority order:

  1. OpenAP (36 types + aliases — best for airline fleet)
  2. JSBSim (59 models — fills GA/military/historic gaps)
  3. Default fallback (B738 via OpenAP)

Each source provides what it can. The unified adapter
merges results and tracks which source contributed.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from cesium_app.performance import openap_adapter
from cesium_app.performance import jsbsim_adapter

logger = logging.getLogger(__name__)


@lru_cache(maxsize=256)
def lookup(icao_type: str) -> dict:
    """Get the best available performance data for a type.

    Returns a dict with source info and whatever specs
    are available from the highest-priority source.
    """
    key = icao_type.strip().upper()

    # Try OpenAP first (richest data: thrust/drag/fuel/emissions)
    if openap_adapter.is_supported(key):
        props = openap_adapter.get_aircraft_props(key)
        props["source"] = "openap"
        props["icao_type"] = key
        return props

    # Try JSBSim (has GA/military/historic types)
    jsb = jsbsim_adapter.get_aircraft_props(key)
    if jsb:
        jsb["icao_type"] = key
        return jsb

    # Fallback to OpenAP default (B738)
    props = openap_adapter.get_aircraft_props(key)
    props["source"] = "openap_fallback"
    props["icao_type"] = key
    props["fallback_type"] = "B738"
    return props


def coverage_report() -> dict:
    """Report on type coverage across all sources."""
    openap_types = set(openap_adapter.available_types())
    jsbsim_models = set(jsbsim_adapter.available_models()) if jsbsim_adapter.is_available() else set()

    openap_aliases = set()
    for alias_key in openap_adapter._resolve.__wrapped__.__code__.co_consts if hasattr(openap_adapter._resolve, '__wrapped__') else []:
        pass

    return {
        "openap_native": len(openap_types),
        "openap_types": sorted(openap_types),
        "jsbsim_models": len(jsbsim_models),
        "jsbsim_types": sorted(jsbsim_models),
        "jsbsim_available": jsbsim_adapter.is_available(),
        "total_unique": len(openap_types | jsbsim_models),
    }


def resolve_source(icao_type: str) -> str:
    """Which source would handle this type?"""
    key = icao_type.strip().upper()
    if openap_adapter.is_supported(key):
        return "openap"
    if jsbsim_adapter.resolve(key):
        return "jsbsim"
    return "fallback"
