"""Historic traffic replay from OpenSky state vector samples.

Downloads hourly state-vector CSVs from the OpenSky S3
bucket, filters to a geographic bounding box, stores the
result in SQLite, and serves time-sliced snapshots through
the same shape as the live surveillance endpoint.

Usage (CLI):
    python -m cesium_app.surveillance.replay download \\
        --date 2022-06-27 --hours 14,15,16,17,18 \\
        --bbox 31.5,-98.5,34.0,-96.0 --label dfw

    python -m cesium_app.surveillance.replay list

State vector source (no auth, free):
    https://opensky-network.org/datasets/states/
    Weekly Tuesday snapshots, 2017-06 through 2022-06.
"""
from __future__ import annotations

import csv
import gzip
import io
import logging
import sqlite3
import tarfile
import time
from pathlib import Path

import httpx

from cesium_app.store.db import _data_dir

logger = logging.getLogger(__name__)

_S3_BASE = (
    "https://s3.opensky-network.org/data-samples/states"
)

# OpenSky CSV columns (verified from README + sample)
_COLS = [
    "time", "icao24", "lat", "lon", "velocity",
    "heading", "vertrate", "callsign", "onground",
    "alert", "spi", "squawk", "baroaltitude",
    "geoaltitude", "lastposupdate", "lastcontact",
]

_M_TO_FT = 3.28084
_MS_TO_KT = 1.94384
_MS_TO_FPM = 196.85


def _db_path() -> Path:
    return _data_dir() / "replay.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS replay_sessions (
            label       TEXT PRIMARY KEY,
            date        TEXT NOT NULL,
            bbox        TEXT NOT NULL,
            hours       TEXT NOT NULL,
            row_count   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS replay_states (
            session     TEXT NOT NULL,
            time        INTEGER NOT NULL,
            icao24      TEXT NOT NULL,
            lat         REAL,
            lon         REAL,
            velocity    REAL,
            heading     REAL,
            vertrate    REAL,
            callsign    TEXT,
            onground    INTEGER,
            squawk      TEXT,
            baro_alt    REAL,
            geo_alt     REAL
        );

        CREATE INDEX IF NOT EXISTS idx_replay_time
            ON replay_states(session, time);
        CREATE INDEX IF NOT EXISTS idx_replay_icao
            ON replay_states(session, icao24, time);
    """)


# ── Download + filter ──────────────────────────────────


def _hour_url(date: str, hour: int) -> str:
    hh = f"{hour:02d}"
    return (
        f"{_S3_BASE}/{date}/{hh}/"
        f"states_{date}-{hh}.csv.tar"
    )


def _parse_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


async def download_hour(
    date: str,
    hour: int,
    bbox: tuple[float, float, float, float],
    session_label: str,
    conn: sqlite3.Connection,
) -> int:
    """Download one hour, filter to bbox, insert rows.

    Returns count of rows inserted for this hour.
    """
    url = _hour_url(date, hour)
    lat_s, lon_w, lat_n, lon_e = bbox
    logger.info("Downloading %s ...", url)

    async with httpx.AsyncClient(
        timeout=300.0,
        follow_redirects=True,
        headers={"User-Agent": "cesium-bluesky/0.1"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    raw = resp.content
    logger.info(
        "Downloaded %.1f MB, extracting...",
        len(raw) / 1e6,
    )

    n = 0
    batch: list[tuple] = []

    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        for member in tf.getmembers():
            if not member.name.endswith('.csv.gz'):
                continue
            fobj = tf.extractfile(member)
            if fobj is None:
                continue
            with gzip.open(fobj, 'rt', encoding='utf-8',
                           errors='replace') as gz:
                reader = csv.DictReader(gz)
                for row in reader:
                    lat = _parse_float(row.get('lat', ''))
                    lon = _parse_float(row.get('lon', ''))
                    if lat is None or lon is None:
                        continue
                    if not (lat_s <= lat <= lat_n
                            and lon_w <= lon <= lon_e):
                        continue

                    batch.append((
                        session_label,
                        int(row.get('time', 0)),
                        row.get('icao24', '').strip(),
                        lat, lon,
                        _parse_float(row.get('velocity')),
                        _parse_float(row.get('heading')),
                        _parse_float(row.get('vertrate')),
                        (row.get('callsign') or '').strip(),
                        1 if row.get('onground') == 'True'
                        else 0,
                        (row.get('squawk') or '').strip(),
                        _parse_float(
                            row.get('baroaltitude')),
                        _parse_float(
                            row.get('geoaltitude')),
                    ))
                    if len(batch) >= 10000:
                        conn.executemany(
                            "INSERT INTO replay_states "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            batch,
                        )
                        conn.commit()
                        n += len(batch)
                        batch = []

    if batch:
        conn.executemany(
            "INSERT INTO replay_states "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
        n += len(batch)

    logger.info(
        "Hour %02d: %d DFW rows extracted.", hour, n,
    )
    return n


async def download_session(
    date: str,
    hours: list[int],
    bbox: tuple[float, float, float, float],
    label: str,
) -> int:
    """Download multiple hours and store as a session."""
    conn = _connect()
    _ensure_schema(conn)

    conn.execute(
        "DELETE FROM replay_states WHERE session = ?",
        (label,),
    )
    conn.execute(
        "DELETE FROM replay_sessions WHERE label = ?",
        (label,),
    )
    conn.commit()

    total = 0
    for h in hours:
        n = await download_hour(date, h, bbox, label, conn)
        total += n

    bbox_str = ",".join(str(x) for x in bbox)
    hours_str = ",".join(str(h) for h in hours)
    conn.execute(
        "INSERT INTO replay_sessions "
        "(label, date, bbox, hours, row_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (label, date, bbox_str, hours_str, total),
    )
    conn.commit()
    conn.close()

    logger.info(
        "Session '%s': %d total rows across %d hours.",
        label, total, len(hours),
    )
    return total


# ── Query (replay serving) ─────────────────────────────


def list_sessions() -> list[dict]:
    conn = _connect()
    _ensure_schema(conn)
    rows = conn.execute(
        "SELECT * FROM replay_sessions "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_snapshot(
    label: str,
    epoch: int,
    tolerance: int = 5,
) -> list[dict]:
    """Get all aircraft positions at a given epoch.

    Returns the latest state for each icao24 within
    [epoch - tolerance, epoch].  Normalizes to the
    ObservedAircraft shape used by the live feed.
    """
    conn = _connect()
    _ensure_schema(conn)

    rows = conn.execute("""
        SELECT s.*
        FROM replay_states s
        INNER JOIN (
            SELECT icao24, MAX(time) AS mt
            FROM replay_states
            WHERE session = ?
              AND time BETWEEN ? AND ?
            GROUP BY icao24
        ) g ON s.icao24 = g.icao24 AND s.time = g.mt
        WHERE s.session = ?
          AND s.time BETWEEN ? AND ?
    """, (label, epoch - tolerance, epoch,
          label, epoch - tolerance, epoch)).fetchall()
    conn.close()

    items = []
    for r in rows:
        alt_m = r['geo_alt'] or r['baro_alt'] or 0
        vel = r['velocity'] or 0
        vr = r['vertrate'] or 0
        items.append({
            "icao24": r['icao24'],
            "callsign": r['callsign'] or '',
            "lat": r['lat'],
            "lon": r['lon'],
            "alt_m": alt_m,
            "alt_ft": alt_m * _M_TO_FT,
            "gs_kt": vel * _MS_TO_KT,
            "trk_deg": r['heading'] or 0,
            "vs_fpm": vr * _MS_TO_FPM,
            "on_ground": bool(r['onground']),
            "squawk": r['squawk'] or '',
            "source": "REPLAY",
        })
    return items


def get_trails(
    label: str,
    t_start: int | None,
    t_end: int,
    step: int = 1,
) -> dict[str, list[list[float]]]:
    """Get trails between t_start and t_end.

    If t_start is None, uses the session start.
    Returns {icao24: [[lat, lon, alt_m], ...]} for each
    aircraft in the time range.
    """
    conn = _connect()
    _ensure_schema(conn)

    if t_start is None:
        r = get_time_range(label)
        if r is None:
            conn.close()
            return {}
        t_start = r[0]

    if step <= 1:
        rows = conn.execute("""
            SELECT icao24, time, lat, lon,
                   COALESCE(geo_alt, baro_alt, 0) AS alt
            FROM replay_states
            WHERE session = ?
              AND time BETWEEN ? AND ?
            ORDER BY icao24, time
        """, (label, t_start, t_end)).fetchall()
    else:
        rows = conn.execute("""
            SELECT icao24, time, lat, lon,
                   COALESCE(geo_alt, baro_alt, 0) AS alt
            FROM replay_states
            WHERE session = ?
              AND time BETWEEN ? AND ?
              AND time % ? < 2
            ORDER BY icao24, time
        """, (label, t_start, t_end, step)).fetchall()
    conn.close()

    trails: dict[str, list[list[float]]] = {}
    for r in rows:
        icao = r['icao24']
        if icao not in trails:
            trails[icao] = []
        trails[icao].append([r['lat'], r['lon'], r['alt']])
    return trails


def get_time_range(label: str) -> tuple[int, int] | None:
    conn = _connect()
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT MIN(time), MAX(time) "
        "FROM replay_states WHERE session = ?",
        (label,),
    ).fetchone()
    conn.close()
    if row and row[0] is not None:
        return (row[0], row[1])
    return None


# ── CLI entry point ────────────────────────────────────


def _cli():
    import asyncio
    import sys

    args = sys.argv[1:]
    if not args or args[0] == 'list':
        sessions = list_sessions()
        if not sessions:
            print("No replay sessions.")
            return
        print(f"{'Label':<20s}  {'Date':<12s}  "
              f"{'Hours':<20s}  {'Rows':>8s}")
        print(f"{'-'*20}  {'-'*12}  {'-'*20}  {'-'*8}")
        for s in sessions:
            print(f"{s['label']:<20s}  {s['date']:<12s}  "
                  f"{s['hours']:<20s}  "
                  f"{s['row_count']:>8d}")
        return

    if args[0] == 'download':
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument('--date', required=True)
        p.add_argument('--hours', required=True)
        p.add_argument('--bbox', required=True)
        p.add_argument('--label', required=True)
        opts = p.parse_args(args[1:])

        hours = [int(h) for h in opts.hours.split(',')]
        bbox = tuple(float(x) for x in opts.bbox.split(','))
        assert len(bbox) == 4

        total = asyncio.run(
            download_session(opts.date, hours, bbox, opts.label)
        )
        print(f"Done: {total} rows in session '{opts.label}'")
        return

    print(f"Unknown command: {args[0]}")
    print("Usage: replay [list|download --date ... "
          "--hours ... --bbox ... --label ...]")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _cli()
