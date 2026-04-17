"""FAA Preferred Routes storage + lookup.

The FAA publishes a machine-readable CSV of
preferred / TEC / NAR routes at
``https://www.fly.faa.gov/rmt/data_file/prefroutes_db.csv``.
Each row is one ATC-favored route between a (3-letter)
origin and destination, with a pre-assembled route
string that mixes procedure names, fix names, and
airway identifiers.

The route builder queries this table first — pilots
almost always file a preferred route if one exists
for the city pair, and ATC clears them near
universally over shortest-distance alternatives.
"""
from __future__ import annotations

import time
from collections.abc import Iterable

from cesium_app.store.db import connect

SOURCE_PREFERRED_ROUTES = "preferred_routes"


def replace_all(rows: Iterable[dict]) -> int:
    """Atomically replace every preferred-route row."""
    now = time.time()
    conn = connect()
    n = 0
    try:
        with conn:
            conn.execute("DELETE FROM preferred_route")
            for r in rows:
                conn.execute(
                    "INSERT INTO preferred_route("
                    "orig, dest, route_string, route_type,"
                    " area, altitude_ft, aircraft,"
                    " direction, seq, dep_center,"
                    " arr_center, fetched_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        r["orig"], r["dest"],
                        r["route_string"],
                        r.get("route_type"),
                        r.get("area"),
                        r.get("altitude_ft"),
                        r.get("aircraft"),
                        r.get("direction"),
                        r.get("seq"),
                        r.get("dep_center"),
                        r.get("arr_center"),
                        now,
                    ),
                )
                n += 1
        return n
    finally:
        conn.close()


def _icao_to_faa(icao: str) -> str:
    """US ICAO codes drop the K prefix in FAA tables."""
    icao = icao.upper()
    if len(icao) == 4 and icao[0] == "K":
        return icao[1:]
    return icao


def find_routes(
    dep_icao: str, arr_icao: str,
) -> list[dict]:
    """Lookup preferred routes for a city pair.

    Accepts ICAO (KDFW) or FAA 3-letter (DFW)
    inputs; normalizes to the 3-letter code used in
    the table.
    """
    dep = _icao_to_faa(dep_icao)
    arr = _icao_to_faa(arr_icao)
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT orig, dest, route_string, route_type,"
            " area, altitude_ft, aircraft, direction,"
            " seq, dep_center, arr_center "
            "FROM preferred_route "
            "WHERE orig = ? AND dest = ? "
            "ORDER BY seq",
            (dep, arr),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_rows() -> int:
    conn = connect()
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM preferred_route"
        ).fetchone()[0])
    finally:
        conn.close()
