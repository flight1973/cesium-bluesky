"""Download 1 Hz state vectors from OpenSky Trino database.

Requires an approved OpenSky research account. Credentials
are read from the credential vault (integration: 'opensky')
or from environment variables OPENSKY_USERNAME / OPENSKY_PASSWORD
or from ~/.config/pyopensky/settings.conf (pyopensky default).

Usage (CLI):
    python -m cesium_app.surveillance.trino_download \\
        --start "2024-06-27 15:00" \\
        --stop "2024-06-27 16:00" \\
        --bbox 31.5,-98.5,34.0,-96.0 \\
        --label dfw-1hz

The data goes into the same replay.db SQLite database as
the free 10s samples, but at true 1-second resolution.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_credentials() -> tuple[str, str] | None:
    """Try credential vault, then env vars."""
    try:
        from cesium_app.credentials import get_secret
        user = get_secret('opensky', 'username')
        pwd = get_secret('opensky', 'password')
        if user and pwd:
            return (user, pwd)
    except Exception:
        pass

    import os
    user = os.environ.get('OPENSKY_USERNAME', '')
    pwd = os.environ.get('OPENSKY_PASSWORD', '')
    if user and pwd:
        return (user, pwd)

    return None


def download(
    start: str,
    stop: str,
    bbox: tuple[float, float, float, float],
    label: str,
) -> int:
    """Download 1 Hz state vectors via Trino and store in replay.db.

    Args:
        start: ISO datetime string (e.g. "2024-06-27 15:00")
        stop:  ISO datetime string (e.g. "2024-06-27 16:00")
        bbox:  (lat_s, lon_w, lat_n, lon_e)
        label: Session label for replay.db

    Returns:
        Number of rows inserted.
    """
    try:
        from pyopensky.trino import Trino
    except ImportError:
        raise RuntimeError(
            "pyopensky not installed. Run: pip install pyopensky"
        )

    logger.info(
        "Querying Trino: %s to %s, bbox=%s",
        start, stop, bbox,
    )

    trino = Trino()

    creds = _get_credentials()
    if creds:
        logger.info("Using credentials for user: %s", creds[0])

    t0 = time.monotonic()
    df = trino.history(
        start=start,
        stop=stop,
        bounds=bbox,
    )
    elapsed = time.monotonic() - t0

    if df is None or len(df) == 0:
        logger.warning("Trino returned no data.")
        return 0

    logger.info(
        "Trino returned %d rows in %.1fs",
        len(df), elapsed,
    )

    from cesium_app.surveillance.replay import (
        _connect, _ensure_schema,
    )
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

    n = 0
    batch: list[tuple] = []

    for _, row in df.iterrows():
        lat = row.get('latitude') or row.get('lat')
        lon = row.get('longitude') or row.get('lon')
        if lat is None or lon is None:
            continue

        timestamp = row.get('timestamp')
        if hasattr(timestamp, 'timestamp'):
            epoch = int(timestamp.timestamp())
        else:
            epoch = int(timestamp) if timestamp else 0

        icao24 = str(row.get('icao24', '')).strip().lower()
        if not icao24:
            continue

        velocity = row.get('velocity') or row.get('groundspeed')
        heading = row.get('heading') or row.get('track')
        vertrate = row.get('vertical_rate') or row.get('vertrate')
        callsign = str(row.get('callsign', '')).strip()
        onground = 1 if row.get('onground') else 0
        squawk = str(row.get('squawk', '')).strip()
        baro_alt = row.get('baroaltitude') or row.get('altitude')
        geo_alt = row.get('geoaltitude')

        batch.append((
            label, epoch, icao24,
            float(lat), float(lon),
            float(velocity) if velocity is not None else None,
            float(heading) if heading is not None else None,
            float(vertrate) if vertrate is not None else None,
            callsign, onground, squawk,
            float(baro_alt) if baro_alt is not None else None,
            float(geo_alt) if geo_alt is not None else None,
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

    # Parse date from start string for the session record
    date_str = start[:10]
    bbox_str = ",".join(str(x) for x in bbox)

    conn.execute(
        "INSERT INTO replay_sessions "
        "(label, date, bbox, hours, row_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (label, date_str, bbox_str, f"trino:{start}/{stop}", n),
    )
    conn.commit()
    conn.close()

    logger.info(
        "Session '%s': %d rows at 1 Hz resolution.", label, n,
    )
    return n


def _cli():
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser(
        description="Download 1 Hz OpenSky data via Trino",
    )
    p.add_argument('--start', required=True,
                   help='Start time (ISO, e.g. "2024-06-27 15:00")')
    p.add_argument('--stop', required=True,
                   help='Stop time (ISO)')
    p.add_argument('--bbox', required=True,
                   help='Bounding box: lat_s,lon_w,lat_n,lon_e')
    p.add_argument('--label', required=True,
                   help='Session label')

    args = p.parse_args()
    bbox = tuple(float(x) for x in args.bbox.split(','))
    assert len(bbox) == 4, "bbox must have 4 values"

    n = download(args.start, args.stop, bbox, args.label)
    print(f"Done: {n} rows in session '{args.label}'")


if __name__ == '__main__':
    _cli()
