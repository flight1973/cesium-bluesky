"""Enroute airway storage.

One row per (airway, fix) pair; the airway's full
path is ``SELECT fix_id, lat, lon FROM airway_fix
WHERE airway_name=? ORDER BY seq``.

Looking up airways *containing* a given fix is the
graph-walk service's hot path (``find routes from
MLC toward EWR``), so ``idx_airway_fix_fix`` is
what makes the flight-path builder fast.
"""
from __future__ import annotations

import time
from collections.abc import Iterable

from cesium_app.store.db import connect
from cesium_app.store.procedures_cache import lookup_fix

SOURCE_AIRWAYS = "airways"


def replace_all(rows: Iterable[dict]) -> tuple[int, int]:
    """Drop + reload every airway row.

    Each input row is ``{airway_name, seq, fix_id,
    fix_region, route_type, min_fl_ft, max_fl_ft}``
    from :func:`cifp.parser.parse_airway_line`.
    Fix coordinates are resolved here via
    :func:`procedures_cache.lookup_fix` — navfix must
    be populated before this runs.

    Returns ``(n_airways, n_fixes)``.
    """
    now = time.time()
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM airway_fix")
            conn.execute("DELETE FROM airway")
            # Group by airway to dedupe header writes.
            header_written: set[str] = set()
            unresolved = 0
            n_rows = 0
            for row in rows:
                name = row["airway_name"]
                if name not in header_written:
                    conn.execute(
                        "INSERT INTO airway("
                        "name, route_type, fetched_at) "
                        "VALUES(?, ?, ?) "
                        "ON CONFLICT(name) DO UPDATE SET "
                        " route_type = excluded.route_type,"
                        " fetched_at = excluded.fetched_at",
                        (
                            name, row.get("route_type") or "",
                            now,
                        ),
                    )
                    header_written.add(name)
                fix = lookup_fix(
                    row["fix_id"],
                    region=row.get("fix_region") or None,
                )
                if fix is None:
                    unresolved += 1
                    continue
                conn.execute(
                    "INSERT INTO airway_fix("
                    "airway_name, seq, fix_id, fix_region,"
                    " lat, lon, min_fl, max_fl) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        name, row["seq"], row["fix_id"],
                        row.get("fix_region") or "",
                        fix["lat"], fix["lon"],
                        row.get("min_fl_ft"),
                        row.get("max_fl_ft"),
                    ),
                )
                n_rows += 1
            return len(header_written), n_rows
    finally:
        conn.close()


def airway_count() -> int:
    conn = connect()
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM airway"
        ).fetchone()[0])
    finally:
        conn.close()


def airway_fix_count() -> int:
    conn = connect()
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM airway_fix"
        ).fetchone()[0])
    finally:
        conn.close()


def get_airway(name: str) -> list[dict] | None:
    """Ordered fix list for one airway, or None."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT seq, fix_id, fix_region, lat, lon,"
            " min_fl, max_fl FROM airway_fix "
            "WHERE airway_name = ? ORDER BY seq",
            (name.upper(),),
        ).fetchall()
        if not rows:
            return None
        return [
            {
                "seq": r["seq"],
                "fix_id": r["fix_id"],
                "fix_region": r["fix_region"],
                "lat": r["lat"],
                "lon": r["lon"],
                "min_fl_ft": r["min_fl"],
                "max_fl_ft": r["max_fl"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def airways_through(fix_id: str) -> list[dict]:
    """Every airway that includes ``fix_id``.

    Returned rows carry the airway name, the fix's
    sequence position within it, and the fix's
    coords — enough for a graph walk to decide
    "which way does this airway continue past this
    fix?".
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT airway_name, seq, fix_id, lat, lon "
            "FROM airway_fix WHERE fix_id = ? "
            "ORDER BY airway_name, seq",
            (fix_id.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
