"""FAA Preferred Routes / TEC / NAR ingest.

Downloads the CSV bulk table from
``fly.faa.gov/rmt/data_file/prefroutes_db.csv`` and
writes every row into the ``preferred_route`` table.

Refreshes on the 28-day AIRAC cycle in theory;
in practice the FAA updates this table more often
(weekly-ish) as TEC revisions trickle in, so we
treat it as a 14-day cadence for staleness warnings.
"""
from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterator

import httpx

logger = logging.getLogger(__name__)

_PREFROUTES_URL = (
    "https://www.fly.faa.gov/rmt/data_file/prefroutes_db.csv"
)
_USER_AGENT = "cesium-bluesky/0.1 (research-sim)"
_TIMEOUT_SEC = 60.0


async def fetch_csv() -> str:
    """Download the CSV and return the decoded body."""
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SEC,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    ) as client:
        res = await client.get(_PREFROUTES_URL)
        res.raise_for_status()
        # The file is BOM-prefixed in practice; decode
        # as utf-8-sig to strip it cleanly.
        return res.content.decode("utf-8-sig")


def _parse_altitude(raw: str) -> int | None:
    """Route CSV altitude column is numeric (feet)
    or blank.  Some rows have free text — be lenient."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_rows(body: str) -> Iterator[dict]:
    """Yield one dict per CSV row, matching the
    ``preferred_route`` table's column shape."""
    reader = csv.reader(io.StringIO(body))
    header = next(reader, None)
    if header is None:
        return
    # Column layout as of 2026-04 — anchor by index
    # since the FAA occasionally shifts columns.
    # Row: Orig, Route String, Dest, H1, H2, H3,
    #      Type, Area, Altitude, Aircraft, Direction,
    #      Seq, DCNTR, ACNTR
    for row in reader:
        if len(row) < 14:
            continue
        orig = row[0].strip().upper()
        route_string = row[1].strip()
        dest = row[2].strip().upper()
        if not orig or not dest:
            continue
        seq_raw = row[11].strip()
        try:
            seq = int(seq_raw) if seq_raw else None
        except ValueError:
            seq = None
        yield {
            "orig": orig,
            "dest": dest,
            "route_string": route_string,
            "route_type": (row[6] or "").strip() or None,
            "area": (row[7] or "").strip() or None,
            "altitude_ft": _parse_altitude(row[8]),
            "aircraft": (row[9] or "").strip() or None,
            "direction": (row[10] or "").strip() or None,
            "seq": seq,
            "dep_center": (row[12] or "").strip() or None,
            "arr_center": (row[13] or "").strip() or None,
        }
