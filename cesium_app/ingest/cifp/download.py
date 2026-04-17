"""CIFP archive downloader.

Fetches ``CIFP_<YYNN>.zip`` from the FAA's
aeronav distribution and unzips ``FAACIFP18`` into a
local data directory.  Caches the unzipped file on
disk so re-runs of the parser don't re-download
~80 MB unnecessarily.
"""
from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, timedelta
from pathlib import Path

import httpx

from cesium_app.ingest.cifp import airac_for
from cesium_app.store.db import _data_dir

logger = logging.getLogger(__name__)

_BASE_URL = "https://aeronav.faa.gov/Upload_313-d/cifp"
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
_INNER_FILE = "FAACIFP18"
DOWNLOAD_TIMEOUT_SEC = 600.0


def cifp_dir() -> Path:
    """Where downloaded + extracted CIFP files live."""
    p = _data_dir() / "cifp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cached_path(cycle: str) -> Path:
    return cifp_dir() / f"FAACIFP18_{cycle}"


async def fetch_cifp(
    cycle: str | None = None,
    *,
    force: bool = False,
) -> tuple[str, Path]:
    """Download + unzip CIFP for ``cycle``.

    The FAA CIFP archive is named
    ``CIFP_<YYMMDD>.zip`` where YYMMDD is the AIRAC
    effective date.  We pass ``today`` to
    :func:`airac_for` to get the active cycle, then
    fall back one cycle if FAA hasn't posted the
    current one yet.

    Returns ``(cycle_id, path_to_FAACIFP18)``.
    """
    if cycle is None:
        # Tuple of (cycle_id, effective_date) candidates,
        # current first then one cycle back.
        cycle_id, eff = airac_for()
        candidates: list[tuple[str, date]] = [
            (cycle_id, eff),
            airac_for(eff - timedelta(days=1)),
        ]
    else:
        # Caller knows the cycle but not necessarily
        # the effective date — derive it.
        eff = _effective_date_for_cycle(cycle)
        candidates = [(cycle, eff)]

    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        timeout=DOWNLOAD_TIMEOUT_SEC, headers=headers,
        follow_redirects=True,
    ) as client:
        for cand_cycle, cand_eff in candidates:
            local = cached_path(cand_cycle)
            if local.exists() and not force:
                logger.info(
                    "CIFP %s already cached at %s",
                    cand_cycle, local,
                )
                return cand_cycle, local
            url = (
                f"{_BASE_URL}/CIFP_"
                f"{cand_eff.strftime('%y%m%d')}.zip"
            )
            logger.info("Downloading %s", url)
            try:
                res = await client.get(url)
                res.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning(
                        "CIFP %s (%s) not yet published; "
                        "trying previous cycle.",
                        cand_cycle, url,
                    )
                    continue
                raise
            zf = zipfile.ZipFile(io.BytesIO(res.content))
            inner = next(
                (
                    n for n in zf.namelist()
                    if n.upper().endswith(
                        _INNER_FILE.upper()
                    )
                ),
                None,
            )
            if inner is None:
                raise RuntimeError(
                    f"CIFP zip {url} missing "
                    f"{_INNER_FILE} entry; "
                    f"contents: {zf.namelist()[:5]}…"
                )
            with zf.open(inner) as src, local.open("wb") as dst:
                dst.write(src.read())
            logger.info(
                "Wrote %s (%.1f MB)",
                local, local.stat().st_size / 1e6,
            )
            return cand_cycle, local
    cycle_strs = [c for c, _ in candidates]
    raise RuntimeError(
        f"No CIFP archive available for cycles "
        f"{cycle_strs} on {_BASE_URL}"
    )


def _effective_date_for_cycle(cycle: str) -> date:
    """Find the effective date for a YYNN cycle id."""
    # Walk forward one day at a time would be slow;
    # just step by 28d from epoch through cycles
    # until we find the matching id.
    yy = int(cycle[:2])
    nn = int(cycle[2:])
    # Start at Jan 1 of the cycle's year minus 1 to
    # be sure we sweep into it from an earlier point.
    probe = date(2000 + yy, 1, 1) - timedelta(days=14)
    while True:
        cid, eff = airac_for(probe)
        if cid == cycle:
            return eff
        probe = eff + timedelta(days=28)
        # Safety bail — if we've walked years past
        # the requested cycle, give up.
        if probe.year > 2000 + yy + 1:
            raise ValueError(
                f"Cycle {cycle} not reachable "
                f"from epoch."
            )
