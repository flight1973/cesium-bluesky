# Camera Modes

Cesium-BlueSky offers five camera behaviors today,
with two more planned:

1. **Free camera** (default) — standard Cesium
   pan/tilt/zoom.
2. **CHASE** — 3rd-person view locked behind and above
   a selected aircraft.
3. **PILOT** — 1st-person cockpit view looking forward
   from the aircraft.
4. **STARBOARD** — window view looking out the right
   side.
5. **PORT** — window view looking out the left side.
6. **RUNWAY** *(planned)* — stationary camera at a
   selected airport / runway, pointed down the runway,
   optionally tracking an inbound or outbound
   aircraft.
7. **PADLOCK / SPOT** *(planned)* — camera positioned
   on one object but looking at another, decoupling
   vantage point from target.

All tracking modes are driven by a **preset table**
keyed by mode name — each preset is a
(forward, right, up) offset in the aircraft's local
ENU frame plus a (yaw, pitch) offset from its track.
Adding a new mode is one new entry; no new tracking
loop.

Chase and Pilot are toggles on the aircraft panel. Each
click toggles the camera on / off for that aircraft /
mode combo.

## CHASE

Click the **CHASE** button on the aircraft panel.

- Camera position: ~150 m **behind** the aircraft,
  ~25 m **above** it.
- Camera orientation: pitch ~−5° (looking down and
  forward), heading matches aircraft track.
- Updates every render frame so the camera stays glued
  to the aircraft as it flies.

Useful for watching maneuvers, climb/descent profiles,
and sequencing through a waypoint route. The aircraft is
always framed with a bit of sky / ground visible for
spatial orientation.

## PILOT

Click the **PILOT** button on the aircraft panel.

- Camera position: at the aircraft, with a small forward
  offset so you're at the nose rather than inside the
  hull.
- Camera orientation: pitch ~−2° (slight downward look),
  heading matches aircraft track.
- Full 3D forward-looking view.

Useful for approach visualization, spatial checks
("does the autopilot steer toward this waypoint
correctly?"), and spotting terrain features or other
aircraft from the pilot's perspective.

Note: this view is just at the aircraft position — it
doesn't render a cockpit model, instrument panel, or
windscreen. It's a simulated out-the-window view, not a
flight simulator cockpit.

## Toggling off

Click the same button again to detach the camera:

- **CHASE → click CHASE** again = off.
- **PILOT → click PILOT** again = off.

Switching between modes on the same aircraft toggles
directly — clicking **PILOT** while chasing jumps to
pilot view without first detaching.

Selecting a different aircraft automatically **detaches**
the camera. This is intentional: it prevents the camera
from being "stuck" on an old aircraft you deselected.

## Under the hood

Camera tracking is implemented as a `scene.preRender`
listener that:

1. Reads the tracked aircraft's current state (lat,
   lon, alt, track) from the aircraft manager's cache.
2. Computes a local ENU (east-north-up) offset based on
   the chosen mode.
3. Multiplies by the ENU→world transform at the
   aircraft's position to get the camera's world-frame
   Cartesian.
4. Sets camera `destination` + `orientation` each
   frame.

The offset math:

```typescript
if (mode === 'pilot') {
  east  = sin(heading) * 3;
  north = cos(heading) * 3;
  up    = 2;
  pitch = -2;
} else {  // chase
  east  = -sin(heading) * 150;
  north = -cos(heading) * 150;
  up    = 25;
  pitch = -5;
}
```

Negative east/north in chase mode puts the camera on the
*opposite* side of the heading vector (behind the
aircraft); positive values in pilot mode put the camera
*ahead* of the aircraft position (at the nose).

## Altitude exaggeration

The tracked aircraft's altitude is multiplied by the
viewer's **Alt Exag** factor (VIEW tab, default 10×) to
match how aircraft are rendered. Otherwise chase/pilot
views would misalign at cruise altitudes.

## STARBOARD / PORT (planned)

Not yet implemented. The design intent:

- Aircraft-attached, like CHASE and PILOT.
- Camera at the aircraft position, oriented **90° to
  the right** of track (STARBOARD) or **90° to the
  left** (PORT), pitch near-level.
- Gives a window-seat / passenger-side view —
  especially useful during banked turns (the low wing
  side shows the ground beautifully, the high wing
  side shows sky).
- Toggle behavior identical to CHASE / PILOT: click
  again to detach, switch modes by clicking the other
  button.

## PADLOCK / SPOT (planned)

Not yet implemented. The most general of the planned
camera modes — **decouples the camera's position from
its target**.

- **Position source** — where the camera *sits*. Can
  be an aircraft, a waypoint, a runway, an airport, a
  fixed lat/lon/alt, or "free."
- **Target source** — what the camera *looks at*.
  Same taxonomy, independently chosen.
- Camera updates each frame: position and target
  resolve to world coordinates, camera orients toward
  the target.

Use cases:

- Watching traffic from a stationary vantage (camera
  on a runway threshold, target = the next aircraft
  on final).
- Studying conflict geometry — camera on one aircraft
  in a conflict pair, target locked on the other.
- Keeping a waypoint or runway centered on screen
  while the host aircraft maneuvers around it.
- Virtual "chase ship" — camera on one aircraft,
  target on a different aircraft it's escorting.

Design intent: this may eventually **subsume** CHASE,
PILOT, STARBOARD/PORT, and RUNWAY as presets — each
of those is a special case of "position source X,
target source Y." Worth exploring whether the
generalized form replaces the bespoke modes or
coexists as an advanced option.

## RUNWAY (planned)

Not yet implemented. The design intent:

- Pick an **airport** (from `bs.navdb`) and a **runway**
  on that airport.
- Camera placed at the runway **center** (or
  threshold), at eye height above runway elevation.
- Heading aligned with the **runway heading**, pitch
  near-level for a natural ground-observer view.
- Optional **tracking mode** — follow the nearest
  inbound aircraft on approach to that runway, or the
  latest aircraft cleared for takeoff from it.

Intended use: watching landings, takeoffs, and
ground-level operations from the tower/observer
perspective. A complement to CHASE (aircraft-attached)
and PILOT (aircraft-POV).

## Tips

- **CHASE for storyboarding** — lets you watch the
  aircraft execute a full route from a pleasant
  external view. Good for demos.
- **PILOT for spatial checks** — when the autopilot
  does something unexpected (e.g., a sharp turn), pilot
  view makes it obvious whether the aircraft is
  actually pointed at the next waypoint.
- **Don't stay in pilot view during conflicts** — you
  lose the spatial context of the full airspace. Switch
  to chase or free camera to assess.
- **Free camera** — click anywhere on the globe (in
  normal mode) to deselect the aircraft and regain free
  camera control.
