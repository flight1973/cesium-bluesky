"""Read/write API for cached CIFP procedures.

Sync (sqlite3-backed); wrap calls in
``asyncio.to_thread`` from async contexts.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterable

from cesium_app.store.db import connect

SOURCE_PROCEDURES = "procedures"


# ─── navfix lookup (used by leg compiler) ───────────

def replace_navfixes(items: Iterable[dict]) -> int:
    """Atomically replace the entire navfix table.

    Each ``item`` is ``{id, region, fix_type, lat,
    lon, airport, raw}`` from
    :func:`cifp.parser.parse_fix_line`.
    """
    conn = connect()
    n = 0
    try:
        with conn:
            conn.execute("DELETE FROM navfix")
            for fix in items:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO navfix("
                        "id, region, fix_type, lat, lon,"
                        " airport, raw_json) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (
                            fix["id"], fix["region"],
                            fix["fix_type"],
                            fix["lat"], fix["lon"],
                            fix.get("airport"),
                            json.dumps(fix),
                        ),
                    )
                    n += 1
                except Exception:  # noqa: BLE001
                    # Skip individual bad rows rather
                    # than failing the whole ingest.
                    continue
        return n
    finally:
        conn.close()


def lookup_fix(
    fix_id: str,
    *,
    region: str | None = None,
    airport: str | None = None,
    fix_type: str | None = None,
    near: tuple[float, float] | None = None,
) -> dict | None:
    """Resolve a fix to coords.

    Disambiguation order (most specific first):

    1. Exact airport-scoped match.
    2. Region match (with airport NULL → enroute).
    3. ``near``-biased: of all id matches, pick the
       one closest to ``near`` (procedure airport or
       previous leg endpoint).  Critical guard
       against picking a same-named fix on the wrong
       continent — without it, ``BIRMS`` (Texas) can
       resolve to ``BIRMS`` (Alaska) and create a
       3000 NM phantom leg.
    4. Last resort: any match by id (no bias).
    """
    conn = connect()
    try:
        if airport:
            row = conn.execute(
                "SELECT lat, lon, fix_type, raw_json "
                "FROM navfix WHERE id = ? AND airport = ? "
                "LIMIT 1",
                (fix_id, airport),
            ).fetchone()
            if row:
                return _hit(row)
        if region:
            sql = (
                "SELECT lat, lon, fix_type, raw_json "
                "FROM navfix WHERE id = ? AND region = ? "
                "AND airport IS NULL"
            )
            params: list = [fix_id, region]
            if fix_type:
                sql += " AND fix_type = ?"
                params.append(fix_type)
            row = conn.execute(
                sql + " LIMIT 1", params,
            ).fetchone()
            if row:
                return _hit(row)
        # Proximity-biased disambiguation.
        if near is not None:
            rows = conn.execute(
                "SELECT lat, lon, fix_type, raw_json "
                "FROM navfix WHERE id = ?",
                (fix_id,),
            ).fetchall()
            if rows:
                ref_lat, ref_lon = near
                # Squared planar distance is fine for
                # ranking — we're just picking the
                # closest of a small candidate set.
                rows = sorted(
                    rows,
                    key=lambda r: (
                        (r[0] - ref_lat) ** 2
                        + (r[1] - ref_lon) ** 2
                    ),
                )
                return _hit(rows[0])
        row = conn.execute(
            "SELECT lat, lon, fix_type, raw_json "
            "FROM navfix WHERE id = ? LIMIT 1",
            (fix_id,),
        ).fetchone()
        return _hit(row) if row else None
    finally:
        conn.close()


def airport_position(airport: str) -> tuple[float, float] | None:
    """Lat/lon of the named airport, if known.

    Used by the leg compiler as the proximity
    reference for ambiguous fix lookups.
    """
    conn = connect()
    try:
        # Airport reference points are stored as
        # navfix rows with airport = id (terminal
        # waypoints scoped to themselves).  Fallback:
        # take any terminal fix at that airport.
        row = conn.execute(
            "SELECT lat, lon FROM navfix "
            "WHERE airport = ? LIMIT 1",
            (airport.upper(),),
        ).fetchone()
        return (row[0], row[1]) if row else None
    finally:
        conn.close()


def _hit(row) -> dict:
    return {
        "lat": row[0], "lon": row[1],
        "fix_type": row[2], "raw": row[3],
    }


def navfix_count() -> int:
    conn = connect()
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM navfix"
            ).fetchone()[0]
        )
    finally:
        conn.close()


# ─── Compiled procedure geometry ────────────────────

def replace_geom(items: Iterable[dict]) -> int:
    """Replace all rows in procedure_geom + r-tree.

    Each item: ``{procedure_id, polyline, fixes,
    bbox: (min_lat, max_lat, min_lon, max_lon)}``.
    """
    conn = connect()
    n = 0
    try:
        with conn:
            # Drop r-tree rows first; SQLite r-tree
            # virtual tables don't cascade.
            conn.execute(
                "DELETE FROM procedure_geom_rtree"
            )
            conn.execute("DELETE FROM procedure_geom")
            for item in items:
                bbox = item.get("bbox")
                if bbox is None:
                    continue
                cur = conn.execute(
                    "INSERT INTO procedure_geom("
                    "procedure_id, polyline_json,"
                    " fixes_json,"
                    " min_lat, max_lat,"
                    " min_lon, max_lon) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["procedure_id"],
                        json.dumps(item["polyline"]),
                        json.dumps(item.get("fixes", [])),
                        bbox[0], bbox[1], bbox[2], bbox[3],
                    ),
                )
                conn.execute(
                    "INSERT INTO procedure_geom_rtree("
                    "id, min_lat, max_lat,"
                    " min_lon, max_lon) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (
                        cur.lastrowid,
                        bbox[0], bbox[1], bbox[2], bbox[3],
                    ),
                )
                n += 1
        return n
    finally:
        conn.close()


def get_geom(procedure_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT polyline_json, fixes_json "
            "FROM procedure_geom WHERE procedure_id = ?",
            (procedure_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "polyline": json.loads(row[0]),
            "fixes": json.loads(row[1]),
        }
    finally:
        conn.close()


def geom_count() -> int:
    conn = connect()
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM procedure_geom"
            ).fetchone()[0]
        )
    finally:
        conn.close()


def replace_all(items: Iterable[dict]) -> tuple[int, int]:
    """Replace every procedure + leg row from ``items``.

    Each ``item`` is a ``{id, airport, proc_type,
    name, transition, legs: [...]}`` dict produced by
    :func:`cifp.parser.group_procedures`.

    Returns ``(n_procedures, n_legs)``.
    """
    now = time.time()
    conn = connect()
    n_proc = 0
    n_legs = 0
    try:
        with conn:
            conn.execute("DELETE FROM procedure_leg")
            conn.execute("DELETE FROM procedure")
            for proc in items:
                conn.execute(
                    "INSERT INTO procedure("
                    "id, airport, proc_type, name,"
                    " transition, raw_json,"
                    " source, fetched_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        proc["id"], proc["airport"],
                        proc["proc_type"], proc["name"],
                        proc["transition"],
                        json.dumps(proc),
                        SOURCE_PROCEDURES, now,
                    ),
                )
                n_proc += 1
                for leg in proc["legs"]:
                    conn.execute(
                        "INSERT INTO procedure_leg("
                        "procedure_id, seq, leg_type,"
                        " fix_ident, raw_json) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (
                            proc["id"],
                            leg.get("seq") or 0,
                            leg.get("leg_type") or "",
                            leg.get("fix_ident") or None,
                            json.dumps(leg),
                        ),
                    )
                    n_legs += 1
        return n_proc, n_legs
    finally:
        conn.close()


def list_for_airport(
    airport: str,
    *,
    proc_type: str | None = None,
) -> list[dict]:
    """All procedures (with legs) for one airport."""
    conn = connect()
    try:
        sql = (
            "SELECT raw_json FROM procedure "
            "WHERE airport = ?"
        )
        params: list = [airport.upper()]
        if proc_type:
            sql += " AND proc_type = ?"
            params.append(proc_type.upper())
        sql += " ORDER BY proc_type, name, transition"
        return [
            json.loads(row[0])
            for row in conn.execute(sql, params)
        ]
    finally:
        conn.close()


def get_procedure(procedure_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT raw_json FROM procedure WHERE id = ?",
            (procedure_id,),
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def airport_count() -> int:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT airport) FROM procedure"
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()
