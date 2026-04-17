"""Convert recorded ADS-B replay tracks into BlueSky .scn scenario files.

Each aircraft is CREated on first appearance. State changes
(altitude, speed, heading) are detected with deadband
thresholds, and ALT/SPD/HDG commands are issued with lead
time calculated from the aircraft's performance envelope
(via OpenAP kinematic limits when available).

Usage:
    python -m cesium_app.surveillance.replay_to_scenario \\
        --session dfw-full \\
        --start 1656342000 --stop 1656345600 \\
        --output dfw-replay.scn
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cesium_app.surveillance.replay import _connect, _ensure_schema

logger = logging.getLogger(__name__)

M_TO_FT = 3.28084
MS_TO_KT = 1.94384
MS_TO_FPM = 196.85

# Deadband thresholds for detecting intentional changes.
ALT_DEADBAND_FT = 200
SPD_DEADBAND_KT = 5
HDG_DEADBAND_DEG = 5

# Default performance for lead-time calculation.
DEFAULT_CLIMB_FPM = 2000
DEFAULT_DESCENT_FPM = 1500
DEFAULT_ACCEL_KT_S = 2.0


def _fmt_time(epoch: int, t0: int) -> str:
    """Format epoch as HH:MM:SS.00 relative to scenario start."""
    dt = epoch - t0
    h = dt // 3600
    m = (dt % 3600) // 60
    s = dt % 60
    return f"{h:02d}:{m:02d}:{s:02d}.00"


def _get_perf(typecode: str) -> dict:
    """Get performance limits for lead-time calculation."""
    try:
        from cesium_app.performance.openap_adapter import (
            get_kinematic_envelope, _resolve,
        )
        env = get_kinematic_envelope(typecode)
        climb_vs = env.get('climb_vs_concas_ms', {})
        descent_vs = env.get('descent_vs_concas_ms', {})
        return {
            'climb_fpm': abs(climb_vs.get('default', 0)) * MS_TO_FPM
                         or DEFAULT_CLIMB_FPM,
            'descent_fpm': abs(descent_vs.get('default', 0)) * MS_TO_FPM
                           or DEFAULT_DESCENT_FPM,
        }
    except Exception:
        return {
            'climb_fpm': DEFAULT_CLIMB_FPM,
            'descent_fpm': DEFAULT_DESCENT_FPM,
        }


def convert(
    session: str,
    start_epoch: int | None = None,
    stop_epoch: int | None = None,
    output: str | Path = "replay.scn",
) -> dict:
    """Convert a replay session to a .scn file.

    Returns stats: {aircraft, commands, duration_s}.
    """
    conn = _connect()
    _ensure_schema(conn)
    conn.row_factory = sqlite3.Row

    where = "WHERE session = ?"
    params: list = [session]
    if start_epoch:
        where += " AND time >= ?"
        params.append(start_epoch)
    if stop_epoch:
        where += " AND time <= ?"
        params.append(stop_epoch)

    rows = conn.execute(f"""
        SELECT icao24, time, lat, lon, velocity, heading,
               vertrate, callsign, onground, squawk,
               baro_alt, geo_alt
        FROM replay_states
        {where}
        ORDER BY time, icao24
    """, params).fetchall()
    conn.close()

    if not rows:
        return {"aircraft": 0, "commands": 0, "duration_s": 0}

    t0 = rows[0]['time']
    t_end = rows[-1]['time']

    # Try to get typecodes from the aircraft registry.
    try:
        from cesium_app.ingest import aircraft_db
        def _typecode(icao24: str) -> str:
            reg = aircraft_db.lookup(icao24)
            return (reg.get('typecode') or 'B738').strip() if reg else 'B738'
    except Exception:
        def _typecode(icao24: str) -> str:
            return 'B738'

    # Track state per aircraft.
    state: dict[str, dict] = {}
    commands: list[tuple[int, str]] = []
    perf_cache: dict[str, dict] = {}
    created = set()
    deleted = set()

    for row in rows:
        icao = row['icao24']
        t = row['time']
        alt_m = row['geo_alt'] or row['baro_alt'] or 0
        alt_ft = alt_m * M_TO_FT
        vel_kt = (row['velocity'] or 0) * MS_TO_KT
        hdg = row['heading'] or 0
        cs = (row['callsign'] or '').strip() or icao.upper()
        on_ground = row['onground']
        lat = row['lat']
        lon = row['lon']

        if icao not in state:
            # First appearance — CRE command.
            tc = _typecode(icao)
            if not on_ground and vel_kt > 30:
                commands.append((t, (
                    f"CRE {cs} {tc} "
                    f"{lat:.5f} {lon:.5f} "
                    f"{hdg:.0f} {alt_ft:.0f} {vel_kt:.0f}"
                )))
                created.add(icao)
            state[icao] = {
                'cs': cs, 'tc': tc,
                'alt_ft': alt_ft, 'spd_kt': vel_kt,
                'hdg': hdg, 'last_t': t,
            }
            if tc not in perf_cache:
                perf_cache[tc] = _get_perf(tc)
            continue

        if icao not in created:
            continue

        prev = state[icao]
        cs = prev['cs']
        tc = prev['tc']
        perf = perf_cache.get(tc, {})

        # Detect altitude change.
        dalt = alt_ft - prev['alt_ft']
        if abs(dalt) > ALT_DEADBAND_FT:
            # Calculate lead time.
            if dalt > 0:
                lead_s = abs(dalt) / (perf.get('climb_fpm', DEFAULT_CLIMB_FPM) / 60)
            else:
                lead_s = abs(dalt) / (perf.get('descent_fpm', DEFAULT_DESCENT_FPM) / 60)
            cmd_t = max(t0, int(t - lead_s))
            commands.append((cmd_t, f"ALT {cs} {alt_ft:.0f}"))
            prev['alt_ft'] = alt_ft

        # Detect speed change.
        dspd = vel_kt - prev['spd_kt']
        if abs(dspd) > SPD_DEADBAND_KT:
            lead_s = abs(dspd) / DEFAULT_ACCEL_KT_S
            cmd_t = max(t0, int(t - lead_s))
            commands.append((cmd_t, f"SPD {cs} {vel_kt:.0f}"))
            prev['spd_kt'] = vel_kt

        # Detect heading change.
        dhdg = hdg - prev['hdg']
        if dhdg > 180:
            dhdg -= 360
        if dhdg < -180:
            dhdg += 360
        if abs(dhdg) > HDG_DEADBAND_DEG:
            commands.append((t, f"HDG {cs} {hdg:.0f}"))
            prev['hdg'] = hdg

        prev['last_t'] = t

    # DEL aircraft at their last appearance.
    for icao, prev in state.items():
        if icao in created:
            commands.append((
                prev['last_t'] + 10,
                f"DEL {prev['cs']}",
            ))

    # Sort by time, deduplicate.
    commands.sort(key=lambda c: c[0])

    # Write .scn file.
    output = Path(output)
    with output.open('w') as f:
        f.write(f"# Replay-to-scenario: {session}\n")
        f.write(f"# Period: {t0} to {t_end}\n")
        f.write(f"# Aircraft: {len(created)}\n")
        f.write(f"# Commands: {len(commands)}\n\n")
        for t, cmd in commands:
            f.write(f"{_fmt_time(t, t0)} > {cmd}\n")

    stats = {
        "aircraft": len(created),
        "commands": len(commands),
        "duration_s": t_end - t0,
        "output": str(output),
    }
    logger.info(
        "Scenario written: %d aircraft, %d commands, %s",
        stats['aircraft'], stats['commands'], output,
    )
    return stats


def _cli():
    import argparse
    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser(
        description="Convert replay to BlueSky scenario",
    )
    p.add_argument('--session', required=True)
    p.add_argument('--start', type=int, default=None)
    p.add_argument('--stop', type=int, default=None)
    p.add_argument('--output', default='replay.scn')

    args = p.parse_args()
    stats = convert(
        args.session, args.start, args.stop, args.output,
    )
    import json
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    _cli()
