"""CLI entry point: ``python -m cesium_app.ingest``.

Usage::

    python -m cesium_app.ingest              # refresh all
    python -m cesium_app.ingest classes      # just class airspace
    python -m cesium_app.ingest suas         # just SUAs
    python -m cesium_app.ingest status       # show cache status
"""
from __future__ import annotations

import asyncio
import sys

from cesium_app.ingest import (
    _configure_logging,
    refresh_airways,
    refresh_all,
    refresh_class_airspace,
    refresh_preferred_routes,
    refresh_procedures,
    refresh_suas,
    register_all_sources,
)
from cesium_app.store import airspace_cache, db


def _fmt_age(sec: float | None) -> str:
    if sec is None:
        return "never fetched"
    if sec < 3600:
        return f"{sec / 60:.0f}m ago"
    if sec < 86400:
        return f"{sec / 3600:.1f}h ago"
    return f"{sec / 86400:.1f}d ago"


def _status() -> int:
    print(f"Cache: {db.db_path()}")
    print(f"Exists: {db.db_exists()}")
    register_all_sources()
    sources = airspace_cache.list_sources()
    if not sources:
        print("  (no sources registered)")
        return 0
    print()
    print(
        f"  {'source':<18s}  {'rows':>6s}  {'cadence':>8s}  "
        f"{'age':>12s}  {'status':<10s}"
    )
    print(f"  {'-' * 18}  {'-' * 6}  {'-' * 8}  "
          f"{'-' * 12}  {'-' * 10}")
    for s in sources:
        rows = (
            f"{s['last_row_count']:>6d}"
            if s["last_row_count"] is not None
            else "     -"
        )
        cadence = (
            f"{s['cadence_days']:>4d}d"
            if s["cadence_days"] is not None
            else "    -"
        )
        status = (
            "ERROR"
            if s["last_error"]
            else "stale"
            if s["stale"]
            else "fresh"
            if s["last_fetched_at"]
            else "empty"
        )
        print(
            f"  {s['source']:<18s}  {rows}  "
            f"{cadence:>8s}  "
            f"{_fmt_age(s['age_sec']):>12s}  "
            f"{status:<10s}"
        )
        if s["last_error"]:
            print(f"    └─ error: {s['last_error']}")
    return 0


def main(argv: list[str]) -> int:
    _configure_logging()
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd == "status":
        return _status()
    if cmd == "classes":
        asyncio.run(refresh_class_airspace())
    elif cmd == "suas":
        asyncio.run(refresh_suas())
    elif cmd == "procedures":
        asyncio.run(refresh_procedures())
    elif cmd == "airways":
        asyncio.run(refresh_airways())
    elif cmd in ("preferred_routes", "preferred"):
        asyncio.run(refresh_preferred_routes())
    elif cmd in ("aircraft_db", "aircraft", "registry"):
        import asyncio as _aio
        from cesium_app.ingest import aircraft_db
        path = _aio.run(aircraft_db.download())
        n = aircraft_db.load(path)
        print(f"Aircraft registry: {n} records loaded")
    elif cmd == "graph":
        # Graph rebuild from existing SQLite source —
        # no CIFP re-download, no re-compile.  Useful
        # for schema changes or Neo4j wipe recovery.
        from cesium_app.store import graph_ingest
        stats = graph_ingest.rebuild()
        print("Neo4j rebuild:", stats)
    elif cmd == "ddr2":
        # EUROCONTROL DDR2 ingest — reads files
        # from data/ddr2/ (manual download).  See
        # data/ddr2/README.md for setup.
        from cesium_app.ingest.ddr2 import cli as ddr2_cli
        stats = ddr2_cli.run()
        import json as _json
        print(_json.dumps(stats, indent=2))
    elif cmd in ("all", "refresh"):
        asyncio.run(refresh_all())
    else:
        print(
            f"Unknown command: {cmd!r}.  Use one of: "
            f"all, classes, suas, procedures, airways, "
            f"graph, status.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
