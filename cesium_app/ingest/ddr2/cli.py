"""``python -m cesium_app.ingest ddr2`` entry point.

Walks ``data/ddr2/`` for known DDR2 file names
(case-insensitive), parses, loads.  Reports a
summary of inserts vs FAA-wins skips per file.
"""
from __future__ import annotations

import logging
from pathlib import Path

from cesium_app.ingest.ddr2 import loader, parser
from cesium_app.store.db import _data_dir

logger = logging.getLogger(__name__)


def _find(stem: str, dir_: Path) -> Path | None:
    """Case-insensitive lookup; allow .csv or .txt."""
    if not dir_.is_dir():
        return None
    candidates = []
    for p in dir_.iterdir():
        n = p.name.lower()
        if n.startswith(stem.lower()) and (
            n.endswith(".csv") or n.endswith(".txt")
        ):
            candidates.append(p)
    return candidates[0] if candidates else None


def run() -> dict:
    ddr_dir = _data_dir() / "ddr2"
    if not ddr_dir.exists():
        raise RuntimeError(
            f"DDR2 data dir missing: {ddr_dir}.  "
            f"See {ddr_dir}/README.md for the "
            f"manual download flow."
        )
    stats: dict = {}

    # 1) Points first — airways depend on these for
    # coordinate resolution.
    pts = _find("point", ddr_dir)
    if pts is None:
        # Try plural 'points'.
        pts = _find("points", ddr_dir)
    if pts is not None:
        rows = list(parser.parse_points(pts))
        ins, skip = loader.load_navfixes(rows)
        stats["points"] = {
            "file": pts.name, "parsed": len(rows),
            "inserted": ins, "skipped_faa_wins": skip,
        }
        logger.info(
            "Points: %d parsed, %d inserted, "
            "%d skipped (FAA wins)",
            len(rows), ins, skip,
        )
    else:
        stats["points"] = {"file": None, "note": "missing"}

    # 2) Airports.
    apt = _find("airport", ddr_dir)
    if apt is not None:
        rows = list(parser.parse_airports(apt))
        ins, skip = loader.load_navfixes(rows)
        stats["airports"] = {
            "file": apt.name, "parsed": len(rows),
            "inserted": ins, "skipped_faa_wins": skip,
        }
        logger.info(
            "Airports: %d parsed, %d inserted, "
            "%d skipped (FAA wins)",
            len(rows), ins, skip,
        )
    else:
        stats["airports"] = {"file": None, "note": "missing"}

    # 3) Routes (airways).
    rt = _find("route", ddr_dir) or _find("routes", ddr_dir)
    if rt is not None:
        rows = list(parser.parse_routes(rt))
        n_air, n_fix = loader.load_airways(rows)
        stats["routes"] = {
            "file": rt.name, "parsed_rows": len(rows),
            "airways_inserted": n_air,
            "fixes_inserted": n_fix,
        }
        logger.info(
            "Routes: %d rows → %d airways "
            "(%d fix associations)",
            len(rows), n_air, n_fix,
        )
    else:
        stats["routes"] = {"file": None, "note": "missing"}

    return stats
