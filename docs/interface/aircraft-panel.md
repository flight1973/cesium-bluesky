# Aircraft Panel

The aircraft panel slides in from the right when you
select an aircraft (click on the globe or click a row in
the traffic list). It combines a glass-cockpit-style
state display with inline autopilot controls and route
information.

The panel auto-refreshes every second while open, so
values always reflect the live sim state.

## Header

```
┌─────────────────────────────┐
│ KL204  B738          [×]    │
│ EHAM → LEMD                 │
├─────────────────────────────┤
```

- **Callsign and type** — `KL204 B738` style.
- **Origin → destination** — from the FMS route's ORIG
  / DEST waypoints, or `----` if unset.
- **Close button** — `×` top-right; deselects the
  aircraft.

## Autopilot rows

Four axes, each showing **current state** on the left
and an **autopilot selected value** input with a
**SET** button on the right.

### HDG

Current heading / track display. Adapts to wind:

- **Calm air**: `095°` — single value (hdg and trk
  match).
- **Crab angle present**: `H095° / T100° (WCA 5°R)` —
  shows heading, track, and the wind correction angle
  with direction.

The input is the autopilot's **selected heading**.
Pressing SET (or Enter in the input) sends
`HDG <acid> <value>`. The `HDG` command also
auto-disengages LNAV for that aircraft (matching real
autopilot behavior).

### ALT

- Current value shown as `FL350`.
- Input accepts `FL350`, `35000`, `10000ft`, etc.
- SET sends `ALT <acid> <value>`.

### SPD

- Current value shown as `280kts` (using CAS).
- Input accepts a number; unit is assumed from BlueSky's
  default (kt internally).
- SET sends `SPD <acid> <value>`.

### VS

- Current vertical speed in `fpm` (positive up, negative
  down).
- Input is the target vertical speed.
- SET sends `VS <acid> <value>`.

## BANK

Display-only row showing bank angle with direction
arrow:

```
BANK   25° ↻ R (max 25°)
BANK   0° level (max 25°)
BANK   18° ↺ L (max 25°)
```

The direction arrow (`↻ R` right / `↺ L` left) indicates
which way the aircraft is banking. `level` means wings
level. Max bank is the aircraft's configured limit.

BlueSky's stock turn model snaps bank from 0 to the
limit instantly during turns — see
[Smooth Banking](/docs/plans/smooth-banking) for a plan
to model proper roll-in / roll-out dynamics.

## WIND

Display-only row showing wind **sampled at this
aircraft's position and altitude**:

```
WIND   270°/28 kt
WIND   CALM                   # if < 0.5 m/s
```

Always in METAR convention (from-direction). Unit
follows the global unit system (kt / m/s / mph).

## Airspeed triplet

Three rows showing speeds in three canonical forms:

| Row | What it is |
|---|---|
| **IAS** | Indicated airspeed. Currently equal to CAS in BlueSky (no instrument or position error modeled). See the [IAS TODO](/docs/autopilot). |
| **CAS** | Calibrated airspeed — the pilot's reference speed after instrument correction. |
| **GS** | Ground speed — actual speed over the ground, including wind. Differs from CAS by wind component along track. |

Note that **TAS** is not shown but is accessible via the
REST API. The three shown cover the typical pilot
workflow; TAS matters mostly for atmospheric / density
calculations.

## Autopilot mode buttons

Row of toggle buttons below the physical state:

| Button | Purpose |
|---|---|
| **LNAV ON/OFF** | Toggles LNAV (lateral navigation). When on, autopilot steers along the FMS route. |
| **VNAV ON/OFF** | Toggles VNAV (vertical navigation). When on, autopilot follows altitude / speed constraints from the FMS. |
| **FMS** | Opens the FMS panel for route editing. |
| **CHASE** | Attach the camera to this aircraft in 3rd-person behind-and-above view. Click again to detach. |
| **PILOT** | Attach the camera in 1st-person cockpit view. Click again to detach. |

LNAV / VNAV buttons use **optimistic updates** — the
label flips immediately on click while the backend
catches up, then reconciles on the next refresh.

See [Camera Modes](/docs/interface/camera-modes) for
chase / pilot details.

## Route section

If the aircraft has FMS waypoints, a scrolling list
shows them below the controls:

```
Route: 5 waypoints
  EHAM  -----/---
▶ SPY   FL350/280
  MARKA FL350/280
  ADX   FL240/280
  LEMD  FL050/180
```

- **`▶`** marks the active waypoint (the one the FMS is
  currently tracking toward).
- **`FL/spd`** columns show the altitude and speed
  **constraints** at each waypoint. `-----` / `---`
  means no constraint.

## Keyboard

- **Enter** in any SET input submits the command (same
  as clicking SET).
- Click anywhere outside the panel (but not on another
  aircraft) to leave selection unchanged — the panel
  stays open. Click the `×` or click empty space to
  close.

## Panel lifecycle

1. Selecting an aircraft (map click or traffic-list
   click) calls `GET /api/aircraft/{acid}/detail` to
   populate the panel.
2. A 1-second refresh timer re-fetches the detail while
   the panel is open.
3. When you issue a SET command or a LNAV / VNAV toggle,
   the panel schedules extra refreshes at 500 ms and
   1,500 ms to catch up quickly.
4. Closing the panel (via `×` or clicking blank space)
   dispatches `panel-close` — the camera detaches, the
   route line clears, and the refresh timer stops.
