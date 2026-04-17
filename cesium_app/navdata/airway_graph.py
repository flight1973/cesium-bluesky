"""Directed graph over airway fixes + Dijkstra.

The fix→fix adjacency is built from ``airway_fix``:
consecutive rows within the same airway (by seq) are
adjacent, bidirectionally.  Edge weight is the
great-circle distance between the two fixes in
nautical miles.

Loaded lazily from SQLite on first query and held in
memory — the US airway network is ~15 K fixes and
~30 K edges, so the graph fits in a few MB.  Freshness
check reloads whenever the ingest writes new rows.
"""
from __future__ import annotations

import heapq
import logging
import threading
from dataclasses import dataclass, field
from math import inf

from pyproj import Geod

from cesium_app.store import airways_cache
from cesium_app.store.db import connect

logger = logging.getLogger(__name__)

_GEOD = Geod(ellps="WGS84")
_NM_TO_M = 1852.0


@dataclass
class AirwayEdge:
    """One segment along an airway."""
    airway: str
    from_fix: str
    to_fix: str
    dist_nm: float


@dataclass
class AirwayGraph:
    """In-memory airway graph keyed by fix id.

    ``adj[fix_id]`` → list of outgoing edges.  Fix
    positions are kept alongside so Dijkstra can
    apply an A* heuristic (great-circle to target)
    for faster convergence on cross-country routes.
    """
    adj: dict[str, list[AirwayEdge]] = field(default_factory=dict)
    pos: dict[str, tuple[float, float]] = field(default_factory=dict)
    # ``airway_fix`` row count at build time — used
    # by :func:`_stale` to detect ingest refreshes.
    source_rows: int = 0


_graph: AirwayGraph | None = None
_lock = threading.Lock()


def _build() -> AirwayGraph:
    """One-shot load of all airway fixes into memory."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT airway_name, seq, fix_id, lat, lon "
            "FROM airway_fix ORDER BY airway_name, seq",
        ).fetchall()
    finally:
        conn.close()

    g = AirwayGraph()
    # Group consecutive same-airway rows and wire
    # bidirectional edges between successive fixes.
    prev: dict | None = None
    for r in rows:
        fix_id = r["fix_id"]
        pos = (r["lat"], r["lon"])
        g.pos.setdefault(fix_id, pos)
        if prev and prev["airway_name"] == r["airway_name"]:
            _, _, d_m = _GEOD.inv(
                prev["lon"], prev["lat"], r["lon"], r["lat"],
            )
            d_nm = d_m / _NM_TO_M
            edge_fwd = AirwayEdge(
                r["airway_name"], prev["fix_id"], fix_id, d_nm,
            )
            edge_rev = AirwayEdge(
                r["airway_name"], fix_id, prev["fix_id"], d_nm,
            )
            g.adj.setdefault(prev["fix_id"], []).append(edge_fwd)
            g.adj.setdefault(fix_id, []).append(edge_rev)
        prev = dict(r)
    g.source_rows = len(rows)
    logger.info(
        "Airway graph: %d fixes, %d edges",
        len(g.pos),
        sum(len(e) for e in g.adj.values()) // 2,
    )
    return g


def graph() -> AirwayGraph:
    """Lazy, thread-safe singleton.

    Reloads if the airway table has been repopulated
    since the last build (compared via row count).
    """
    global _graph
    with _lock:
        if _graph is None:
            _graph = _build()
        elif _stale():
            logger.info("Airway graph stale; rebuilding")
            _graph = _build()
        return _graph


def _stale() -> bool:
    if _graph is None:
        return True
    return airways_cache.airway_fix_count() != _graph.source_rows


@dataclass
class RouteHop:
    """One leg in a routed path: A→B along an airway."""
    airway: str
    from_fix: str
    to_fix: str
    dist_nm: float


def shortest_path(
    start: str, end: str,
) -> list[RouteHop] | None:
    """A* from ``start`` fix id to ``end`` fix id.

    Returns the ordered hop list, or None if no path
    exists through the airway network.  Uses great-
    circle distance as both weight and heuristic, so
    the search is admissible (never overestimates) and
    optimal.
    """
    g = graph()
    start = start.upper()
    end = end.upper()
    if start not in g.pos or end not in g.pos:
        return None
    if start == end:
        return []
    end_pos = g.pos[end]

    def _h(fix: str) -> float:
        fp = g.pos.get(fix)
        if fp is None:
            return inf
        _, _, d_m = _GEOD.inv(
            fp[1], fp[0], end_pos[1], end_pos[0],
        )
        return d_m / _NM_TO_M

    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, AirwayEdge]] = {}
    heap: list[tuple[float, str]] = [(_h(start), start)]
    while heap:
        _, cur = heapq.heappop(heap)
        if cur == end:
            hops: list[RouteHop] = []
            k = end
            while k in prev:
                pk, edge = prev[k]
                hops.append(RouteHop(
                    edge.airway, edge.from_fix,
                    edge.to_fix, edge.dist_nm,
                ))
                k = pk
            return list(reversed(hops))
        for edge in g.adj.get(cur, []):
            nd = dist[cur] + edge.dist_nm
            if nd < dist.get(edge.to_fix, inf):
                dist[edge.to_fix] = nd
                prev[edge.to_fix] = (cur, edge)
                heapq.heappush(
                    heap, (nd + _h(edge.to_fix), edge.to_fix),
                )
    return None


def path_distance_nm(hops: list[RouteHop]) -> float:
    return sum(h.dist_nm for h in hops)


def path_polyline(
    hops: list[RouteHop],
) -> list[tuple[float, float]]:
    """Hop sequence → lat/lon points along the route."""
    g = graph()
    out: list[tuple[float, float]] = []
    if not hops:
        return out
    first = g.pos.get(hops[0].from_fix)
    if first is not None:
        out.append(first)
    for h in hops:
        p = g.pos.get(h.to_fix)
        if p is not None:
            out.append(p)
    return out
