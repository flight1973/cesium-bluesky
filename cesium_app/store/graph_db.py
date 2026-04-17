"""Neo4j connection + schema for the navdata graph.

The SQLite cache (``data/airspace.db``) remains the
source of truth for FAA data.  Neo4j is a *derived*
graph index refreshed at ingest time — same pattern
as ``procedure_geom`` but for graph-shaped queries.
This way we keep one canonical dataset and the
graph can be rebuilt from scratch any time.

Node labels:

* ``:Airport``  — ``icao``, ``lat``, ``lon``
* ``:Fix``      — ``id``, ``region``, ``lat``, ``lon``, ``fix_type``
* ``:Procedure`` — ``id``, ``proc_type``, ``name``,
                   ``transition``, ``airport``, ``n_legs``
* ``:Airway``   — ``name``, ``route_type``

Relationships:

* ``(a:Airport)-[:DEPARTS_VIA]->(s:Procedure {proc_type:'SID'})``
* ``(a:Airport)-[:ARRIVES_VIA]->(t:Procedure {proc_type:'STAR'})``
* ``(a:Airport)-[:APPROACHES_ON]->(i:Procedure {proc_type:'IAP'})``
* ``(p:Procedure)-[:STARTS_AT]->(f:Fix)``  — first fix on the procedure
* ``(p:Procedure)-[:ENDS_AT]->(f:Fix)``    — last fix on the procedure
* ``(w:Airway)-[:INCLUDES {seq}]->(f:Fix)``
* ``(f1:Fix)-[:NEIGHBOR_VIA {airway, dist_nm}]->(f2:Fix)``
  bidirectional, pre-computed from consecutive airway
  fixes — the hot path for route-finding queries.
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase

logger = logging.getLogger(__name__)


# Defaults match ``docker run`` setup in the README.
# Override via env for dockerised / production deployments.
_URI = os.environ.get("CESIUM_NEO4J_URI", "bolt://localhost:7687")
_USER = os.environ.get("CESIUM_NEO4J_USER", "neo4j")
_PASS = os.environ.get(
    "CESIUM_NEO4J_PASS", "bluesky-neo4j",
)

_driver: Driver | None = None
_lock = threading.Lock()


def driver() -> Driver:
    """Lazy Bolt driver; created once per process."""
    global _driver
    if _driver is not None:
        return _driver
    with _lock:
        if _driver is None:
            _driver = GraphDatabase.driver(
                _URI, auth=(_USER, _PASS),
            )
            _driver.verify_connectivity()
            logger.info("Neo4j connected at %s", _URI)
        return _driver


@contextmanager
def session():
    """Short-lived session context manager."""
    with driver().session() as s:
        yield s


def close() -> None:
    """Explicit shutdown — FastAPI calls this on lifespan end."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ─── Schema management ──────────────────────────────

_CONSTRAINTS = [
    # Unique keys double as implicit indexes.
    ("airport_icao_unique",
     "CREATE CONSTRAINT airport_icao_unique IF NOT EXISTS "
     "FOR (a:Airport) REQUIRE a.icao IS UNIQUE"),
    ("fix_key_unique",
     "CREATE CONSTRAINT fix_key_unique IF NOT EXISTS "
     "FOR (f:Fix) REQUIRE (f.id, f.region) IS UNIQUE"),
    ("procedure_id_unique",
     "CREATE CONSTRAINT procedure_id_unique IF NOT EXISTS "
     "FOR (p:Procedure) REQUIRE p.id IS UNIQUE"),
    ("airway_name_unique",
     "CREATE CONSTRAINT airway_name_unique IF NOT EXISTS "
     "FOR (w:Airway) REQUIRE w.name IS UNIQUE"),
]

_INDEXES = [
    ("fix_id_idx",
     "CREATE INDEX fix_id_idx IF NOT EXISTS "
     "FOR (f:Fix) ON (f.id)"),
    ("procedure_airport_type_idx",
     "CREATE INDEX procedure_airport_type_idx IF NOT EXISTS "
     "FOR (p:Procedure) ON (p.airport, p.proc_type)"),
]


def ensure_schema() -> None:
    """Idempotent constraint + index creation."""
    with session() as s:
        for _, q in _CONSTRAINTS + _INDEXES:
            s.run(q)


def wipe() -> None:
    """Drop every node + relationship.

    Used by the ingest pipeline before repopulating
    so the Neo4j graph mirrors the SQLite source
    exactly; no stale nodes leak across AIRAC cycles.
    """
    with session() as s:
        # Batched delete to avoid a single giant tx.
        s.run(
            "CALL apoc.periodic.iterate("
            "'MATCH (n) RETURN n', "
            "'DETACH DELETE n', "
            "{batchSize: 5000})"
        )


def node_counts() -> dict[str, int]:
    """Diagnostic: count by label."""
    labels = ["Airport", "Fix", "Procedure", "Airway"]
    out: dict[str, int] = {}
    with session() as s:
        for label in labels:
            r = s.run(
                f"MATCH (n:{label}) RETURN count(n) AS c",
            ).single()
            out[label] = r["c"] if r else 0
    return out


def rel_counts() -> dict[str, int]:
    with session() as s:
        r = s.run(
            "CALL db.relationshipTypes() YIELD relationshipType"
        )
        types = [row["relationshipType"] for row in r]
        out: dict[str, int] = {}
        for t in types:
            r2 = s.run(
                f"MATCH ()-[r:{t}]->() RETURN count(r) AS c",
            ).single()
            out[t] = r2["c"] if r2 else 0
        return out
