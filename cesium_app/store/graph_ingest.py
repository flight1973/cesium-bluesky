"""Populate Neo4j from the SQLite source-of-truth.

Design: SQLite remains canonical.  This module walks
``navfix`` / ``procedure`` / ``airway`` tables and
rebuilds the Neo4j graph.  Calls to Neo4j use
``UNWIND $batch`` so we ship thousands of rows per
Cypher round-trip — the only way to stay snappy at
our scale (100k nodes + 100k edges).

Sequence:

1. :func:`graph_db.wipe` drops the old graph.
2. Nodes first, in batches: Airports → Fixes →
   Procedures → Airways.
3. Edges: ``Airport→Procedure``,
   ``Procedure→Fix`` endpoints,
   ``Airway→Fix`` via sequence,
   ``Fix↔Fix`` via ``NEIGHBOR_VIA`` — the hot path
   for route queries.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

from pyproj import Geod

from cesium_app.store import graph_db
from cesium_app.store.db import connect

logger = logging.getLogger(__name__)

_GEOD = Geod(ellps="WGS84")
_NM_TO_M = 1852.0

# Neo4j performs best with batches of a few thousand;
# large batches reduce round-trip overhead, but very
# large ones exceed the transaction memory budget.
_BATCH_SIZE = 2_000


def _batches(rows: list, size: int = _BATCH_SIZE) -> Iterator[list]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


# ─── Nodes ──────────────────────────────────────────

def _load_airports(sqlite_conn) -> int:
    """PA-type navfix rows → :Airport nodes."""
    rows = sqlite_conn.execute(
        "SELECT DISTINCT id, lat, lon FROM navfix "
        "WHERE fix_type = 'APT'"
    ).fetchall()
    records = [
        {"icao": r["id"], "lat": r["lat"], "lon": r["lon"]}
        for r in rows
    ]
    with graph_db.session() as s:
        for batch in _batches(records):
            s.run(
                "UNWIND $batch AS row "
                "MERGE (a:Airport {icao: row.icao}) "
                "SET a.lat = row.lat, a.lon = row.lon",
                batch=batch,
            )
    return len(records)


def _load_fixes(sqlite_conn) -> int:
    """All navfix rows → :Fix nodes.

    Airport rows get both an :Airport and a :Fix node
    so routing queries that cross airport↔airway
    boundaries still terminate cleanly on a single
    fix-keyed node.
    """
    rows = sqlite_conn.execute(
        "SELECT id, region, fix_type, lat, lon "
        "FROM navfix"
    ).fetchall()
    records = [
        {
            "id": r["id"],
            "region": r["region"] or "",
            "fix_type": r["fix_type"],
            "lat": r["lat"],
            "lon": r["lon"],
        }
        for r in rows
    ]
    with graph_db.session() as s:
        for batch in _batches(records):
            s.run(
                "UNWIND $batch AS row "
                "MERGE (f:Fix {id: row.id, region: row.region}) "
                "SET f.fix_type = row.fix_type,"
                "    f.lat = row.lat, f.lon = row.lon",
                batch=batch,
            )
    return len(records)


def _load_procedures(sqlite_conn) -> int:
    rows = sqlite_conn.execute(
        "SELECT id, airport, proc_type, name, transition "
        "FROM procedure"
    ).fetchall()
    records = [
        {
            "id": r["id"],
            "airport": r["airport"],
            "proc_type": r["proc_type"],
            "name": r["name"],
            "transition": r["transition"] or "",
        }
        for r in rows
    ]
    with graph_db.session() as s:
        for batch in _batches(records):
            s.run(
                "UNWIND $batch AS row "
                "MERGE (p:Procedure {id: row.id}) "
                "SET p.airport = row.airport,"
                "    p.proc_type = row.proc_type,"
                "    p.name = row.name,"
                "    p.transition = row.transition",
                batch=batch,
            )
    return len(records)


def _load_airways(sqlite_conn) -> int:
    rows = sqlite_conn.execute(
        "SELECT name, route_type FROM airway"
    ).fetchall()
    records = [
        {
            "name": r["name"],
            "route_type": r["route_type"] or "",
        }
        for r in rows
    ]
    with graph_db.session() as s:
        for batch in _batches(records):
            s.run(
                "UNWIND $batch AS row "
                "MERGE (w:Airway {name: row.name}) "
                "SET w.route_type = row.route_type",
                batch=batch,
            )
    return len(records)


# ─── Edges ──────────────────────────────────────────

def _link_airport_procedures(sqlite_conn) -> int:
    """Airport → procedure ownership edges.

    Edge type varies by proc_type so queries can
    filter at the edge level (``MATCH (a)-[:DEPARTS_VIA]->(p)``)
    rather than having to check a property.
    """
    rows = sqlite_conn.execute(
        "SELECT id, airport, proc_type FROM procedure"
    ).fetchall()
    by_type: dict[str, list[dict]] = {
        "SID": [], "STAR": [], "IAP": [],
    }
    for r in rows:
        t = r["proc_type"]
        if t in by_type:
            by_type[t].append({
                "icao": r["airport"],
                "proc_id": r["id"],
            })
    rel_for_type = {
        "SID": "DEPARTS_VIA",
        "STAR": "ARRIVES_VIA",
        "IAP": "APPROACHES_ON",
    }
    total = 0
    with graph_db.session() as s:
        for t, records in by_type.items():
            rel = rel_for_type[t]
            for batch in _batches(records):
                s.run(
                    f"UNWIND $batch AS row "
                    f"MATCH (a:Airport {{icao: row.icao}}) "
                    f"MATCH (p:Procedure {{id: row.proc_id}}) "
                    f"MERGE (a)-[:{rel}]->(p)",
                    batch=batch,
                )
                total += len(batch)
    return total


def _link_procedure_fixes(sqlite_conn) -> int:
    """Procedure → first-leg and last-leg fix endpoints.

    Gives route-builder queries direct handles to
    each procedure's entry and exit fixes without
    walking the whole leg list at query time.
    """
    rows = sqlite_conn.execute(
        "SELECT procedure_id, seq, fix_ident "
        "FROM procedure_leg "
        "WHERE fix_ident IS NOT NULL AND fix_ident != '' "
        "ORDER BY procedure_id, seq"
    ).fetchall()
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for r in rows:
        pid = r["procedure_id"]
        fid = r["fix_ident"]
        if pid not in first:
            first[pid] = fid
        last[pid] = fid
    start_records = [
        {"proc_id": p, "fix_id": f}
        for p, f in first.items()
    ]
    end_records = [
        {"proc_id": p, "fix_id": f}
        for p, f in last.items()
    ]
    with graph_db.session() as s:
        for batch in _batches(start_records):
            s.run(
                "UNWIND $batch AS row "
                "MATCH (p:Procedure {id: row.proc_id}) "
                "MATCH (f:Fix {id: row.fix_id}) "
                "MERGE (p)-[:STARTS_AT]->(f)",
                batch=batch,
            )
        for batch in _batches(end_records):
            s.run(
                "UNWIND $batch AS row "
                "MATCH (p:Procedure {id: row.proc_id}) "
                "MATCH (f:Fix {id: row.fix_id}) "
                "MERGE (p)-[:ENDS_AT]->(f)",
                batch=batch,
            )
    return len(start_records) + len(end_records)


def _link_airway_fixes(sqlite_conn) -> int:
    """Airway → fix membership + fix↔fix neighbors."""
    rows = sqlite_conn.execute(
        "SELECT airway_name, seq, fix_id, fix_region,"
        " lat, lon FROM airway_fix "
        "ORDER BY airway_name, seq"
    ).fetchall()
    includes_records: list[dict] = []
    neighbor_records: list[dict] = []
    prev: dict | None = None
    for r in rows:
        rec = dict(r)
        includes_records.append({
            "airway": rec["airway_name"],
            "fix_id": rec["fix_id"],
            "region": rec["fix_region"] or "",
            "seq": rec["seq"],
        })
        if (
            prev
            and prev["airway_name"] == rec["airway_name"]
        ):
            _, _, d_m = _GEOD.inv(
                prev["lon"], prev["lat"],
                rec["lon"], rec["lat"],
            )
            neighbor_records.append({
                "from_id": prev["fix_id"],
                "from_region": (prev["fix_region"] or ""),
                "to_id": rec["fix_id"],
                "to_region": (rec["fix_region"] or ""),
                "airway": rec["airway_name"],
                "dist_nm": d_m / _NM_TO_M,
            })
        prev = rec
    with graph_db.session() as s:
        for batch in _batches(includes_records):
            s.run(
                "UNWIND $batch AS row "
                "MATCH (w:Airway {name: row.airway}) "
                "MATCH (f:Fix {id: row.fix_id, "
                "              region: row.region}) "
                "MERGE (w)-[r:INCLUDES]->(f) "
                "SET r.seq = row.seq",
                batch=batch,
            )
        # Bidirectional: store one edge with a
        # direction property, query without direction
        # via ``MATCH (a)-[r:NEIGHBOR_VIA]-(b)``.  That
        # halves the edge count vs. storing both
        # directions explicitly.
        for batch in _batches(neighbor_records):
            s.run(
                "UNWIND $batch AS row "
                "MATCH (a:Fix {id: row.from_id, "
                "              region: row.from_region}) "
                "MATCH (b:Fix {id: row.to_id, "
                "              region: row.to_region}) "
                "MERGE (a)-[r:NEIGHBOR_VIA "
                "          {airway: row.airway}]->(b) "
                "SET r.dist_nm = row.dist_nm",
                batch=batch,
            )
    return len(includes_records) + len(neighbor_records)


def rebuild() -> dict[str, int]:
    """Full rebuild from SQLite.  Callers: ingest CLI."""
    # Drop the GDS graph projection so the next
    # route query re-projects against fresh data.
    try:
        from cesium_app.navdata.route_builder import (
            invalidate_projection,
        )
        invalidate_projection()
    except Exception:  # noqa: BLE001
        pass
    logger.info("Neo4j: wiping old graph")
    graph_db.ensure_schema()
    graph_db.wipe()
    stats: dict[str, int] = {}
    conn = connect()
    try:
        logger.info("Neo4j: loading airports")
        stats["airports"] = _load_airports(conn)
        logger.info(
            "Neo4j: loading fixes (all navfix rows)",
        )
        stats["fixes"] = _load_fixes(conn)
        logger.info("Neo4j: loading procedures")
        stats["procedures"] = _load_procedures(conn)
        logger.info("Neo4j: loading airways")
        stats["airways"] = _load_airways(conn)
        logger.info(
            "Neo4j: linking airports → procedures",
        )
        stats["apt_proc_rels"] = (
            _link_airport_procedures(conn)
        )
        logger.info(
            "Neo4j: linking procedures → fixes",
        )
        stats["proc_fix_rels"] = (
            _link_procedure_fixes(conn)
        )
        logger.info(
            "Neo4j: linking airways → fixes + neighbors",
        )
        stats["airway_fix_rels"] = (
            _link_airway_fixes(conn)
        )
    finally:
        conn.close()
    logger.info("Neo4j rebuild complete: %s", stats)
    return stats
