"""Read/write API for cached airspace features.

Public functions are sync (sqlite3 is blocking).
Callers in async code should wrap via
``asyncio.to_thread``.

The geometry-bbox used for R-tree indexing is
computed from the feature's rings — the union of all
ring vertex extents.  That's a conservative (often
too-wide) bbox, but it's cheap and correct: any
polygon that intersects a query window must have a
bbox that intersects it too.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Iterable

from cesium_app.store.db import connect


def _ring_bbox(
    rings: list[list[tuple[float, float]]],
) -> tuple[float, float, float, float] | None:
    """Union bbox (min_lat, max_lat, min_lon, max_lon)."""
    mn_lat = mn_lon = float("inf")
    mx_lat = mx_lon = float("-inf")
    any_point = False
    for ring in rings:
        for pt in ring:
            if len(pt) < 2:
                continue
            lat, lon = float(pt[0]), float(pt[1])
            if lat < mn_lat: mn_lat = lat
            if lat > mx_lat: mx_lat = lat
            if lon < mn_lon: mn_lon = lon
            if lon > mx_lon: mx_lon = lon
            any_point = True
    if not any_point:
        return None
    return mn_lat, mx_lat, mn_lon, mx_lon


def replace_source(
    source: str,
    items: Iterable[dict],
) -> int:
    """Atomically replace all rows for a given source.

    ``source`` is a stable tag (e.g., ``"class_airspace"``
    or ``"sua"``) that scopes the delete.  Used by the
    ingest CLI so a refresh of class airspace doesn't
    wipe SUAs.

    Returns the number of rows written.
    """
    now = time.time()
    conn = connect()
    try:
        with conn:
            # Collect rowids to purge from the r-tree too.
            rowids = [
                r[0] for r in conn.execute(
                    "SELECT rowid FROM airspace "
                    "WHERE source = ?", (source,),
                )
            ]
            if rowids:
                placeholders = ",".join("?" * len(rowids))
                conn.execute(
                    f"DELETE FROM airspace_rtree "
                    f"WHERE id IN ({placeholders})",
                    rowids,
                )
                conn.execute(
                    "DELETE FROM airspace "
                    "WHERE source = ?", (source,),
                )
            # Handle cross-source id collisions (e.g.,
            # user manually ingested same dataset under
            # two source tags) by deleting by id first.
            seen_ids: set[str] = set()
            count = 0
            for item in items:
                bbox = _ring_bbox(item.get("rings") or [])
                if bbox is None:
                    continue
                if item["id"] in seen_ids:
                    continue
                seen_ids.add(item["id"])
                # Purge any prior row with this id from
                # a different source — keeps INSERT safe.
                prior = conn.execute(
                    "SELECT rowid FROM airspace WHERE id = ?",
                    (item["id"],),
                ).fetchone()
                if prior is not None:
                    conn.execute(
                        "DELETE FROM airspace_rtree "
                        "WHERE id = ?", (prior[0],),
                    )
                    conn.execute(
                        "DELETE FROM airspace WHERE id = ?",
                        (item["id"],),
                    )
                t = item.get("type") or ""
                subtype = (
                    item.get("airspace_class")
                    or item.get("sua_class")
                    or None
                )
                cur = conn.execute(
                    "INSERT INTO airspace("
                    "id, type, subtype, bottom_ft, top_ft,"
                    "props_json, source, fetched_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["id"], t, subtype,
                        item.get("bottom_ft"),
                        item.get("top_ft"),
                        json.dumps(item),
                        source, now,
                    ),
                )
                rowid = cur.lastrowid
                mn_lat, mx_lat, mn_lon, mx_lon = bbox
                conn.execute(
                    "INSERT INTO airspace_rtree("
                    "id, min_lat, max_lat, min_lon, max_lon) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (rowid, mn_lat, mx_lat, mn_lon, mx_lon),
                )
                count += 1
            return count
    finally:
        conn.close()


def query(
    *,
    type_: str | None = None,
    subtypes: set[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """Fetch features, optionally filtered.

    * ``type_``: ``"CLASS"`` or ``"SUA"`` (``None`` = all).
    * ``subtypes``: single-letter class codes; ``None`` = all.
    * ``bbox``: ``(lat_s, lon_w, lat_n, lon_e)``; None = global.
    """
    conn = connect()
    try:
        sql = (
            "SELECT a.props_json FROM airspace a"
        )
        params: list = []
        where: list[str] = []
        if bbox is not None:
            lat_s, lon_w, lat_n, lon_e = bbox
            sql += (
                " JOIN airspace_rtree r ON r.id = a.rowid"
            )
            where.append(
                "r.min_lat <= ? AND r.max_lat >= ? "
                "AND r.min_lon <= ? AND r.max_lon >= ?"
            )
            params.extend([lat_n, lat_s, lon_e, lon_w])
        if type_ is not None:
            where.append("a.type = ?")
            params.append(type_)
        if subtypes:
            placeholders = ",".join("?" * len(subtypes))
            where.append(f"a.subtype IN ({placeholders})")
            params.extend(sorted(subtypes))
        if where:
            sql += " WHERE " + " AND ".join(where)
        return [
            json.loads(row[0])
            for row in conn.execute(sql, params)
        ]
    finally:
        conn.close()


def source_info(source: str) -> dict | None:
    """Row count + age in seconds for a given source."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(fetched_at) AS t "
            "FROM airspace WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None or row["n"] == 0:
            return None
        return {
            "count": row["n"],
            "age_sec": time.time() - row["t"],
        }
    finally:
        conn.close()


def has_source(source: str) -> bool:
    return source_info(source) is not None


# ─── cache_source metadata (update-cycle tracking) ──

def register_source(
    source: str,
    *,
    label: str,
    cadence_days: int | None,
    endpoint: str | None,
) -> None:
    """Declare a dataset to the cache tracker.

    Idempotent — updates static fields (label /
    cadence / endpoint) on each call, preserving
    fetched_at / row_count from prior runs.  Safe to
    call on every app start.
    """
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO cache_source("
                "source, label, cadence_days, endpoint) "
                "VALUES(?, ?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET "
                " label = excluded.label,"
                " cadence_days = excluded.cadence_days,"
                " endpoint = excluded.endpoint",
                (source, label, cadence_days, endpoint),
            )
    finally:
        conn.close()


def record_fetch_success(
    source: str,
    row_count: int,
) -> None:
    """Stamp a successful ingest; clears any prior error."""
    now = time.time()
    conn = connect()
    try:
        with conn:
            row = conn.execute(
                "SELECT cadence_days FROM cache_source "
                "WHERE source = ?", (source,),
            ).fetchone()
            cadence = (
                row["cadence_days"] if row else None
            )
            next_refresh = (
                now + cadence * 86400.0
                if cadence else None
            )
            conn.execute(
                "UPDATE cache_source SET "
                " last_fetched_at = ?,"
                " last_row_count = ?,"
                " next_refresh_at = ?,"
                " last_error = NULL,"
                " last_error_at = NULL "
                "WHERE source = ?",
                (now, row_count, next_refresh, source),
            )
    finally:
        conn.close()


def record_fetch_error(source: str, err: str) -> None:
    """Stamp a failed ingest; preserves prior success data."""
    now = time.time()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "UPDATE cache_source SET "
                " last_error = ?, last_error_at = ? "
                "WHERE source = ?",
                (err[:500], now, source),
            )
    finally:
        conn.close()


def list_sources() -> list[dict]:
    """All registered datasets with their freshness state."""
    now = time.time()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM cache_source ORDER BY source"
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            fetched = r["last_fetched_at"]
            age_sec = (now - fetched) if fetched else None
            next_at = r["next_refresh_at"]
            stale = (
                next_at is not None
                and now > next_at
            )
            out.append({
                "source": r["source"],
                "label": r["label"],
                "cadence_days": r["cadence_days"],
                "endpoint": r["endpoint"],
                "last_fetched_at": fetched,
                "last_row_count": r["last_row_count"],
                "age_sec": age_sec,
                "next_refresh_at": next_at,
                "stale": bool(stale),
                "last_error": r["last_error"],
                "last_error_at": r["last_error_at"],
            })
        return out
    finally:
        conn.close()


def wipe() -> None:
    """Delete all cached rows (test helper)."""
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM airspace_rtree")
            conn.execute("DELETE FROM airspace")
    finally:
        conn.close()
