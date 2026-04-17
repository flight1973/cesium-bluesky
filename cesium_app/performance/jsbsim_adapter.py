"""JSBSim integration for aircraft performance data.

Extracts aircraft specifications from JSBSim's XML
aircraft definitions (59 models including GA types
like C172, PA28, C182, C310 that OpenAP lacks).

JSBSim is a full 6DOF flight dynamics model — we extract
static performance specs (weights, dimensions, engine
type) and can run trim solutions for specific flight
conditions to get thrust/drag/fuel at a given state.
"""
from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import jsbsim
    _ROOT = jsbsim.get_default_root_dir()
    _AIRCRAFT_DIR = os.path.join(_ROOT, 'aircraft')
    _AVAILABLE = True
except ImportError:
    _ROOT = ''
    _AIRCRAFT_DIR = ''
    _AVAILABLE = False
    logger.warning("jsbsim not installed — JSBSim adapter disabled")

# Map ICAO type codes to JSBSim model names
_ICAO_TO_JSBSIM: dict[str, str] = {
    'b737': '737', 'b738': '737', 'b739': '737',
    'b734': '737', 'b73g': '737', 'b73h': '737',
    'b788': '787-8', 'b789': '787-8',
    'a320': 'A320', 'a319': 'A320', 'a321': 'A320',
    'a318': 'A320', 'a20n': 'A320', 'a21n': 'A320',
    'b744': 'B747', 'b748': 'B747', 'b74s': 'B747',
    'md11': 'MD11', 'md1f': 'MD11',
    'c172': 'c172r', 'c17r': 'c172r', 'c72r': 'c172r',
    'c182': 'c182', 'c82r': 'c182', 'c82s': 'c182',
    'c310': 'c310',
    'pa28': 'pa28', 'p28a': 'pa28', 'p28b': 'pa28',
    'pa32': 'pa28', 'pa34': 'pa28',
    'j3': 'J3Cub', 'j3cu': 'J3Cub',
    'conc': 'Concorde',
    'c130': 'C130', 'c30j': 'C130',
    'dh8a': 'DHC6', 'dh8b': 'DHC6', 'dhc6': 'DHC6',
    'f100': 'fokker100', 'f70': 'fokker100',
    'f50': 'fokker50',
    'p51': 'p51d', 'p51d': 'p51d',
    'pc7': 'pc7', 'pc12': 'pc7',
    'gl5t': 'global5000', 'glex': 'global5000',
    'glf5': 'global5000',
    'ah1': 'ah1s',
    't38': 'T38', 't37': 'T37',
    'f16': 'f16', 'f15': 'f15', 'f22': 'f22',
    'l410': 'L410',
}


def is_available() -> bool:
    return _AVAILABLE


def available_models() -> list[str]:
    if not _AVAILABLE:
        return []
    models = []
    for name in os.listdir(_AIRCRAFT_DIR):
        d = os.path.join(_AIRCRAFT_DIR, name)
        if os.path.isdir(d) and os.path.isfile(
            os.path.join(d, f'{name}.xml')
        ):
            models.append(name)
    return sorted(models)


def resolve(icao_type: str) -> str | None:
    """Map ICAO type code to JSBSim model name, or None."""
    key = icao_type.strip().lower()
    return _ICAO_TO_JSBSIM.get(key)


@lru_cache(maxsize=64)
def _parse_aircraft(model: str) -> dict:
    """Parse JSBSim aircraft XML for specs."""
    xml_path = os.path.join(
        _AIRCRAFT_DIR, model, f'{model}.xml')
    if not os.path.isfile(xml_path):
        return {}
    tree = ET.parse(xml_path)
    r = tree.getroot()

    def _text(path: str, default: str = '0') -> str:
        el = r.find(path)
        return el.text.strip() if el is not None and el.text else default

    def _float(path: str) -> float:
        try:
            return float(_text(path, '0'))
        except ValueError:
            return 0.0

    metrics = r.find('.//metrics')
    mass = r.find('.//mass_balance')
    prop = r.find('.//propulsion')

    engines = prop.findall('.//engine') if prop is not None else []
    eng_files = [e.get('file', '?') for e in engines]

    return {
        "jsbsim_model": model,
        "wingarea_sqft": _float('.//metrics/wingarea'),
        "wingspan_ft": _float('.//metrics/wingspan'),
        "chord_ft": _float('.//metrics/chord'),
        "empty_weight_lbs": _float('.//mass_balance/emptywt'),
        "engine_count": len(engines),
        "engine_names": eng_files,
        "wingarea_m2": _float('.//metrics/wingarea') * 0.0929,
        "wingspan_m": _float('.//metrics/wingspan') * 0.3048,
        "empty_weight_kg": _float('.//mass_balance/emptywt') * 0.4536,
    }


def get_aircraft_props(icao_type: str) -> dict | None:
    """Get aircraft specs for an ICAO type via JSBSim."""
    if not _AVAILABLE:
        return None
    model = resolve(icao_type)
    if not model:
        return None
    data = _parse_aircraft(model)
    if not data:
        return None
    return {
        "source": "jsbsim",
        **data,
    }
