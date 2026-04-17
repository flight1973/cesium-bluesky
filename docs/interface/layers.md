# Layers

Visualization layers are toggled from the **LAYERS tab**
of the toolbar. Each layer is an independent overlay on
the 3D globe. Toggles are immediate — no reload needed.

## Aircraft

Always on. Every aircraft in `bs.traf` renders as a
point with optional label, velocity vector, and PZ
cylinder.

- **Color**: green (clear), orange (in conflict), red
  (loss of separation).
- **Position**: from ACDATA lat/lon/alt, scaled by
  Alt Exag for display.
- **Selected aircraft**: highlighted with a brighter
  point and a route line.

See [Visual Conventions](/docs/interface/visual-conventions)
for the full color code.

## TRAIL

Cyan polylines trailing behind each aircraft, recording
its position history.

- **Enables `TRAIL ON` in the sim** — the button does
  double duty, turning on BlueSky's trail recording
  AND toggling the display. `TRAIL ON` causes the sim
  to publish `TRAILS` WebSocket messages every second;
  the frontend accumulates segments into a rolling
  polyline collection.
- **Cleared on RESET / IC** — trails don't persist
  across scenarios.
- **No per-aircraft filter** — all aircraft's trails
  render.

## ROUTE

Magenta polyline showing the selected aircraft's FMS
route:

- Line from **aircraft → active waypoint → remaining
  waypoints** in sequence.
- **Waypoint markers** at each route point.
- **Constraint labels** at each waypoint:
  `FL350 / 280` means "cross at FL350, 280 kt" —
  `---` indicates no constraint.
- Only one aircraft's route at a time (the selected
  one). Deselecting hides it.

Click a different aircraft to switch whose route is
shown. Toggle **ROUTE OFF** to hide even when an
aircraft is selected.

## LABEL

Floating text block next to each aircraft showing:

```
KL204
FL350 280
```

Line 1 is the callsign; line 2 is flight level and CAS.
Toggle off for a cleaner view when tracking many
aircraft.

Labels **always render above other geometry** (via
`disableDepthTestDistance`), so they stay readable
even when behind PZ cylinders or other aircraft in 3D.

## VEL VECTOR

Leader line projecting **1 minute ahead** of each
aircraft based on current ground speed and track:

- Line length = `gs × 60 seconds`.
- Line color matches aircraft color (green / orange /
  red).
- Shows intended direction of motion; useful for
  reading traffic flow at a glance.

Works in both 2D and 3D.

## PZ (Protected Zone)

3D cylinders around each aircraft indicating the zone
that other aircraft should not enter.

- **Shape**: flat cylinder at the aircraft's altitude,
  with radius = `rpz` (default 5 NM) and top/bottom at
  `alt ± hpz` (default ±1000 ft).
- **Color**:
  - **Green** — no conflict predicted.
  - **Orange** — predicted conflict with another
    aircraft's PZ within look-ahead.
  - **Red** — currently in loss of separation (another
    PZ is intruded right now).
- **Rendered as 3D volumes** — the top and bottom
  surfaces are visible from any camera angle, making
  vertical separation immediate and obvious.
- **Transparency** — semi-transparent so aircraft
  labels remain readable.

Toggle off when scaling visibly or when you want a
less-cluttered view.

See [Conflict Detection & Resolution](/docs/asas) for
what the colors mean in terms of sim state, and
[Autopilot & FMS](/docs/autopilot) for how detection
interacts with the resolver.

## APT (Airports)

Small markers at airport positions from BlueSky's nav
database.

- **Zoom-filtered**: at global scale, only major
  airports (`aptype=1`). At continental scale, medium
  airports. Zoomed in close, all airports visible.
- **Label**: ICAO code (e.g., `EHAM`, `LEMD`).
- **Shape**: square billboard.

Lookups come from `/api/navdata/airports` with the
current camera bounds; the frontend debounces fetches
as you pan / zoom.

## WPT (Waypoints)

Same zoom-filtered pattern as airports, for en-route
waypoints (fixes, VOR, NDB, etc.).

- **Shape**: triangle billboard.
- **Label**: waypoint name (e.g., `SPY`, `ROUSY`).
- **Tiered visibility**: VOR/NDB at continental scale,
  full waypoint set only when zoomed in closer.

## Areas

Not a LAYERS-tab toggle — areas render whenever any
shape is defined. See [Area Tools](/docs/interface/area-tools).

## Performance impact

At typical research scales (a few hundred aircraft),
all layers on is smooth at 60fps. For large fleets:

- **LABEL**, **VEL VECTOR**, and **PZ** are the most
  expensive per-aircraft layers.
- Toggling them off recovers frame rate for very large
  sims.
- **APT / WPT** zoom-filter aggressively, so they scale
  fine even globally.
- **TRAIL** accumulates unboundedly until the next
  RESET — at high speed with long runs, the trail
  polyline collection can get large.

## Persistence

Layer toggles are **per-session** — they don't persist
across reloads. This is intentional: the default set
(`ROUTE`, `LABEL`, `VEL VECTOR` on; others off) is a
reasonable starting point for most tasks.
