"""Performance Based Navigation (PBN) model.

Determines which procedures an aircraft is
allowed to fly based on its avionics equipage.
Without this gating, the route builder could
assign an RNP AR approach (requiring curved-path
GNSS with integrity monitoring) to a C172 that
only has a basic GPS.

The PBN hierarchy (strictest → loosest):

    RNP AR  (0.10 NM)  — curved RF legs + monitoring
    RNP 0.3 (0.30 NM)  — RNAV GPS approach standard
    RNP 1   (1.00 NM)  — terminal (SID/STAR)
    RNAV 1  (1.00 NM)  — terminal (no monitoring)
    RNAV 5  (5.00 NM)  — enroute (basic GPS / VOR-DME)
    NONE    (∞)         — no PBN capability (NDB only)

An aircraft with RNP AR capability can fly all
procedures; one with only RNAV 5 can fly enroute
airways but not precision approaches.

CIFP encodes the RNP requirement per leg as a
3-digit hundredths-of-NM value (``010`` = 0.10 NM,
``031`` = 0.31 NM, ``100`` = 1.00 NM, etc.).  A
procedure's overall PBN requirement is the
*tightest* (smallest) RNP across all its legs.

Sources observed in CIFP 2603:
    0.10 NM  34,445 legs  (RNP AR — RF/curved legs)
    0.31 NM  11,211 legs  (non-precision approach)
    0.20 NM     874 legs  (RNP AR variant)
    0.51 NM     518 legs  (transitional)
"""
from __future__ import annotations

import json
import logging
from enum import IntEnum

from cesium_app.store.db import connect

logger = logging.getLogger(__name__)


class PbnSpec(IntEnum):
    """PBN capability levels, ordered strictest→loosest.

    Integer value = hundredths of NM for the
    accuracy guarantee.  Higher number = looser.
    ``NONE`` uses 99999 as a sentinel for "no PBN".
    """
    RNP_AR = 10       # 0.10 NM — curved (RF legs)
    RNP_02 = 20       # 0.20 NM — tight RNP AR variant
    RNP_03 = 30       # 0.30 NM — RNAV GPS approach
    RNP_1  = 100      # 1.00 NM — terminal with monitoring
    RNAV_1 = 101      # 1.00 NM — terminal (no monitoring)
    RNAV_2 = 200      # 2.00 NM — enroute RNAV
    RNAV_5 = 500      # 5.00 NM — basic enroute
    NONE   = 99999    # No PBN capability


def pbn_label(spec: PbnSpec) -> str:
    _LABELS = {
        PbnSpec.RNP_AR: "RNP AR (0.10 NM)",
        PbnSpec.RNP_02: "RNP 0.2",
        PbnSpec.RNP_03: "RNP 0.3",
        PbnSpec.RNP_1:  "RNP 1",
        PbnSpec.RNAV_1: "RNAV 1",
        PbnSpec.RNAV_2: "RNAV 2",
        PbnSpec.RNAV_5: "RNAV 5",
        PbnSpec.NONE:   "No PBN",
    }
    return _LABELS.get(spec, f"RNP {spec / 100:.2f}")


def rnp_hundredths_to_spec(val: int) -> PbnSpec:
    """Map a CIFP hundredths-of-NM value to the
    nearest PbnSpec bucket.

    CIFP values don't always land on clean spec
    boundaries (``031`` = 0.31, ``051`` = 0.51);
    bucket to the next-stricter named spec.
    """
    if val <= 10:
        return PbnSpec.RNP_AR
    if val <= 20:
        return PbnSpec.RNP_02
    if val <= 30:
        return PbnSpec.RNP_03
    if val <= 100:
        return PbnSpec.RNP_1
    if val <= 200:
        return PbnSpec.RNAV_2
    if val <= 500:
        return PbnSpec.RNAV_5
    return PbnSpec.NONE


def can_fly(
    aircraft_pbn: PbnSpec,
    procedure_pbn: PbnSpec,
) -> bool:
    """True if the aircraft's PBN capability is at
    least as tight as the procedure's requirement.

    Lower numeric value = tighter accuracy =
    more capable.  An RNP AR aircraft (10) can fly
    anything; an RNAV 5 aircraft (500) can only fly
    procedures requiring ≤500.
    """
    return aircraft_pbn <= procedure_pbn


# ─── Procedure PBN requirement lookup ───────────────

def procedure_pbn_requirement(
    procedure_id: str,
) -> PbnSpec:
    """The tightest RNP value across all legs of a
    procedure, bucketed to a PbnSpec.

    Reads the ``rnp`` field from ``procedure_leg``
    rows.  If no leg has an RNP value, returns
    ``RNAV_5`` (the loosest named spec — effectively
    "any GPS-equipped aircraft can fly this").
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT raw_json FROM procedure_leg "
            "WHERE procedure_id = ?",
            (procedure_id,),
        ).fetchall()
    finally:
        conn.close()
    tightest = PbnSpec.RNAV_5
    for row in rows:
        leg = json.loads(row[0])
        rnp_raw = (leg.get("rnp") or "").strip()
        if not rnp_raw:
            continue
        try:
            val = int(rnp_raw)
        except ValueError:
            continue
        spec = rnp_hundredths_to_spec(val)
        if spec < tightest:
            tightest = spec
    return tightest


# ─── Default aircraft PBN by type category ──────────

# Broad defaults when we don't have per-tail equipage
# from the registration DB.  Conservative: assume the
# baseline for the category.  Override per-aircraft
# when the registration / CNS dashboard data lands.
_TYPE_PBN_DEFAULTS: dict[str, PbnSpec] = {
    # Modern airliners — RNP AR capable
    "B738": PbnSpec.RNP_AR,
    "B739": PbnSpec.RNP_AR,
    "B38M": PbnSpec.RNP_AR,
    "B39M": PbnSpec.RNP_AR,
    "A320": PbnSpec.RNP_AR,
    "A321": PbnSpec.RNP_AR,
    "A20N": PbnSpec.RNP_AR,
    "A21N": PbnSpec.RNP_AR,
    "B789": PbnSpec.RNP_AR,
    "B77W": PbnSpec.RNP_AR,
    "A333": PbnSpec.RNP_AR,
    "B744": PbnSpec.RNP_1,     # older 747s may lack AR
    "B752": PbnSpec.RNP_1,
    "B763": PbnSpec.RNP_1,
    # Regional jets
    "E170": PbnSpec.RNP_AR,
    "E175": PbnSpec.RNP_AR,
    "CRJ9": PbnSpec.RNP_1,
    "CRJ7": PbnSpec.RNP_1,
    # Turboprops
    "AT75": PbnSpec.RNAV_1,
    "DH8D": PbnSpec.RNAV_1,
    "C208": PbnSpec.RNAV_1,
    # GA piston — IFR-equipped with basic GPS
    "C172": PbnSpec.RNP_03,    # with WAAS GPS
    "C182": PbnSpec.RNP_03,
    "SR22": PbnSpec.RNP_03,    # Cirrus: G1000 standard
    "PA28": PbnSpec.RNAV_1,
    "BE58": PbnSpec.RNAV_1,
    # Autonomous platforms — modern avionics
    "C208": PbnSpec.RNP_AR,    # Reliable Robotics Caravan
}

# Category fallbacks when type isn't in the table
_CATEGORY_PBN_DEFAULTS: dict[str, PbnSpec] = {
    "JET": PbnSpec.RNP_1,
    "TURBOPROP": PbnSpec.RNAV_1,
    "PISTON": PbnSpec.RNAV_5,
    "HELO": PbnSpec.RNAV_5,
}


def aircraft_pbn(
    icao_type: str,
    category: str | None = None,
) -> PbnSpec:
    """Best-guess PBN capability for an aircraft type.

    Uses the type-specific table first, then the
    category fallback.  Override per-tail when
    registration / CNS data is available.
    """
    t = icao_type.upper()
    if t in _TYPE_PBN_DEFAULTS:
        return _TYPE_PBN_DEFAULTS[t]
    if category:
        c = category.upper()
        if c in _CATEGORY_PBN_DEFAULTS:
            return _CATEGORY_PBN_DEFAULTS[c]
    return PbnSpec.RNAV_5


# ─── Convenience: filter procedures by aircraft ─────

def filter_procedures_by_pbn(
    procedures: list[dict],
    ac_pbn: PbnSpec,
) -> list[dict]:
    """Return only procedures the aircraft can fly.

    Each ``procedure`` dict must have an ``id`` key;
    the PBN requirement is looked up from the DB.
    """
    return [
        p for p in procedures
        if can_fly(ac_pbn, procedure_pbn_requirement(p["id"]))
    ]
