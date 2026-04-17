"""FAA CIFP (Coded Instrument Flight Procedures) ingest.

CIFP is the FAA's free monthly release of every US
SID, STAR, and Instrument Approach Procedure encoded
as ARINC-424 fixed-column text records.  Refreshed
on the AIRAC 28-day cycle.

Distribution: ``aeronav.faa.gov/Upload_313-d/cifp/``
as ``CIFP_<YYNN>.zip`` where YYNN is the AIRAC cycle
identifier (e.g., ``CIFP_2604.zip`` for the 4th
cycle of 2026).

This package is split into:

* :mod:`download` — fetch + unzip the CIFP archive,
  with cycle auto-detection.
* :mod:`parser` — line-oriented ARINC-424 parser that
  yields procedure header + leg records.
* :mod:`models` — typed records the parser produces.

Phase 1 (current): download → parse → store raw
records keyed by procedure.  Phase 2 will add the
leg-to-polyline compiler so curved legs (RF, HM,
HF, PI, …) render correctly without per-client math.
"""
from __future__ import annotations

from datetime import date, timedelta

# AIRAC cycle anchor: 2024-01-25 was AIRAC 2401
# (verified against FAA/Eurocontrol AIRAC calendars).
# Cycles run 28 days each, with the cycle index
# resetting to 01 at the first cycle of each calendar
# year — that's why we walk forward instead of using
# a closed form.
_AIRAC_EPOCH = date(2024, 1, 25)
_AIRAC_EPOCH_NUM = (24, 1)
_CYCLE_DAYS = 28


def airac_for(
    today: date | None = None,
) -> tuple[str, date]:
    """Return ``(YYNN cycle, effective date)`` for ``today``.

    For 2026-04-14 returns ``("2603", date(2026, 3, 19))``
    — the currently effective cycle.  The FAA CIFP
    download URL uses the YYMMDD form of the
    effective date, so callers consume the date
    directly.

    Walks the cycle list forward from the epoch —
    clearer than a closed form because cycles-per-
    year flexes (12 or 13).
    """
    if today is None:
        today = date.today()
    yy, nn = _AIRAC_EPOCH_NUM
    eff = _AIRAC_EPOCH
    while True:
        nxt = eff + timedelta(days=_CYCLE_DAYS)
        if today < nxt:
            return f"{yy:02d}{nn:02d}", eff
        if nxt.year != eff.year:
            yy = nxt.year - 2000
            nn = 1
        else:
            nn += 1
        eff = nxt


def airac_cycle(today: date | None = None) -> str:
    """Return just the cycle id; convenience wrapper."""
    return airac_for(today)[0]
