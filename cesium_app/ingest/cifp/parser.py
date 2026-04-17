"""ARINC-424 record parser for FAA CIFP.

CIFP files use ARINC Specification 424 fixed-column
text records, 132 characters per line.  Procedure
records live in section ``P`` with subsection
letters ``D`` (SID), ``E`` (STAR), or ``F`` (Approach).

This parser is deliberately narrow — it only reads
the columns we need for Phase 1 (procedure grouping
+ leg sequence) and Phase 2 (leg-to-polyline
compilation).  Every parsed leg keeps its raw line
in the output so we can extend the parser without
re-downloading.

Spec reference: ARINC 424-21, "Standards for Navigation
System Database Records", procedure leg layout
(SIDS / STARS / Approach Procedures).  Column
numbers in this module are 1-based per the spec;
Python slices subtract 1.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


_SECTION_TO_TYPE = {"D": "SID", "E": "STAR", "F": "IAP"}


def _opt_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_leg_line(line: str) -> dict | None:
    """Parse one ARINC-424 line; None if not a procedure leg.

    Captures every field a downstream leg compiler
    might need — turn direction, recommended NAVAID,
    arc radius/center, altitude/speed/vertical-angle
    constraints — even though Phase 1 stores them as
    raw strings.
    """
    if len(line) < 50 or line[0] != "S":
        return None
    if line[4] != "P":
        return None
    section = line[12]
    proc_type = _SECTION_TO_TYPE.get(section)
    if proc_type is None:
        return None

    # Skip continuation records — they carry auxiliary
    # data (extra speed/alt constraints, equipment
    # notes) that the current compiler doesn't use
    # and would be double-counted if grouped as their
    # own legs.  Primary records are cont_rec_no
    # '0' or '1'.
    cont = line[38:39]
    if cont not in ("0", "1"):
        return None

    # Column layout for SID / STAR / IAP legs
    # (ARINC 424-15, verified empirically against
    # CIFP 2603).  Key altitude/speed offsets:
    #   col 83:      alt description (+, -, B, @, …)
    #   col 85-89:   altitude 1 (ft, zero-padded)
    #   col 90-94:   altitude 2 (optional)
    #   col 95-99:   transition altitude
    #   col 100-102: speed limit (kt)
    #   col 103-106: vertical angle (deg × 100)
    return {
        "airport":       line[6:10].strip(),
        "region":        line[10:12].strip(),
        "proc_type":     proc_type,
        "name":          line[13:19].strip(),
        "route_type":    line[19:20].strip(),
        "transition":    line[20:25].strip(),
        "seq":           _opt_int(line[26:29]),
        "fix_ident":     line[29:34].strip(),
        "fix_region":    line[34:36].strip(),
        "fix_section":   line[36:37].strip(),
        "fix_subsection": line[37:38].strip(),
        "cont_rec_no":   cont.strip(),
        "wpt_desc":      line[39:43].strip(),
        "turn_dir":      line[43:44].strip(),
        "rnp":           line[44:47].strip(),
        "leg_type":      line[47:49].strip(),
        "turn_valid":    line[49:50].strip(),
        "rec_navaid":    line[50:54].strip(),
        "navaid_region": line[54:56].strip(),
        "navaid_subsec": line[56:58].strip(),
        "arc_radius":    line[58:61].strip(),
        "theta":         line[61:65].strip(),
        "rho":           line[65:69].strip(),
        "outbound_mag":  line[69:73].strip(),
        "route_dist":    line[73:77].strip(),
        "alt_desc":      line[82:83].strip(),
        "alt_1":         line[84:89].strip(),
        "alt_2":         line[89:94].strip(),
        "trans_alt":     line[94:99].strip(),
        "speed_limit":   line[99:102].strip(),
        "vert_angle":    line[102:106].strip(),
        "center_fix":    line[106:111].strip(),
        "center_region": line[112:114].strip(),
        "raw":           line.rstrip("\n"),
    }


def iter_leg_lines(
    path: Path,
) -> Iterator[dict]:
    """Yield one parsed leg dict per qualifying line."""
    with path.open("r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            leg = parse_leg_line(raw)
            if leg is not None:
                yield leg


# ─── Fix-bearing records (waypoints, navaids, runways)

def _decode_lat(s: str) -> float | None:
    """ARINC-424 'H DD MM SS ss' (9 chars) → decimal deg."""
    if len(s) != 9 or s[0] not in "NS":
        return None
    sign = 1 if s[0] == "N" else -1
    try:
        deg = int(s[1:3])
        minu = int(s[3:5])
        # SSss = whole seconds + hundredths
        sec = int(s[5:9]) / 100.0
    except ValueError:
        return None
    return sign * (deg + minu / 60.0 + sec / 3600.0)


def _decode_lon(s: str) -> float | None:
    """ARINC-424 'H DDD MM SS ss' (10 chars) → decimal deg."""
    if len(s) != 10 or s[0] not in "EW":
        return None
    sign = 1 if s[0] == "E" else -1
    try:
        deg = int(s[1:4])
        minu = int(s[4:6])
        sec = int(s[6:10]) / 100.0
    except ValueError:
        return None
    return sign * (deg + minu / 60.0 + sec / 3600.0)


def parse_fix_line(line: str) -> dict | None:
    """Parse a fix-bearing record (waypoint / navaid / runway).

    Returns ``{id, region, fix_type, lat, lon, airport,
    raw}`` or ``None`` if the line doesn't contribute
    a fix the leg compiler can consume.

    Handles four record subsets:

    * ``EA`` — Enroute Waypoint (id at 14-18, no airport).
    * ``P_`` then ``C`` (col 13) — Terminal Waypoint
      scoped to a specific airport.
    * ``P_`` then ``G`` (col 13) — Runway threshold
      (id like ``RW17R``, scoped to airport).
    * ``D``, ``DB`` — VOR-DME / NDB; position parsed
      from the standard 33-41 / 42-51 columns when
      present, else falls back to the second pair.
    """
    if len(line) < 51 or line[0] != "S":
        return None

    sec = line[4]
    sub = line[5] if len(line) > 5 else " "
    fix_type: str | None = None
    fix_id: str | None = None
    region: str | None = None
    airport: str | None = None

    if sec == "E" and sub == "A":
        # Enroute waypoint.
        fix_type = "WPT"
        fix_id = line[13:18].strip()
        region = line[19:21].strip()
    elif sec == "P":
        # Terminal record — col 13 disambiguates.
        sub_term = line[12] if len(line) > 12 else " "
        airport = line[6:10].strip()
        region = line[10:12].strip()
        if sub_term == "C":
            fix_type = "WPT"
            fix_id = line[13:18].strip()
        elif sub_term == "G":
            fix_type = "RWY"
            fix_id = line[13:18].strip()
        elif sub_term == "A":
            # Airport reference point — id = airport
            # ICAO so airport_position() can find it.
            fix_type = "APT"
            fix_id = airport
        else:
            return None
    elif sec == "D" and sub != "B":
        # VOR / VOR-DME / DME.  These often have two
        # coord blocks (VOR + DME); read the *first*
        # 9+10 chars after a 'N/S' that fits.
        fix_type = "VOR"
        fix_id = line[13:17].strip()
        region = line[19:21].strip()
    elif sec == "D" and sub == "B":
        fix_type = "NDB"
        fix_id = line[13:17].strip()
        region = line[19:21].strip()
    else:
        return None

    if not fix_id:
        return None

    # Try the canonical 33-41 / 42-51 positions first.
    lat = _decode_lat(line[32:41])
    lon = _decode_lon(line[41:51])
    if lat is None or lon is None:
        # Fallback: scan for the first valid N/S+E/W
        # pair anywhere in the line (covers VOR
        # records whose lat lives in the DME slot).
        lat, lon = _scan_first_coord(line)
        if lat is None or lon is None:
            return None

    return {
        "id": fix_id,
        "region": region or "",
        "fix_type": fix_type,
        "lat": lat,
        "lon": lon,
        "airport": airport,
        "raw": line.rstrip("\n"),
    }


def _scan_first_coord(
    line: str,
) -> tuple[float | None, float | None]:
    """Slow fallback for records with non-standard
    coord placement (e.g., VOR records whose lat
    sits in the DME-position slot)."""
    n = len(line)
    for i in range(n - 18):
        ch = line[i]
        if ch not in "NS":
            continue
        lat = _decode_lat(line[i:i + 9])
        if lat is None:
            continue
        lon = _decode_lon(line[i + 9:i + 19])
        if lon is None:
            continue
        return lat, lon
    return None, None


def iter_fix_lines(path: Path) -> Iterator[dict]:
    """Yield parsed fix records from a CIFP file."""
    with path.open("r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            fix = parse_fix_line(raw)
            if fix is not None:
                yield fix


# ─── Enroute airway records (Section ER) ────────────

def parse_airway_line(line: str) -> dict | None:
    """Parse one ER record → one fix in an airway.

    Column layout (CIFP 2603, verified empirically):

    - col 14-19: airway identifier (``V23``, ``J501``,
      ``Q802``, ``T278``; trailing blanks stripped).
    - col 26-29: sequence within airway, ×10.
    - col 30-34: fix identifier (5 chars).
    - col 35-36: fix region.
    - col 40-41: route type (``O`` = VOR-to-VOR,
      ``H`` = high-altitude jet, ``R`` = RNAV,
      ``L`` = LF/MF, etc.).
    - col 71-74 + 75-78: min / max altitude bounds
      (e.g., ``18000`` / ``60000`` for a J-route);
      in practice often reported as raw feet.

    Returns ``None`` if the line isn't an airway
    record (wrong section / bad columns).
    """
    if len(line) < 40 or line[0] != "S":
        return None
    if line[4:6] != "ER":
        return None
    airway_name = line[13:19].strip()
    if not airway_name:
        return None
    seq_raw = line[25:29].strip()
    seq = _opt_int(seq_raw)
    if seq is None:
        return None
    fix_id = line[29:34].strip()
    fix_region = line[34:36].strip()
    if not fix_id:
        return None
    route_type = line[39:41].strip()
    min_fl_raw = line[70:75].strip()
    max_fl_raw = line[75:80].strip()
    return {
        "airway_name": airway_name,
        "seq": seq,
        "fix_id": fix_id,
        "fix_region": fix_region,
        "route_type": route_type,
        "min_fl_ft": _opt_int(min_fl_raw),
        "max_fl_ft": _opt_int(max_fl_raw),
        "raw": line.rstrip("\n"),
    }


def iter_airway_lines(path: Path) -> Iterator[dict]:
    """Yield airway-fix records in file order.

    Consumers group by ``airway_name`` and sort by
    ``seq`` to reconstruct each airway's fix sequence.
    """
    with path.open("r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            row = parse_airway_line(raw)
            if row is not None:
                yield row


def group_procedures(
    legs: Iterable[dict],
) -> Iterator[dict]:
    """Collect leg records into procedure groups.

    A procedure is keyed by
    ``(airport, proc_type, name, transition)`` —
    that's how CIFP organizes them, and matches the
    way pilots refer to them on a chart (the
    "NEELY1.RW17R" departure off DFW).
    """
    current_key: tuple | None = None
    current: dict | None = None

    def _emit():
        if current is not None and current["legs"]:
            current["legs"].sort(
                key=lambda x: x.get("seq") or 0,
            )
            yield_buffer.append(current)

    yield_buffer: list[dict] = []
    for leg in legs:
        key = (
            leg["airport"], leg["proc_type"],
            leg["name"], leg["transition"],
        )
        if key != current_key:
            _emit()
            for emitted in yield_buffer:
                yield emitted
            yield_buffer = []
            current_key = key
            current = {
                "id": _proc_id(*key),
                "airport": leg["airport"],
                "proc_type": leg["proc_type"],
                "name": leg["name"],
                "transition": leg["transition"] or None,
                "legs": [],
            }
        current["legs"].append(leg)
    _emit()
    for emitted in yield_buffer:
        yield emitted


def _proc_id(
    airport: str,
    proc_type: str,
    name: str,
    transition: str,
) -> str:
    """Stable id used as primary key in the DB."""
    return f"{airport}-{proc_type}-{name}-{transition or 'ALL'}"
