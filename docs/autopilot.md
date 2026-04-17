# Autopilot & FMS

Every BlueSky aircraft flies under autopilot. The
autopilot takes a **selected** target for each axis —
heading, altitude, speed, vertical speed — and commands
the aircraft toward it, subject to performance limits.
The **FMS** (flight management system) is layered on top,
feeding the autopilot from a waypoint-based route.

## Selected values vs. current values

This distinction trips up newcomers. For each axis there
are two numbers:

| Axis | Current | Selected (target) |
|---|---|---|
| Heading | `bs.traf.hdg[i]` | `bs.traf.ap.selhdg[i]` |
| Track | `bs.traf.trk[i]` | `bs.traf.ap.trk[i]` |
| Altitude | `bs.traf.alt[i]` | `bs.traf.ap.alt[i]` / `selalt` |
| Speed (CAS) | `bs.traf.cas[i]` | `bs.traf.ap.spd[i]` / `selspd` |
| Vertical speed | `bs.traf.vs[i]` | `bs.traf.ap.vs[i]` |

**Current** = what the aircraft is doing right now.
**Selected** = what the autopilot is trying to achieve.

Cesium-BlueSky's aircraft panel surfaces both on each
axis row: the big number is current, the `[_______]`
input is selected (with a `SET` button to update it).

## Autopilot modes

Two modes govern how the selected targets are chosen:

- **LNAV** (Lateral Navigation) — when on, the autopilot
  steers along the FMS route (toward the active
  waypoint). When off, the aircraft flies whatever
  heading you last `SET` via `HDG`.
- **VNAV** (Vertical Navigation) — when on, the autopilot
  follows altitude and speed constraints from the FMS
  route. When off, it holds whatever `ALT` / `SPD` you
  set manually.

State flags: `bs.traf.swlnav[i]` and `bs.traf.swvnav[i]`.
Toggle via `LNAV <acid> ON|OFF` and `VNAV <acid> ON|OFF`.

Manual `HDG` automatically disengages LNAV for that
aircraft. Manual `ALT` disengages VNAV similarly. This
matches real airline autopilot behavior — pilot input
overrides FMS guidance.

## Commanding the autopilot

Basic commands:

```
HDG KL204 090         # turn to 090°
ALT KL204 FL350       # climb/descend to FL350
SPD KL204 280         # target 280 kt CAS
VS  KL204 1500        # vertical speed 1500 fpm (target only, not autopilot command)
LNAV KL204 ON         # resume route tracking
VNAV KL204 ON         # resume altitude / speed profile
```

When LNAV is on, `HDG` is transient — the autopilot steers
to the commanded heading briefly, then LNAV kicks back in.
To actually leave the route, combine `HDG` with `LNAV OFF`.

## The FMS route

Every aircraft has a route object at
`bs.traf.ap.route[i]` with parallel arrays:

| Array | Meaning |
|---|---|
| `wpname` | Waypoint names |
| `wplat`, `wplon` | Waypoint positions |
| `wpalt` | Altitude constraint (-1 = no constraint) |
| `wpspd` | Speed constraint (-1 = no constraint) |
| `wptype` | Waypoint kind (origin, destination, fix, etc.) |
| `iactwp` | Index of the active (next) waypoint |

Typical route-building commands:

```
CRE KL204 B738 52.31 4.76 090 FL100 220    # create at EHAM vicinity
ORIG KL204 EHAM                             # set origin
DEST KL204 LEMD                             # set destination
ADDWPT KL204 SPY FL350 280                  # add SPY with constraints
ADDWPT KL204 MAR FL350 280
LNAV KL204 ON                               # engage LNAV
VNAV KL204 ON                               # engage VNAV
OP                                          # start sim
```

The active waypoint is `wpname[iactwp]`. When the
aircraft gets within the capture distance, `iactwp`
increments and the next waypoint becomes active.

## How the autopilot steers

Per step, `bs.traf.ap.update()` computes commanded
acceleration and turn rate to drive each axis toward its
selected target:

- **Heading** — turn rate derived from bank angle
  (default max 25°, scaled by true airspeed).
- **Altitude** — vertical speed ramped toward selected
  VS or the FMS-commanded climb/descent rate.
- **Speed** — thrust/drag difference to accelerate or
  decelerate toward selected CAS, capped by performance
  model.

If the conflict resolver (RESO) has flagged this
aircraft, the resolver's `newtrack/gs/vs/alt` values
**override** the selected targets for that step. The
autopilot still runs the servo loop — it just uses the
resolver's demand instead of the FMS's.

## Bank angle

Turn dynamics are bank-based:
```
turn_rate = g · tan(bank) / TAS
```
With a 25° bank limit and cruise TAS, standard turn rates
work out to ~3°/s (2-minute 360° turn). BlueSky's stock
behavior is **binary** — bank is either at the limit
during a turn or zero. See [Smooth
Banking](/docs/plans/smooth-banking) for a plan to add
roll-in / roll-out dynamics.

The bank angle is displayed on the aircraft side panel
(e.g., `25° ↻ R (max 25°)`) and can be computed from
`bs.traf.ap.turnphi` + sign of heading error.

## Wind correction

With wind, the aircraft's **heading** (nose direction)
and **track** (actual path over ground) diverge. The
autopilot targets track, so:

```
hdg ≈ trk + wca         (wind correction angle / crab)
```

Cesium-BlueSky displays this on the aircraft panel: `HDG`
row shows `H095° / T100° (WCA 5°R)` when there's a
non-trivial crab, or just `095°` when calm. See
[Wind](/docs/wind) for how the wind sample reaches the
aircraft.

## Related reading

- [Simulation Overview](/docs/simulation-overview) — how
  the autopilot fits into the main loop.
- [Conflict Detection & Resolution](/docs/asas) — how
  RESO overrides the autopilot.
- [Wind](/docs/wind) — why HDG ≠ TRK.
