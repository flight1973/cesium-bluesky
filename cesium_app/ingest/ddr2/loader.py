"""Load parsed DDR2 records into SQLite, respecting
the FAA-wins-where-it-has-data conflict rule.

Insert behavior per row:

- ``navfix``: skip if a row with the same
  ``(id, region, fix_type, airport)`` exists with
  ``source='FAA'``.  Otherwise insert tagged
  ``source='EUROCONTROL'``.
- ``airway``: same — FAA airways win their
  identifiers (TXK / V23 etc.).  EU airway names
  (UN862, UA34) usually don't collide so insert
  proceeds.
- ``airway_fix``: tagged with the airway's source.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable

from cesium_app.ingest.ddr2 import SOURCE_TAG
from cesium_app.store.db import connect

logger = logging.getLogger(__name__)


def load_navfixes(rows: Iterable[dict]) -> tuple[int, int]:
    """Insert DDR2 fixes; return (inserted, skipped)."""
    conn = connect()
    inserted = 0
    skipped = 0
    try:
        with conn:
            for r in rows:
                if not r.get("id") or r.get("region") is None:
                    skipped += 1
                    continue
                # FAA-wins check.
                exists = conn.execute(
                    "SELECT 1 FROM navfix WHERE "
                    "id = ? AND region = ? AND "
                    "fix_type = ? AND "
                    "(airport IS ?) LIMIT 1",
                    (
                        r["id"], r["region"],
                        r["fix_type"], r.get("airport"),
                    ),
                ).fetchone()
                if exists:
                    skipped += 1
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO navfix("
                    "id, region, fix_type, lat, lon,"
                    " airport, raw_json, source) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        r["id"], r["region"],
                        r["fix_type"], r["lat"], r["lon"],
                        r.get("airport"),
                        json.dumps(r.get("raw") or {}),
                        SOURCE_TAG,
                    ),
                )
                inserted += conn.total_changes - inserted
    finally:
        conn.close()
    return inserted, skipped


def load_airways(
    route_rows: Iterable[dict],
) -> tuple[int, int]:
    """Insert DDR2 routes + their fixes.

    Groups rows by ``airway_name``; inserts the
    airway header (skip if FAA already owns the
    name) then each fix in sequence.  Returns
    ``(n_airways, n_fixes)``.
    """
    now = time.time()
    grouped: dict[str, list[dict]] = {}
    for r in route_rows:
        grouped.setdefault(
            r.get("airway_name", ""), [],
        ).append(r)
    grouped.pop("", None)
    conn = connect()
    n_air = 0
    n_fix = 0
    try:
        with conn:
            for name, fixes in grouped.items():
                exists = conn.execute(
                    "SELECT source FROM airway "
                    "WHERE name = ?", (name,),
                ).fetchone()
                if exists and exists["source"] == "FAA":
                    # FAA already owns this airway —
                    # skip the whole route.
                    continue
                conn.execute(
                    "INSERT INTO airway("
                    "name, route_type, source, fetched_at) "
                    "VALUES(?, ?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET "
                    " route_type = excluded.route_type,"
                    " source = excluded.source,"
                    " fetched_at = excluded.fetched_at "
                    "WHERE airway.source != 'FAA'",
                    (
                        name,
                        fixes[0].get("route_type") or "",
                        SOURCE_TAG, now,
                    ),
                )
                n_air += 1
                # Replace this airway's fix list.
                conn.execute(
                    "DELETE FROM airway_fix "
                    "WHERE airway_name = ?",
                    (name,),
                )
                for f in fixes:
                    # Resolve fix coords from the
                    # navfix table — DDR2 routes
                    # don't carry per-fix lat/lon.
                    pos = conn.execute(
                        "SELECT lat, lon FROM navfix "
                        "WHERE id = ? AND region = ? "
                        "LIMIT 1",
                        (f["fix_id"], f["fix_region"]),
                    ).fetchone()
                    if not pos:
                        continue
                    conn.execute(
                        "INSERT INTO airway_fix("
                        "airway_name, seq, fix_id,"
                        " fix_region, lat, lon,"
                        " min_fl, max_fl, source) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            name, f["seq"], f["fix_id"],
                            f["fix_region"],
                            pos["lat"], pos["lon"],
                            f.get("min_fl_ft"),
                            f.get("max_fl_ft"),
                            SOURCE_TAG,
                        ),
                    )
                    n_fix += 1
    finally:
        conn.close()
    return n_air, n_fix
