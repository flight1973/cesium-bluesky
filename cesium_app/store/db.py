"""SQLite connection + schema for the FAA cache.

The schema intentionally uses JSON-in-a-column for
the feature payload (``props_json``).  We only need
SQL to do two things fast:

1. Bbox pre-filter via R-tree.
2. Type / subtype filter via a plain index.

Anything richer (per-field filters, geometry ops)
happens in Python on the hydrated JSON.  This keeps
the DB schema boring and future-proof — upstream
format changes just flow through ``props_json``
without a migration.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_ENV_VAR = "CESIUM_DATA_DIR"
DEFAULT_DIR = "data"
DB_FILE = "airspace.db"


def _data_dir() -> Path:
    base = os.environ.get(DB_ENV_VAR) or DEFAULT_DIR
    return Path(base)


def db_path() -> Path:
    return _data_dir() / DB_FILE


def db_exists() -> bool:
    return db_path().exists()


def _ensure_parent() -> None:
    _data_dir().mkdir(parents=True, exist_ok=True)


# Schema version — bump if the shape changes.  The
# ingest CLI will refuse to read an older DB and
# prompt the user to re-run ``python -m cesium_app.ingest``.
SCHEMA_VERSION = 7


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS airspace (
  rowid       INTEGER PRIMARY KEY,
  id          TEXT UNIQUE NOT NULL,
  type        TEXT NOT NULL,        -- CLASS | SUA
  subtype     TEXT,                 -- B/C/D/E or P/R/W/A/M/N/T
  bottom_ft   REAL,
  top_ft      REAL,
  props_json  TEXT NOT NULL,
  source      TEXT NOT NULL,
  fetched_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_airspace_type
  ON airspace(type, subtype);

CREATE VIRTUAL TABLE IF NOT EXISTS airspace_rtree
  USING rtree(
    id,                -- matches airspace.rowid
    min_lat, max_lat,
    min_lon, max_lon
  );

-- ─── FAA CIFP procedures (SIDs / STARs / IAPs) ──────
-- Two-table layout: ``procedure`` for the header
-- (airport, name, transition) plus the parsed raw
-- JSON; ``procedure_leg`` for each ARINC-424 leg in
-- order.  Phase 2 will add ``procedure_geom`` with
-- the pre-computed polyline (curved legs included).
CREATE TABLE IF NOT EXISTS procedure (
  rowid       INTEGER PRIMARY KEY,
  id          TEXT UNIQUE NOT NULL,    -- airport-type-name-transition
  airport     TEXT NOT NULL,           -- ICAO, e.g., KDFW
  proc_type   TEXT NOT NULL,           -- SID | STAR | IAP
  name        TEXT NOT NULL,           -- e.g., NEELY1, ILSZ10L
  transition  TEXT,                    -- runway or enroute fix
  raw_json    TEXT NOT NULL,
  source      TEXT NOT NULL,
  fetched_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_procedure_airport
  ON procedure(airport, proc_type);

CREATE TABLE IF NOT EXISTS procedure_leg (
  rowid         INTEGER PRIMARY KEY,
  procedure_id  TEXT NOT NULL
                  REFERENCES procedure(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  leg_type      TEXT NOT NULL,         -- TF / CF / RF / HM / ...
  fix_ident     TEXT,                  -- waypoint id at the leg endpoint
  raw_json      TEXT NOT NULL          -- full ARINC-424 leg fields
);

CREATE INDEX IF NOT EXISTS idx_leg_procedure
  ON procedure_leg(procedure_id, seq);

-- ─── Compiled procedure geometry (Phase 2) ──────────
-- One row per procedure with the densely-sampled
-- polyline (curved legs interpolated, MSL→HAE
-- conversion applied at compile time).  Bbox lives
-- alongside for filter-by-view queries.
CREATE TABLE IF NOT EXISTS procedure_geom (
  procedure_id  TEXT PRIMARY KEY
                  REFERENCES procedure(id) ON DELETE CASCADE,
  polyline_json TEXT NOT NULL,         -- [[lat, lon, alt_hae_m, alt_msl_ft], ...]
  fixes_json    TEXT NOT NULL,         -- per-fix annotations
  min_lat       REAL,
  max_lat       REAL,
  min_lon       REAL,
  max_lon       REAL
);

CREATE VIRTUAL TABLE IF NOT EXISTS procedure_geom_rtree
  USING rtree(
    id,                -- matches procedure_geom.rowid
    min_lat, max_lat,
    min_lon, max_lon
  );

-- ─── CIFP fix records (waypoints / navaids / runways)
-- Lookup table the leg compiler consults to resolve
-- fix names to coordinates.  Composite key on
-- (id, region) since names like ``BIRMS`` collide
-- worldwide; the ARINC region disambiguates.
CREATE TABLE IF NOT EXISTS navfix (
  rowid       INTEGER PRIMARY KEY,
  id          TEXT NOT NULL,           -- waypoint / navaid identifier
  region      TEXT NOT NULL,           -- ICAO region (e.g., K1, K2, K3)
  fix_type    TEXT NOT NULL,           -- WPT | VOR | NDB | RWY
  lat         REAL NOT NULL,
  lon         REAL NOT NULL,
  airport     TEXT,                    -- terminal-only fixes; NULL for enroute
  raw_json    TEXT,
  source      TEXT NOT NULL DEFAULT 'FAA',  -- FAA | EUROCONTROL | OPENAIP | OURAIRPORTS
  UNIQUE(id, region, fix_type, airport)
);

CREATE INDEX IF NOT EXISTS idx_navfix_source ON navfix(source);

CREATE INDEX IF NOT EXISTS idx_navfix_id ON navfix(id);

-- ─── Enroute airways (CIFP Section ER) ──────────────
-- One row per (airway, sequence-in-airway) pair.
-- ``airway_name`` repeats across rows; the full path
-- is reconstructed by ``SELECT * FROM airway_fix
-- WHERE airway_name=? ORDER BY seq``.  ``airway``
-- table holds the header (route type, min/max FL)
-- for the whole airway.
CREATE TABLE IF NOT EXISTS airway (
  name        TEXT PRIMARY KEY,        -- V23, J501, Q802, T278, UN862
  route_type  TEXT,                    -- O / H / R / L / etc.
  source      TEXT NOT NULL DEFAULT 'FAA',  -- FAA | EUROCONTROL | OPENAIP
  fetched_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS airway_fix (
  rowid        INTEGER PRIMARY KEY,
  airway_name  TEXT NOT NULL
                 REFERENCES airway(name) ON DELETE CASCADE,
  seq          INTEGER NOT NULL,
  fix_id       TEXT NOT NULL,
  fix_region   TEXT,
  lat          REAL NOT NULL,
  lon          REAL NOT NULL,
  min_fl       INTEGER,
  max_fl       INTEGER,
  source       TEXT NOT NULL DEFAULT 'FAA'
);

CREATE INDEX IF NOT EXISTS idx_airway_fix_airway
  ON airway_fix(airway_name, seq);
CREATE INDEX IF NOT EXISTS idx_airway_fix_fix
  ON airway_fix(fix_id);

-- ─── FAA Preferred Routes / TEC / NAR ───────────────
-- The authoritative FAA table of ATC-favored routes
-- between city pairs.  Route builder queries these
-- first before falling back to Dijkstra over the
-- airway graph — pilots almost always file these
-- for common origin/destination pairs.
CREATE TABLE IF NOT EXISTS preferred_route (
  rowid            INTEGER PRIMARY KEY,
  orig             TEXT NOT NULL,       -- 3-letter FAA (DFW)
  dest             TEXT NOT NULL,       -- 3-letter FAA (ATL)
  route_string     TEXT NOT NULL,
  route_type       TEXT,                -- TEC/H/L/NAR/SHD/HSD/SLD
  area             TEXT,
  altitude_ft      INTEGER,
  aircraft         TEXT,                -- TURBOJET / TURBOPROP / ''
  direction        TEXT,
  seq              INTEGER,
  dep_center       TEXT,                -- ARTCC (ZFW)
  arr_center       TEXT,
  fetched_at       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preferred_route_pair
  ON preferred_route(orig, dest);
CREATE INDEX IF NOT EXISTS idx_preferred_route_type
  ON preferred_route(route_type);

-- Per-source ingest tracking.  One row per logical
-- dataset (class_airspace, sua, runways, …).  The
-- ingest CLI writes this; the REST layer reads it so
-- the UI can surface cache freshness.
CREATE TABLE IF NOT EXISTS cache_source (
  source             TEXT PRIMARY KEY,
  label              TEXT NOT NULL,
  cadence_days       INTEGER,           -- AIRAC 28 or 56, NULL = live
  endpoint           TEXT,              -- URL we pulled from
  last_fetched_at    REAL,              -- unix seconds, success
  last_row_count     INTEGER,
  last_error         TEXT,
  last_error_at      REAL,
  next_refresh_at    REAL                -- hint: fetched_at + cadence
);
"""


def connect() -> sqlite3.Connection:
    """Open (and, if missing, initialize) the cache DB."""
    _ensure_parent()
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    # WAL keeps reads unblocked during ingest refresh.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    cur = conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'",
    )
    row = cur.fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        conn.commit()
    elif int(row["value"]) != SCHEMA_VERSION:
        raise RuntimeError(
            f"Cache DB schema version {row['value']} "
            f"!= expected {SCHEMA_VERSION}.  "
            f"Delete {db_path()} and re-run "
            f"`python -m cesium_app.ingest`."
        )
    return conn
