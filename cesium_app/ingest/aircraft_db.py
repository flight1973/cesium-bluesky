"""Aircraft registration database ingest.

Downloads the OpenSky Network aircraft metadata
(~520K records, free, global coverage) and
populates the ``aircraft_registry`` table.  This
gives us icao24 → tail number + type + operator
for every live ADS-B contact.

Source: ``opensky-network.org/datasets/metadata/``
Redirects to S3. No auth needed.  Refresh monthly.

Falls back gracefully if download fails — live
aircraft still render, just without enriched
identity labels.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from pathlib import Path

import httpx

from cesium_app.store.db import connect, _data_dir

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = (
    "https://opensky-network.org/datasets/metadata/"
    "aircraftDatabase.csv"
)
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
DOWNLOAD_TIMEOUT_SEC = 120.0


def _cache_path() -> Path:
    return _data_dir() / "aircraft_db.csv"


def _ensure_table() -> None:
    conn = connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS aircraft_registry (
                icao24        TEXT PRIMARY KEY,
                registration  TEXT,
                typecode      TEXT,
                model         TEXT,
                manufacturer  TEXT,
                operator      TEXT,
                operator_icao TEXT,
                owner         TEXT,
                ac_type_icao  TEXT,
                built         TEXT,
                source        TEXT NOT NULL DEFAULT 'OPENSKY'
            );
            CREATE INDEX IF NOT EXISTS idx_reg_registration
              ON aircraft_registry(registration);
        """)
    finally:
        conn.close()


async def download() -> Path:
    """Download the CSV to the data dir.  Returns path."""
    out = _cache_path()
    async with httpx.AsyncClient(
        timeout=DOWNLOAD_TIMEOUT_SEC,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    ) as client:
        res = await client.get(_DOWNLOAD_URL)
        res.raise_for_status()
        out.write_bytes(res.content)
    logger.info(
        "Downloaded aircraft DB: %.1f MB",
        out.stat().st_size / 1e6,
    )
    return out


def load(csv_path: Path | None = None) -> int:
    """Parse the CSV and populate aircraft_registry.

    Returns the number of rows loaded.
    """
    if csv_path is None:
        csv_path = _cache_path()
    if not csv_path.exists():
        logger.warning(
            "Aircraft DB CSV not found at %s", csv_path,
        )
        return 0
    _ensure_table()
    conn = connect()
    n = 0
    try:
        with conn:
            conn.execute("DELETE FROM aircraft_registry")
            with csv_path.open(
                "r", encoding="utf-8", errors="replace",
            ) as fh:
                reader = csv.DictReader(fh)
                batch: list[tuple] = []
                for row in reader:
                    icao24 = (
                        row.get("icao24") or ""
                    ).strip().lower()
                    if not icao24:
                        continue
                    batch.append((
                        icao24,
                        (row.get("registration") or "").strip(),
                        (row.get("typecode") or "").strip(),
                        (row.get("model") or "").strip(),
                        (row.get("manufacturername") or "").strip(),
                        (row.get("operator") or "").strip(),
                        (row.get("operatoricao") or "").strip(),
                        (row.get("owner") or "").strip(),
                        (row.get("icaoaircrafttype") or "").strip(),
                        (row.get("built") or "").strip(),
                        "OPENSKY",
                    ))
                    if len(batch) >= 5000:
                        conn.executemany(
                            "INSERT OR IGNORE INTO "
                            "aircraft_registry VALUES"
                            "(?,?,?,?,?,?,?,?,?,?,?)",
                            batch,
                        )
                        n += len(batch)
                        batch = []
                if batch:
                    conn.executemany(
                        "INSERT OR IGNORE INTO "
                        "aircraft_registry VALUES"
                        "(?,?,?,?,?,?,?,?,?,?,?)",
                        batch,
                    )
                    n += len(batch)
    finally:
        conn.close()
    logger.info("Loaded %d aircraft into registry.", n)
    return n


def lookup(icao24: str) -> dict | None:
    """Resolve an ICAO24 hex to registration info."""
    _ensure_table()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM aircraft_registry "
            "WHERE icao24 = ?",
            (icao24.lower(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def lookup_batch(
    icao24s: list[str],
) -> dict[str, dict]:
    """Batch lookup — returns {icao24: info} dict."""
    if not icao24s:
        return {}
    _ensure_table()
    conn = connect()
    try:
        placeholders = ",".join("?" * len(icao24s))
        rows = conn.execute(
            f"SELECT * FROM aircraft_registry "
            f"WHERE icao24 IN ({placeholders})",
            [h.lower() for h in icao24s],
        ).fetchall()
        return {r["icao24"]: dict(r) for r in rows}
    finally:
        conn.close()


def count() -> int:
    _ensure_table()
    conn = connect()
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM aircraft_registry"
        ).fetchone()[0])
    finally:
        conn.close()
