"""FAA data ingest jobs.

Pulls slow-changing aeronautical data from FAA
endpoints and writes it to the local SQLite cache.
Runs manually (``python -m cesium_app.ingest``) or
via cron/systemd on the AIRAC 28/56-day cadence.

See :mod:`cesium_app.store` for the cache schema.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from cesium_app.airspace import classes as classes_mod
from cesium_app.airspace import suas as suas_mod
from cesium_app.ingest.cifp import compiler as cifp_compiler
from cesium_app.ingest.cifp import download as cifp_download
from cesium_app.ingest.cifp import parser as cifp_parser
from cesium_app.ingest import preferred_routes as preferred_routes_mod
from cesium_app.store import (
    airspace_cache, airways_cache, graph_ingest,
    preferred_routes_cache, procedures_cache,
)

logger = logging.getLogger(__name__)


# Registry: every dataset we persist is declared here
# with its upstream update cadence.  Cadence drives
# the "next_refresh_at" computation shown in status
# output and the UI.  FAA aeronautical data follows
# the 28-day AIRAC cycle; controlled-airspace volumes
# change only at the 56-day sub-cycle boundary in
# practice, but 28 is the safe default.
SOURCE_CLASS = "class_airspace"
SOURCE_SUA = "sua"
SOURCE_PROCEDURES = procedures_cache.SOURCE_PROCEDURES
SOURCE_AIRWAYS = airways_cache.SOURCE_AIRWAYS
SOURCE_PREFERRED_ROUTES = (
    preferred_routes_cache.SOURCE_PREFERRED_ROUTES
)

_SOURCES: dict[str, dict] = {
    SOURCE_CLASS: {
        "label": "Class B/C/D/E Airspace",
        "cadence_days": 56,
        "endpoint": classes_mod._FEATURE_URL,
    },
    SOURCE_SUA: {
        "label": "Special Use Airspace",
        "cadence_days": 56,
        "endpoint": suas_mod._WFS_URL,
    },
    SOURCE_PROCEDURES: {
        "label": "CIFP Procedures (SID/STAR/IAP)",
        "cadence_days": 28,
        "endpoint": (
            "https://aeronav.faa.gov/Upload_313-d/cifp/"
        ),
    },
    SOURCE_AIRWAYS: {
        "label": "CIFP Enroute Airways",
        "cadence_days": 28,
        "endpoint": (
            "https://aeronav.faa.gov/Upload_313-d/cifp/"
        ),
    },
    SOURCE_PREFERRED_ROUTES: {
        "label": "FAA Preferred Routes / TEC / NAR",
        # FAA updates mid-cycle when TEC changes
        # land, so warn earlier than a full AIRAC.
        "cadence_days": 14,
        "endpoint": (
            "https://www.fly.faa.gov/rmt/data_file/"
            "prefroutes_db.csv"
        ),
    },
}


def register_all_sources() -> None:
    """Idempotent source registration.

    Declares every dataset to ``cache_source`` so the
    REST status endpoint always shows the full set
    (even entries we've never ingested — rendered as
    ``"(never fetched)"``).  Safe to call on app start
    and from the ingest CLI.
    """
    for src, meta in _SOURCES.items():
        airspace_cache.register_source(
            src,
            label=meta["label"],
            cadence_days=meta["cadence_days"],
            endpoint=meta["endpoint"],
        )


async def _refresh(
    source: str,
    fetcher,
) -> int:
    """Shared path: fetch → replace → stamp outcome."""
    register_all_sources()
    try:
        items = await fetcher()
    except Exception as exc:  # noqa: BLE001
        airspace_cache.record_fetch_error(source, str(exc))
        logger.exception("Ingest %s failed", source)
        raise
    n = await asyncio.to_thread(
        airspace_cache.replace_source, source, items,
    )
    airspace_cache.record_fetch_success(source, n)
    logger.info("Wrote %d %s rows.", n, source)
    return n


async def refresh_class_airspace() -> int:
    """Pull the full Class B/C/D/E set into the cache."""
    logger.info("Fetching class airspace from FAA…")
    return await _refresh(
        SOURCE_CLASS,
        classes_mod._fetch,  # type: ignore[attr-defined]
    )


async def refresh_suas() -> int:
    """Pull the full SUA set into the cache."""
    logger.info("Fetching SUAs from FAA…")
    return await _refresh(
        SOURCE_SUA,
        suas_mod._fetch,  # type: ignore[attr-defined]
    )


async def refresh_preferred_routes() -> int:
    """Download + parse the FAA PFR/TEC/NAR CSV."""
    register_all_sources()
    try:
        body = await preferred_routes_mod.fetch_csv()
        rows = list(preferred_routes_mod.parse_rows(body))
    except Exception as exc:  # noqa: BLE001
        airspace_cache.record_fetch_error(
            SOURCE_PREFERRED_ROUTES, str(exc),
        )
        logger.exception(
            "Preferred-routes ingest failed",
        )
        raise
    n = await asyncio.to_thread(
        preferred_routes_cache.replace_all, rows,
    )
    airspace_cache.record_fetch_success(
        SOURCE_PREFERRED_ROUTES, n,
    )
    logger.info(
        "Wrote %d preferred routes.", n,
    )
    return n


async def refresh_airways(
    cycle: str | None = None,
    *,
    force_download: bool = False,
) -> tuple[int, int]:
    """Parse the CIFP and load enroute airways.

    Depends on navfix already being present (the
    lookup in ``airways_cache.replace_all`` pulls
    lat/lon from there); normally called as part of
    :func:`refresh_procedures` rather than alone.
    Returns ``(n_airways, n_fixes)``.
    """
    register_all_sources()
    try:
        actual_cycle, path = await cifp_download.fetch_cifp(
            cycle, force=force_download,
        )
        logger.info(
            "Parsing airways from CIFP cycle %s",
            actual_cycle,
        )
        rows = list(cifp_parser.iter_airway_lines(path))
    except Exception as exc:  # noqa: BLE001
        airspace_cache.record_fetch_error(
            SOURCE_AIRWAYS, str(exc),
        )
        logger.exception("Airways ingest failed")
        raise
    n_air, n_fix = await asyncio.to_thread(
        airways_cache.replace_all, rows,
    )
    airspace_cache.record_fetch_success(
        SOURCE_AIRWAYS, n_air,
    )
    logger.info(
        "Wrote %d airways (%d fixes) from CIFP %s.",
        n_air, n_fix, actual_cycle,
    )
    return n_air, n_fix


async def refresh_procedures(
    cycle: str | None = None,
    *,
    force_download: bool = False,
) -> tuple[int, int, int, int]:
    """Download + parse + compile the FAA CIFP.

    Returns ``(n_procedures, n_legs, n_navfixes,
    n_geom)``.  The CIFP archive is large (~80 MB
    compressed); we cache the unzipped FAACIFP18
    under ``data/cifp/`` and only re-download when
    the cycle id changes (or when
    ``force_download=True``).

    Pipeline (Phase 2):

    1. Download + extract the CIFP archive.
    2. Parse + load fix records (waypoints, navaids,
       NDBs, runways) into ``navfix`` — leg compiler
       uses this to resolve ``fix_ident`` references.
    3. Parse + load procedure leg records into
       ``procedure`` + ``procedure_leg``.
    4. Compile every procedure's legs into a polyline
       using :mod:`cifp.compiler`; write to
       ``procedure_geom`` (curved legs included,
       MSL→HAE conversion applied).
    """
    register_all_sources()
    try:
        actual_cycle, path = await cifp_download.fetch_cifp(
            cycle, force=force_download,
        )
        logger.info(
            "Parsing CIFP cycle %s from %s",
            actual_cycle, path,
        )
        # Step 2: navfixes (must precede compilation).
        n_fix = await asyncio.to_thread(
            procedures_cache.replace_navfixes,
            cifp_parser.iter_fix_lines(path),
        )
        logger.info("Loaded %d navfixes.", n_fix)
        # Step 3: procedure legs.
        legs = cifp_parser.iter_leg_lines(path)
        procs = list(cifp_parser.group_procedures(legs))
    except Exception as exc:  # noqa: BLE001
        airspace_cache.record_fetch_error(
            SOURCE_PROCEDURES, str(exc),
        )
        logger.exception("CIFP ingest failed")
        raise
    n_proc, n_legs = await asyncio.to_thread(
        procedures_cache.replace_all, procs,
    )
    # Step 4: compile geometry.
    logger.info("Compiling procedure geometry…")
    n_geom = await asyncio.to_thread(
        procedures_cache.replace_geom,
        cifp_compiler.compile_all(procs),
    )
    airspace_cache.record_fetch_success(
        SOURCE_PROCEDURES, n_proc,
    )
    logger.info(
        "Wrote %d procedures (%d legs, %d compiled) "
        "from CIFP %s.",
        n_proc, n_legs, n_geom, actual_cycle,
    )
    # Step 5: airways (shares the same file + navfix).
    logger.info("Ingesting airways…")
    n_air_rows = list(
        cifp_parser.iter_airway_lines(path),
    )
    n_airways, n_air_fix = await asyncio.to_thread(
        airways_cache.replace_all, n_air_rows,
    )
    airspace_cache.record_fetch_success(
        SOURCE_AIRWAYS, n_airways,
    )
    logger.info(
        "Wrote %d airways (%d fix rows).",
        n_airways, n_air_fix,
    )
    # Step 6: rebuild Neo4j graph from SQLite
    # source-of-truth.  Runs in-thread because
    # graph_ingest handles its own batching and the
    # async event loop shouldn't starve during the
    # upload (~10-30 seconds).
    try:
        logger.info("Rebuilding Neo4j graph…")
        graph_stats = await asyncio.to_thread(
            graph_ingest.rebuild,
        )
        logger.info(
            "Neo4j rebuilt: %s", graph_stats,
        )
    except Exception:  # noqa: BLE001
        # Don't fail the whole ingest if Neo4j is
        # unavailable — the SQLite layer is still the
        # canonical store.  Log and move on.
        logger.exception(
            "Neo4j rebuild failed; graph not refreshed",
        )
    return n_proc, n_legs, n_fix, n_geom


async def refresh_all() -> dict[str, int]:
    """Refresh every ingestible dataset.

    Runs them concurrently — upstream servers are
    independent, no reason to serialize.  CIFP
    procedures are large enough that we report the
    count separately.
    """
    # Run serially: SQLite allows only one writer at
    # a time and these all target the same DB file.
    # Network fetches are still async within each
    # step; the serialization is only on write
    # transactions, and since each takes seconds-to-
    # minutes we don't lose meaningful overlap.
    n_class = await refresh_class_airspace()
    n_sua = await refresh_suas()
    proc_counts = await refresh_procedures()
    n_preferred = await refresh_preferred_routes()
    return {
        SOURCE_CLASS: n_class,
        SOURCE_SUA: n_sua,
        # ``proc_counts`` is (n_proc, n_legs,
        # n_navfixes, n_geom).  Surface the procedure
        # row count for the summary print.
        SOURCE_PROCEDURES: proc_counts[0],
        SOURCE_PREFERRED_ROUTES: n_preferred,
    }


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
