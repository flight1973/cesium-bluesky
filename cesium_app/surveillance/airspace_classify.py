"""Per-aircraft airspace classification.

3D point-in-polygon test: determines which class
airspace (B, C, D, E, or G) each aircraft is in by
checking lat/lon against cached airspace polygons AND
verifying the aircraft's altitude falls within the
shelf's floor/ceiling.

Class B and C both have wedding-cake tiered shelves —
an aircraft at 4000 ft MSL may be inside the outer
ring of Class B but above the inner shelf.

Precedence: B > C > D > E > G (most restrictive wins
when an aircraft is inside overlapping volumes).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from functools import lru_cache

from cesium_app.store.db import connect

logger = logging.getLogger(__name__)

_CLASS_PRIORITY = {'B': 0, 'C': 1, 'D': 2, 'E': 3}


def _point_in_ring(
    lat: float, lon: float, ring: list[list[float]],
) -> bool:
    """Ray-casting point-in-polygon for a single ring.

    Ring format: [[lat, lon], [lat, lon], ...]
    """
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = ring[i][0], ring[i][1]
        yj, xj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def classify_aircraft(
    lat: float, lon: float, alt_ft: float,
) -> str:
    """Determine the airspace class for a single aircraft.

    Returns 'B', 'C', 'D', 'E', or 'G'.
    """
    conn = connect()
    conn.row_factory = sqlite3.Row

    # R-tree spatial query for candidate polygons
    candidates = conn.execute("""
        SELECT a.subtype, a.bottom_ft, a.top_ft, a.props_json
        FROM airspace a
        JOIN airspace_rtree r ON a.rowid = r.id
        WHERE a.type = 'CLASS'
          AND r.min_lat <= ? AND r.max_lat >= ?
          AND r.min_lon <= ? AND r.max_lon >= ?
    """, (lat, lat, lon, lon)).fetchall()
    conn.close()

    best_class = 'G'
    best_priority = 999

    for row in candidates:
        subtype = row['subtype']
        if subtype not in _CLASS_PRIORITY:
            continue
        priority = _CLASS_PRIORITY[subtype]
        if priority >= best_priority:
            continue

        bottom = row['bottom_ft'] or 0
        top = row['top_ft'] or 99999
        if alt_ft < bottom or alt_ft > top:
            continue

        props = json.loads(row['props_json'])
        rings = props.get('rings', [])
        if not rings:
            continue

        if _point_in_ring(lat, lon, rings[0]):
            best_class = subtype
            best_priority = priority

    return best_class


def classify_batch(
    aircraft: list[dict],
) -> dict[str, str]:
    """Classify multiple aircraft. Returns {icao24: class}.

    Each aircraft dict must have lat, lon, alt_ft (or alt_m).
    """
    conn = connect()
    conn.row_factory = sqlite3.Row

    all_candidates = conn.execute("""
        SELECT a.rowid, a.subtype, a.bottom_ft, a.top_ft,
               a.props_json,
               r.min_lat, r.max_lat, r.min_lon, r.max_lon
        FROM airspace a
        JOIN airspace_rtree r ON a.rowid = r.id
        WHERE a.type = 'CLASS'
          AND a.subtype IN ('B', 'C', 'D', 'E')
    """).fetchall()
    conn.close()

    parsed = []
    for row in all_candidates:
        props = json.loads(row['props_json'])
        rings = props.get('rings', [])
        if not rings:
            continue
        parsed.append({
            'subtype': row['subtype'],
            'bottom': row['bottom_ft'] or 0,
            'top': row['top_ft'] or 99999,
            'ring': rings[0],
            'min_lat': row['min_lat'],
            'max_lat': row['max_lat'],
            'min_lon': row['min_lon'],
            'max_lon': row['max_lon'],
        })

    result: dict[str, str] = {}
    for ac in aircraft:
        icao = ac.get('icao24', '')
        lat = ac.get('lat')
        lon = ac.get('lon')
        alt_ft = ac.get('alt_ft')
        if alt_ft is None:
            alt_m = ac.get('alt_m', 0) or 0
            alt_ft = alt_m * 3.28084

        if lat is None or lon is None:
            result[icao] = 'G'
            continue

        best = 'G'
        best_pri = 999

        for cand in parsed:
            pri = _CLASS_PRIORITY.get(cand['subtype'], 999)
            if pri >= best_pri:
                continue
            if lat < cand['min_lat'] or lat > cand['max_lat']:
                continue
            if lon < cand['min_lon'] or lon > cand['max_lon']:
                continue
            if alt_ft < cand['bottom'] or alt_ft > cand['top']:
                continue
            if _point_in_ring(lat, lon, cand['ring']):
                best = cand['subtype']
                best_pri = pri

        result[icao] = best

    return result
