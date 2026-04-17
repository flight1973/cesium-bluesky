# Visual Conventions

Everything you see on the globe has a meaning. This page
decodes the colors, symbols, shapes, and label formats
Cesium-BlueSky uses.

## Aircraft

### Point and velocity vector

Each aircraft is a **colored point** with an optional
velocity-vector leader line projecting ~1 minute ahead
in the direction of travel.

| Color | State |
|---|---|
| **Green** | Normal — no predicted conflict. |
| **Orange** | In predicted conflict — another aircraft's PZ is expected to be breached within look-ahead. |
| **Red** | Loss of separation — PZ currently intruded by another aircraft. |

The selected aircraft gets a slightly brighter point
plus a magenta route line (if it has an FMS route).

### Floating label

A two-line block next to each aircraft:

```
KL204
FL350 280
```

- **Line 1** — callsign.
- **Line 2** — flight level and calibrated airspeed
  (e.g., `FL350 280` means FL350, 280 kt CAS).

Labels render above other geometry so they stay readable
through PZ cylinders or other aircraft.

## Protected Zone (PZ)

3D cylinder around each aircraft showing the separation
boundary other aircraft should respect.

- **Shape** — cylinder at the aircraft's altitude,
  radius `rpz` (default 5 NM), height `2 × hpz`
  (default ±1000 ft).
- **Color** — matches the aircraft state:
  - **Green** — no conflict predicted.
  - **Orange** — predicted conflict.
  - **Red** — loss of separation in progress.
- **Transparency** — ~30% opaque, so aircraft labels
  and nearby geometry remain visible through it.

PZ rendering is **3D** — top and bottom surfaces are
drawn at the correct altitudes so you can see from any
camera angle whether two aircraft are vertically
separated even when they're horizontally close.

## Routes

Magenta polyline for the selected aircraft's FMS route:

- **Line** — connects current aircraft position to the
  active waypoint, then each subsequent waypoint in
  order.
- **Waypoint markers** — triangle billboards at each
  route point.
- **Constraint labels** — `FL/kt` at each waypoint:
  - `FL350/280` — cross at FL350, at 280 kt.
  - `-----/---` — no constraint.
- **Active waypoint** — highlighted in yellow with a
  `▶` marker (visible in the aircraft panel's route
  list).

Only one route renders at a time (the selected
aircraft's). Toggle off entirely via the **ROUTE**
button in the LAYERS tab.

## Trails

Cyan polyline trailing each aircraft, recording where
it's been.

- **Color** — cyan, consistent across all aircraft.
- **Accumulation** — segments are added each second
  while `TRAIL ON` is active in the sim.
- **Cleared on RESET or IC** — trails don't persist
  across scenarios.

## Airports

- **Symbol** — square billboard.
- **Label** — ICAO code (e.g., `EHAM`, `LEMD`).
- **Zoom filtering** — at global zoom only major
  airports; zoom in for regional and smaller.

## Waypoints

- **Symbol** — triangle billboard.
- **Label** — waypoint name (e.g., `SPY`, `ROUSY`).
- **Zoom filtering** — VOR/NDB at continental scale;
  all types when zoomed in.

## Areas

Deletion-area polygons / boxes / circles drawn in the
AREAS tab.

- **Fill** — semi-transparent cyan.
- **Outline** — solid cyan.
- **Active area** — brighter outline, pulsed to show
  which shape is currently deleting aircraft that
  leave its bounds.
- **3D volume** — if top/bottom altitudes are set, the
  area has a visible vertical extent (cylinder for
  CIRCLE, prism for POLY/BOX). Otherwise it extends
  from ground to ~100 km (Kármán line) for visual
  clarity.

## Aircraft panel — readouts

### Heading and track

- **Calm air** — `095°` (one value, hdg ≈ trk).
- **Wind present** — `H095° / T100° (WCA 5°R)`:
  - **H** = heading (nose direction).
  - **T** = track (path over ground).
  - **WCA** = wind correction angle with direction
    (`R` right, `L` left).

### Altitude

- `FL350` — flight level (altitude in hundreds of feet
  above 29.92 inHg).
- Below the transition altitude, shown as raw feet:
  `5000ft`.

### Speed

- `280kts` — CAS when in aviation units.
- Always annotated with the unit (`kt`, `m/s`, or
  `mph`) based on the unit system.

### Vertical speed

- `+1500fpm` — climbing.
- `-2000fpm` — descending.
- `0fpm` — level.

### Bank

- `25° ↻ R (max 25°)` — 25° right bank, at the limit.
- `0° level (max 25°)` — wings level.
- `15° ↺ L (max 25°)` — 15° left bank.

### Wind

- `270°/28 kt` — wind from the west at 28 knots
  (METAR convention, "from" direction).
- `CALM` — wind speed below 0.5 m/s.

## Status bar (bottom of screen)

Format:
```
Sim: 00:15:30, Sim UTC: 2026-04-13 00:15:30,
Wall UTC: 2026-04-13 14:22:10,
Δt: 0.05, Speed: 1.0x, Mode: OP, Aircraft: 12,
Conflicts: 2/4, LoS: 0/0
```

- **Sim** — simulation time since start (`HH:MM:SS`).
- **Sim UTC** — simulated wall clock (from any `UTC`
  command in scenarios).
- **Wall UTC** — your computer's current UTC time.
- **Δt** — integration step length (seconds).
- **Speed** — wall-clock multiplier (`1.0x` = real
  time).
- **Mode** — `INIT / OP / HOLD / END`.
- **Aircraft** — ntraf.
- **Conflicts** — `current / total-since-start`,
  orange text.
- **LoS** — loss-of-separation counts, red text.

## Camera controls (bottom-left overlay)

Shows:

- **Tilt** — current pitch angle of the camera.
- **Alt** — approximate camera altitude above ellipsoid.
- Buttons for straight-down, reset, and manual tilt
  adjustment.

## Scale bar (bottom-right overlay)

- **Length** — representative distance at the current
  zoom level.
- **Unit** — matches the selected unit system
  (NM / km / mi).
- **Auto-resize** — updates as you zoom / pan.

## Gear menu (top-right)

- **⚙ icon** — always visible.
- **Units** radios — aviation / SI / imperial.
- **Documentation link** — 📖 Documentation ↗ opens
  this site in a new tab.

## Summary color key

| Color | Meaning |
|---|---|
| Green | Clear / OK / no conflict |
| Orange | Predicted conflict |
| Red | Loss of separation |
| Cyan | Trails, areas, neutral overlays |
| Magenta | Selected aircraft's FMS route |
| Yellow | Active waypoint highlight |
| White | Labels, prominent text |
| Gray | Inactive buttons, dividers |
