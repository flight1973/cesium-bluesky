"""Flight-path builder — GDS-backed.

The Graph Data Science library provides efficient
many-to-many shortest-path (Yens / Dijkstra source-
target) that dramatically outperforms calling APOC
Dijkstra once per SID-STAR pair.  We project the
``NEIGHBOR_VIA`` subgraph once, then run
``gds.shortestPath.dijkstra`` from each unique SID
exit fix to each unique STAR entry fix.

Chain semantics (matches real pilot filing):

    SID.transition → airway hops → transition.STAR

where ``SID.transition`` is a procedure whose
transition is an enroute fix (``MLC``), not a runway
(``RW17R``).  See ``project_pilot_realistic_routing.md``
for the real-pilot-vs-ours diff.
"""
from __future__ import annotations

import logging

from cesium_app.store import graph_db, preferred_routes_cache

logger = logging.getLogger(__name__)


# Graph-projection name reused across calls.
_GRAPH_NAME = "airway_graph"

_MAX_AIRWAY_HOPS = 80


def _ensure_projection(s) -> None:
    """Idempotently project the ``NEIGHBOR_VIA``
    subgraph.  GDS projections live for the session
    server-lifetime; this ``.exists`` check avoids
    re-projecting for every request."""
    exists = s.run(
        "CALL gds.graph.exists($name) "
        "YIELD exists RETURN exists",
        name=_GRAPH_NAME,
    ).single()["exists"]
    if exists:
        return
    s.run(
        "CALL gds.graph.project("
        "  $name,"
        "  'Fix',"
        "  {NEIGHBOR_VIA: {"
        "      orientation: 'UNDIRECTED',"
        "      properties: ['dist_nm']"
        "  }}"
        ") YIELD graphName, nodeCount, relationshipCount",
        name=_GRAPH_NAME,
    )
    logger.info("Projected GDS graph %s", _GRAPH_NAME)


def invalidate_projection() -> None:
    """Drop the in-memory graph projection — call
    after a graph-ingest rebuild so the next route
    query re-projects against fresh data."""
    with graph_db.session() as s:
        exists = s.run(
            "CALL gds.graph.exists($name) YIELD exists",
            name=_GRAPH_NAME,
        ).single()["exists"]
        if exists:
            s.run(
                "CALL gds.graph.drop($name)",
                name=_GRAPH_NAME,
            )
            logger.info(
                "Dropped GDS projection %s", _GRAPH_NAME,
            )


_RUNWAY_PIECES_CYPHER = """
// For a given (dep, arr, sid_name, star_name, dep_rwy,
// arr_rwy), return the runway-transition variants
// of the SID / STAR and candidate IAPs at arr_rwy.
// Also matches CIFP 'B' variants (RW17B = both 17L
// and 17R) when the user specifies a parallel
// runway — those cover both sides in one record.
MATCH (dep:Airport {icao: $dep})
OPTIONAL MATCH (dep)-[:DEPARTS_VIA]->(sid_rwy:Procedure)
  WHERE sid_rwy.name = $sid_name
    AND $dep_rwy <> ''
    AND (
        sid_rwy.transition = 'RW' + $dep_rwy
     OR sid_rwy.transition = 'RW' + substring($dep_rwy, 0, 2) + 'B'
    )

MATCH (arr:Airport {icao: $arr})
OPTIONAL MATCH (arr)-[:ARRIVES_VIA]->(star_rwy:Procedure)
  WHERE star_rwy.name = $star_name
    AND $arr_rwy <> ''
    AND (
        star_rwy.transition = 'RW' + $arr_rwy
     OR star_rwy.transition = 'RW' + substring($arr_rwy, 0, 2) + 'B'
    )
OPTIONAL MATCH (arr)-[:APPROACHES_ON]->(iap:Procedure)
  WHERE $arr_rwy <> ''
    AND iap.name CONTAINS $arr_rwy

RETURN
    sid_rwy.id  AS sid_runway_id,
    star_rwy.id AS star_runway_id,
    collect(DISTINCT iap.id) AS iap_ids
"""


_BUILD_ROUTES_CYPHER = """
// SID + STAR candidate lists with their fix endpoints.
MATCH (dep:Airport {icao: $dep})
  -[:DEPARTS_VIA]->(sid:Procedure)-[:ENDS_AT]->(exit_fix:Fix)
WHERE NOT sid.transition STARTS WITH 'RW'
  AND sid.transition <> ''
WITH dep, collect(DISTINCT exit_fix) AS exit_fixes,
     collect(DISTINCT {sid_id: sid.id, fix_id: exit_fix.id}) AS sid_pairs

MATCH (arr:Airport {icao: $arr})
  -[:ARRIVES_VIA]->(star:Procedure)-[:STARTS_AT]->(entry_fix:Fix)
WHERE NOT star.transition STARTS WITH 'RW'
  AND star.transition <> ''
WITH dep, exit_fixes, sid_pairs,
     arr, collect(DISTINCT entry_fix) AS entry_fixes,
     collect(DISTINCT {star_id: star.id, fix_id: entry_fix.id}) AS star_pairs

// GDS single-source Dijkstra, called per unique SID
// exit.  ``targetNodes`` holds all STAR entries so
// one invocation covers an exit's full fan-out.
// Total calls: #unique SID exits (~50 for KDFW)
// instead of SID × STAR pair-wise (~3000).
UNWIND exit_fixes AS exit_fix
CALL gds.shortestPath.dijkstra.stream(
    $graph_name,
    {
        sourceNode: exit_fix,
        targetNodes: entry_fixes,
        relationshipWeightProperty: 'dist_nm'
    }
) YIELD targetNode, totalCost, nodeIds
WHERE size(nodeIds) > 1
  AND size(nodeIds) <= $max_hops + 1
WITH dep, arr, sid_pairs, star_pairs,
     exit_fix,
     gds.util.asNode(targetNode) AS entry_fix,
     totalCost AS airway_dist_nm,
     [nid IN nodeIds | gds.util.asNode(nid).id] AS fix_chain

// Re-derive the airway label per hop.
UNWIND range(0, size(fix_chain)-2) AS i
MATCH (a:Fix {id: fix_chain[i]})
  -[r:NEIGHBOR_VIA]-(b:Fix {id: fix_chain[i+1]})
WITH dep, arr, sid_pairs, star_pairs,
     exit_fix, entry_fix, airway_dist_nm, fix_chain, i,
     {airway: r.airway, dist_nm: r.dist_nm,
      `from`: fix_chain[i], `to`: fix_chain[i+1]} AS hop
WITH dep, arr, sid_pairs, star_pairs,
     exit_fix, entry_fix, airway_dist_nm, fix_chain, i,
     min(hop) AS hop
ORDER BY i
WITH dep, arr, sid_pairs, star_pairs,
     exit_fix, entry_fix, airway_dist_nm,
     collect(hop) AS hops

// Fan out to every (sid_id, star_id) sharing this
// (exit, entry) pair.  These routes are identical
// except for the terminal procedure name.
WITH dep, arr, exit_fix, entry_fix, airway_dist_nm, hops,
     [s IN sid_pairs WHERE s.fix_id = exit_fix.id | s.sid_id] AS sids,
     [s IN star_pairs WHERE s.fix_id = entry_fix.id | s.star_id] AS stars,
     point.distance(
         point({latitude: dep.lat, longitude: dep.lon}),
         point({latitude: exit_fix.lat, longitude: exit_fix.lon})
     ) / 1852.0 AS sid_dist_nm,
     point.distance(
         point({latitude: arr.lat, longitude: arr.lon}),
         point({latitude: entry_fix.lat, longitude: entry_fix.lon})
     ) / 1852.0 AS star_dist_nm
UNWIND sids AS sid_id
UNWIND stars AS star_id
RETURN
    sid_id,
    exit_fix.id  AS sid_exit_fix,
    sid_dist_nm,
    star_id,
    entry_fix.id AS star_entry_fix,
    star_dist_nm,
    airway_dist_nm,
    sid_dist_nm + airway_dist_nm + star_dist_nm AS total_dist_nm,
    hops
ORDER BY total_dist_nm ASC
LIMIT $max_options
"""


def _sid_name(sid_id: str) -> str:
    # "KDFW-SID-AKUNA9-MLC" → "AKUNA9"
    parts = sid_id.split("-", 3)
    return parts[2] if len(parts) >= 3 else ""


def _star_name(star_id: str) -> str:
    return _sid_name(star_id)


def _preferred_routes(
    dep: str, arr: str, *, max_options: int,
) -> list[dict]:
    """Lookup ATC-favored routes in the FAA PFR table.

    Each hit returned alongside Dijkstra routes with
    ``source='preferred'`` so the UI can prefer them;
    ranked by FAA ``seq`` (the FAA's own ordering).
    Route string is pre-assembled by the FAA and
    mixes SID / fix / airway / STAR tokens — we
    ship it verbatim; downstream can tokenize for
    rendering.
    """
    rows = preferred_routes_cache.find_routes(dep, arr)
    if not rows:
        return []
    rows = rows[:max_options]
    return [
        {
            "dep": dep.upper(),
            "arr": arr.upper(),
            "source": "preferred",
            "route_type": r.get("route_type"),
            "route_string": r.get("route_string"),
            "altitude_ft": r.get("altitude_ft"),
            "aircraft": r.get("aircraft"),
            "direction": r.get("direction"),
            "dep_center": r.get("dep_center"),
            "arr_center": r.get("arr_center"),
            "seq": r.get("seq"),
        }
        for r in rows
    ]


def build_routes(
    dep: str, arr: str,
    *,
    dep_runway: str = "",
    arr_runway: str = "",
    max_options: int = 5,
    include_preferred: bool = True,
    include_direct: bool = True,
) -> list[dict]:
    """Top-N SID → airway → STAR combinations.

    Optional ``dep_runway`` / ``arr_runway`` (bare
    designators like ``"17R"``) fold in:

    - Matching runway-transition SID variant
      (e.g., ``KDFW-SID-AKUNA9-RW17R``) when
      ``dep_runway`` is set.
    - Matching runway-transition STAR variant
      (e.g., ``KJFK-STAR-PUCKY1-RW22L``).
    - Candidate IAPs whose name contains the
      runway designator (several publish styles:
      ``I22L``, ``H22LZ``, ``R22L`` — ``CONTAINS``
      catches them all).

    These are returned alongside the enroute chain
    (``sid_id`` / ``star_id``) rather than replacing
    it — real pilots file the enroute transition;
    the runway-transition variants get assigned by
    ATC at clearance or taxi.
    """
    dep_rwy = (dep_runway or "").upper().lstrip("RW")
    arr_rwy = (arr_runway or "").upper().lstrip("RW")
    preferred: list[dict] = (
        _preferred_routes(
            dep, arr, max_options=max_options,
        )
        if include_preferred
        else []
    )
    with graph_db.session() as s:
        _ensure_projection(s)
        result = s.run(
            _BUILD_ROUTES_CYPHER,
            dep=dep.upper(), arr=arr.upper(),
            max_options=max_options,
            max_hops=_MAX_AIRWAY_HOPS,
            graph_name=_GRAPH_NAME,
        )
        base_routes: list[dict] = []
        for row in result:
            hops = [dict(h) for h in row["hops"]]
            base_routes.append({
                "dep": dep.upper(),
                "arr": arr.upper(),
                "source": "dijkstra",
                "sid_id": row["sid_id"],
                "sid_exit_fix": row["sid_exit_fix"],
                "sid_dist_nm": row["sid_dist_nm"],
                "airway_hops": hops,
                "airway_dist_nm": row["airway_dist_nm"],
                "star_id": row["star_id"],
                "star_entry_fix": row["star_entry_fix"],
                "star_dist_nm": row["star_dist_nm"],
                "total_dist_nm": row["total_dist_nm"],
                "airway_summary": _airway_summary(hops),
            })
        # Decorate with runway + IAP pieces in one
        # extra Cypher per route — cheap vs the main
        # routing query and keeps the main Cypher
        # focused on shortest-path.
        for r in base_routes:
            pieces = s.run(
                _RUNWAY_PIECES_CYPHER,
                dep=dep.upper(), arr=arr.upper(),
                sid_name=_sid_name(r["sid_id"]),
                star_name=_star_name(r["star_id"]),
                dep_rwy=dep_rwy,
                arr_rwy=arr_rwy,
            ).single()
            r["sid_runway_id"] = (
                pieces["sid_runway_id"]
                if pieces else None
            )
            r["star_runway_id"] = (
                pieces["star_runway_id"]
                if pieces else None
            )
            r["iap_ids"] = (
                list(pieces["iap_ids"])
                if pieces else []
            )
            r["dep_runway"] = dep_rwy or None
            r["arr_runway"] = arr_rwy or None
        # Add DIRECT candidates — single great-circle
        # hop from SID exit to STAR entry, for RNAV
        # aircraft that could file direct under
        # favorable traffic conditions.  Computed
        # inline with the main session to reuse the
        # GDS graph projection's live connection.
        direct_opts: list[dict] = (
            _direct_routes(s, dep, arr,
                           max_options=max_options)
            if include_direct
            else []
        )
        # If no SID-based routes found and no preferred
        # routes, try vectored departure fallback (for
        # airports like KORD that have no published SIDs).
        vectored: list[dict] = []
        if not preferred and not base_routes:
            try:
                vectored = _vectored_routes(
                    s, dep, arr, max_options=max_options,
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Vectored-departure fallback failed",
                    exc_info=True,
                )
    # Ordering: FAA Preferred first (ATC favorite),
    # then shortest-airway Dijkstra paths, then
    # vectored departures, then DIRECT alternatives.
    merged = preferred + base_routes + vectored + direct_opts
    return merged[:max_options]


_DIRECT_GREAT_CIRCLE_CYPHER = """
// For each unique SID-exit / STAR-entry pair,
// compute the great-circle distance.  Useful as a
// "what if we flew direct" baseline that bypasses
// airway structure — RNAV aircraft commonly file
// DIRECT between VORs/fixes under 300 NM apart, or
// whenever ATC approves (it's a request, not a
// given).  Returns direct-route candidates only
// when the direct distance is meaningful — i.e.,
// not trivially small (same fix) and not absurdly
// long (transcontinental direct isn't realistic
// without ATC amendment).
MATCH (dep:Airport {icao: $dep})
  -[:DEPARTS_VIA]->(sid:Procedure)-[:ENDS_AT]->(exit_fix:Fix)
WHERE NOT sid.transition STARTS WITH 'RW'
  AND sid.transition <> ''
WITH dep,
     collect(DISTINCT {sid_id: sid.id, fix: exit_fix}) AS sid_pairs

MATCH (arr:Airport {icao: $arr})
  -[:ARRIVES_VIA]->(star:Procedure)-[:STARTS_AT]->(entry_fix:Fix)
WHERE NOT star.transition STARTS WITH 'RW'
  AND star.transition <> ''
WITH dep, arr, sid_pairs,
     collect(DISTINCT {star_id: star.id, fix: entry_fix}) AS star_pairs

UNWIND sid_pairs AS s
UNWIND star_pairs AS t
// Bind the UNWIND'd fix nodes in a dedicated WITH
// so they're in scope for the distance WITH below.
// Cypher can't reference a variable in the same
// WITH clause that defines it.
WITH dep, arr, s.sid_id AS sid_id, s.fix AS exit_fix,
     t.star_id AS star_id, t.fix AS entry_fix
WITH dep, arr, sid_id, exit_fix, star_id, entry_fix,
     point.distance(
         point({latitude: exit_fix.lat, longitude: exit_fix.lon}),
         point({latitude: entry_fix.lat, longitude: entry_fix.lon})
     ) / 1852.0 AS direct_dist_nm,
     point.distance(
         point({latitude: dep.lat, longitude: dep.lon}),
         point({latitude: exit_fix.lat, longitude: exit_fix.lon})
     ) / 1852.0 AS sid_dist_nm,
     point.distance(
         point({latitude: arr.lat, longitude: arr.lon}),
         point({latitude: entry_fix.lat, longitude: entry_fix.lon})
     ) / 1852.0 AS star_dist_nm
// Skip trivial same-fix hops and anything too long
// to be a realistic DIRECT (ATC seldom approves
// transcontinental direct without a specific
// operational reason).
WHERE direct_dist_nm > 10.0
  AND direct_dist_nm <= $max_direct_nm
RETURN
    sid_id, exit_fix.id AS sid_exit_fix, sid_dist_nm,
    star_id, entry_fix.id AS star_entry_fix, star_dist_nm,
    direct_dist_nm,
    sid_dist_nm + direct_dist_nm + star_dist_nm AS total_dist_nm
ORDER BY total_dist_nm ASC
LIMIT $max_options
"""


_MAX_DIRECT_NM = 600.0
_MAX_VECTOR_DIST_NM = 100.0  # search radius for vectored-departure fixes


def _direct_routes(
    s, dep: str, arr: str, *, max_options: int,
) -> list[dict]:
    """Add ``DIRECT`` options when the great-circle
    SID-exit → STAR-entry is reasonable.

    Each option uses a single synthetic hop tagged
    ``airway='DIRECT'``.  The frontend can render
    the hop as a straight 3D polyline (no airway
    polyline to follow).
    """
    result = s.run(
        _DIRECT_GREAT_CIRCLE_CYPHER,
        dep=dep.upper(), arr=arr.upper(),
        max_direct_nm=_MAX_DIRECT_NM,
        max_options=max_options,
    )
    out: list[dict] = []
    for row in result:
        hops = [{
            "airway": "DIRECT",
            "from": row["sid_exit_fix"],
            "to": row["star_entry_fix"],
            "dist_nm": row["direct_dist_nm"],
        }]
        out.append({
            "dep": dep.upper(),
            "arr": arr.upper(),
            "source": "direct",
            "sid_id": row["sid_id"],
            "sid_exit_fix": row["sid_exit_fix"],
            "sid_dist_nm": row["sid_dist_nm"],
            "airway_hops": hops,
            "airway_dist_nm": row["direct_dist_nm"],
            "star_id": row["star_id"],
            "star_entry_fix": row["star_entry_fix"],
            "star_dist_nm": row["star_dist_nm"],
            "total_dist_nm": row["total_dist_nm"],
            "airway_summary": _airway_summary(hops),
        })
    return out


_VECTORED_DEPARTURE_CYPHER = """
// Vectored-departure fallback: departure airport has
// no published SIDs in CIFP (e.g., KORD, which uses
// radar vectors instead).  Find the best airway-
// connected fixes near the departure as synthetic
// "SID exits", then run normal Dijkstra from each
// to the STAR entries.
MATCH (dep:Airport {icao: $dep}),
      (arr:Airport {icao: $arr})

// Nearby fixes that are on the airway graph (have
// NEIGHBOR_VIA edges) — candidate vector-to points.
MATCH (f:Fix)
WHERE EXISTS((f)-[:NEIGHBOR_VIA]-())
WITH dep, arr, f,
     point.distance(
         point({latitude: dep.lat, longitude: dep.lon}),
         point({latitude: f.lat, longitude: f.lon})
     ) / 1852.0 AS dep_dist_nm,
     point.distance(
         point({latitude: arr.lat, longitude: arr.lon}),
         point({latitude: f.lat, longitude: f.lon})
     ) / 1852.0 AS arr_dist_nm
WHERE dep_dist_nm < $max_vector_nm
// Pick the fixes that minimize total dep+arr distance
// (closest to the great-circle path).
ORDER BY dep_dist_nm + arr_dist_nm ASC
LIMIT 5
WITH dep, arr, collect(f) AS exit_fixes,
     collect(dep_dist_nm) AS exit_dists

// STAR entries — same as normal query.
MATCH (arr)-[:ARRIVES_VIA]->(star:Procedure)
  -[:STARTS_AT]->(entry_fix:Fix)
WHERE NOT star.transition STARTS WITH 'RW'
  AND star.transition <> ''
WITH dep, arr, exit_fixes, exit_dists,
     collect(DISTINCT entry_fix) AS entry_fixes,
     collect(DISTINCT {star_id: star.id, fix_id: entry_fix.id}) AS star_pairs

// Run GDS Dijkstra from each synthetic exit.
UNWIND range(0, size(exit_fixes)-1) AS idx
WITH dep, arr, exit_fixes[idx] AS exit_fix,
     exit_dists[idx] AS dep_dist_nm,
     entry_fixes, star_pairs
CALL gds.shortestPath.dijkstra.stream(
    $graph_name,
    {
        sourceNode: exit_fix,
        targetNodes: entry_fixes,
        relationshipWeightProperty: 'dist_nm'
    }
) YIELD targetNode, totalCost, nodeIds
WHERE size(nodeIds) > 1
  AND size(nodeIds) <= $max_hops + 1
WITH dep, arr, exit_fix, dep_dist_nm, star_pairs,
     gds.util.asNode(targetNode) AS entry_fix,
     totalCost AS airway_dist_nm,
     [nid IN nodeIds | gds.util.asNode(nid).id] AS fix_chain

// Rebuild airway labels per hop.
UNWIND range(0, size(fix_chain)-2) AS i
MATCH (a:Fix {id: fix_chain[i]})
  -[r:NEIGHBOR_VIA]-(b:Fix {id: fix_chain[i+1]})
WITH dep, arr, exit_fix, dep_dist_nm, star_pairs,
     entry_fix, airway_dist_nm, fix_chain, i,
     {airway: r.airway, dist_nm: r.dist_nm,
      `from`: fix_chain[i], `to`: fix_chain[i+1]} AS hop
WITH dep, arr, exit_fix, dep_dist_nm, star_pairs,
     entry_fix, airway_dist_nm, fix_chain, i,
     min(hop) AS hop
ORDER BY i
WITH dep, arr, exit_fix, dep_dist_nm, star_pairs,
     entry_fix, airway_dist_nm,
     collect(hop) AS hops

// Expand to star_ids sharing this entry fix.
WITH dep, arr, exit_fix, dep_dist_nm,
     entry_fix, airway_dist_nm, hops,
     [s IN star_pairs WHERE s.fix_id = entry_fix.id | s.star_id] AS stars,
     point.distance(
         point({latitude: arr.lat, longitude: arr.lon}),
         point({latitude: entry_fix.lat, longitude: entry_fix.lon})
     ) / 1852.0 AS star_dist_nm
UNWIND stars AS star_id
RETURN
    exit_fix.id  AS sid_exit_fix,
    dep_dist_nm  AS sid_dist_nm,
    star_id,
    entry_fix.id AS star_entry_fix,
    star_dist_nm,
    airway_dist_nm,
    dep_dist_nm + airway_dist_nm + star_dist_nm AS total_dist_nm,
    hops
ORDER BY total_dist_nm ASC
LIMIT $max_options
"""


def _vectored_routes(
    s, dep: str, arr: str, *, max_options: int,
) -> list[dict]:
    """Synthetic departure vectoring for airports
    without published SIDs.  Returns routes tagged
    ``source='vectored'`` with a descriptive
    ``sid_id='VECTORS-to-FIXNAME'``.
    """
    _ensure_projection(s)
    result = s.run(
        _VECTORED_DEPARTURE_CYPHER,
        dep=dep.upper(), arr=arr.upper(),
        max_options=max_options,
        max_hops=_MAX_AIRWAY_HOPS,
        max_vector_nm=_MAX_VECTOR_DIST_NM,
        graph_name=_GRAPH_NAME,
    )
    out: list[dict] = []
    for row in result:
        hops = [dict(h) for h in row["hops"]]
        exit_fix = row["sid_exit_fix"]
        out.append({
            "dep": dep.upper(),
            "arr": arr.upper(),
            "source": "vectored",
            "sid_id": f"VECTORS-to-{exit_fix}",
            "sid_exit_fix": exit_fix,
            "sid_dist_nm": row["sid_dist_nm"],
            "airway_hops": hops,
            "airway_dist_nm": row["airway_dist_nm"],
            "star_id": row["star_id"],
            "star_entry_fix": row["star_entry_fix"],
            "star_dist_nm": row["star_dist_nm"],
            "total_dist_nm": row["total_dist_nm"],
            "airway_summary": _airway_summary(hops),
        })
    return out


def _airway_summary(hops: list[dict]) -> str:
    """Compact ``MLC.J501.BUM.V23.EWR`` rendering."""
    if not hops:
        return ""
    parts: list[str] = [hops[0]["from"]]
    cur_airway = hops[0]["airway"]
    parts.append(cur_airway)
    for h in hops:
        if h["airway"] != cur_airway:
            parts.append(h["airway"])
            cur_airway = h["airway"]
        parts.append(h["to"])
    return ".".join(parts)
