"""DDR2 file format parsers.

Each EUROCONTROL DDR2 dataset file has its own
quirks — most are CSV-ish but with column counts
that vary by data type (point vs route vs
airspace).  Parsers are deliberately tolerant:
unknown columns are passed through in
``raw_dict`` so we can extend without re-parsing.

Reference: DDR2 Reference Manual, sections on
NEST data formats.
"""
from __future__ import annotations

import csv
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── Significant points (waypoints + navaids) ──────

def parse_points(path: Path) -> Iterator[dict]:
    """Yield navfix-shape dicts from DDR2 points.csv.

    Expected columns (DDR2 Reference Manual §2.3):

    - ``POINT_ID`` — 5-letter waypoint identifier
    - ``LAT_DEC`` — decimal latitude
    - ``LON_DEC`` — decimal longitude
    - ``POINT_TYPE`` — DESIGNATED / VOR / NDB / DME / ...
    - ``ICAO_CODE`` — 2-letter region

    DDR2 ships these in semicolon-delimited ASCII.
    """
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            try:
                lat = float(row.get("LAT_DEC") or "")
                lon = float(row.get("LON_DEC") or "")
            except ValueError:
                continue
            ptype = (row.get("POINT_TYPE") or "").upper()
            fix_type = _map_point_type(ptype)
            yield {
                "id": (row.get("POINT_ID") or "").strip(),
                "region": (row.get("ICAO_CODE") or "").strip(),
                "fix_type": fix_type,
                "lat": lat,
                "lon": lon,
                "airport": None,
                "raw": dict(row),
            }


def _map_point_type(ddr2_type: str) -> str:
    """Map DDR2 POINT_TYPE → our ``fix_type`` enum."""
    if ddr2_type in ("VOR", "DVOR", "VORTAC"):
        return "VOR"
    if ddr2_type in ("NDB", "LOCATOR"):
        return "NDB"
    if ddr2_type == "DME":
        return "DME"
    # DESIGNATED / FIX / RNAV waypoints all collapse.
    return "WPT"


# ─── Airways (routes) ──────────────────────────────

def parse_routes(path: Path) -> Iterator[dict]:
    """Yield airway-fix-shape dicts from DDR2 routes.csv.

    Expected columns:

    - ``ROUTE_ID`` — airway designator (UN862, UA34, ...)
    - ``SEQ`` — fix sequence within the route
    - ``POINT_ID`` — fix referenced
    - ``ICAO_CODE`` — fix region
    - ``ROUTE_TYPE`` — UPPER / LOWER / RNAV
    - ``FL_MIN``, ``FL_MAX`` — altitude bounds
    """
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            try:
                seq = int(row.get("SEQ") or "")
            except ValueError:
                continue
            try:
                min_fl = int(row.get("FL_MIN") or "0") or None
                max_fl = int(row.get("FL_MAX") or "0") or None
            except ValueError:
                min_fl = None
                max_fl = None
            yield {
                "airway_name": (row.get("ROUTE_ID") or "").strip(),
                "seq": seq,
                "fix_id": (row.get("POINT_ID") or "").strip(),
                "fix_region": (row.get("ICAO_CODE") or "").strip(),
                "route_type": (row.get("ROUTE_TYPE") or "").strip(),
                "min_fl_ft": min_fl,
                "max_fl_ft": max_fl,
                "raw": dict(row),
            }


# ─── Airports ──────────────────────────────────────

def parse_airports(path: Path) -> Iterator[dict]:
    """Yield navfix-shape APT-type dicts from DDR2
    airports.csv."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            try:
                lat = float(row.get("LAT_DEC") or "")
                lon = float(row.get("LON_DEC") or "")
            except ValueError:
                continue
            icao = (row.get("ICAO_ID") or "").strip()
            if not icao:
                continue
            yield {
                "id": icao,
                "region": icao[:2],
                "fix_type": "APT",
                "lat": lat,
                "lon": lon,
                "airport": icao,
                "raw": dict(row),
            }
