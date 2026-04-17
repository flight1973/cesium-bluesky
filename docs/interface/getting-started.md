# Getting Started

A 5-minute tour of Cesium-BlueSky.

## Launch

Start the service:

```
uvicorn cesium_app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` in a browser. You should
see:

- A **3D globe** in the center (the main viewer).
- A **toolbar** in the top-left corner with tabs
  `SIM / LAYERS / VIEW / AREAS / WIND`.
- A **traffic list** sidebar on the right (empty until
  aircraft exist).
- A **status bar** at the bottom showing sim time, UTC,
  speed multiplier, aircraft count, and conflict / LoS
  counters.
- A **command console** below the status bar for typing
  raw stack commands.
- A **settings gear ⚙** top-right with unit-system
  toggle and a link to these docs.

## Run a demo scenario

In the **SIM tab**:

1. Click the **Scenario…** dropdown and pick `demo.scn`
   (or any other scenario). The sim resets and loads it.
2. Click **OP** to start the simulation.
3. Watch aircraft appear on the globe and in the
   traffic list.
4. Click **HOLD** to pause, **RESET** to clear.

The **Speed** dropdown picks a wall-clock multiplier —
`1×` is real time, `5×` runs five seconds of sim per
second of wall time, and so on. Useful for watching a
long flight without waiting for it.

## Select an aircraft

Click any aircraft on the globe, or click a row in the
traffic list. The camera flies to it, a **magenta route
line** appears if the aircraft has an FMS route, and the
**aircraft panel** slides in from the right showing:

- Callsign and type (e.g., `KL204 B738`).
- Origin → destination.
- **HDG** (heading vs. track with wind correction),
  **ALT**, **SPD**, **VS** — each with a current value
  on the left, a selected-value input with **SET**
  button for autopilot targets.
- **BANK** angle with direction arrow.
- **WIND** sampled at the aircraft (METAR convention).
- **IAS**, **CAS**, **GS** — the three airspeed
  readouts.
- **LNAV / VNAV / FMS** buttons — toggle the autopilot
  modes or open the FMS panel.
- **CHASE / PILOT** buttons — attach the camera to the
  aircraft in 3rd-person or cockpit view.
- A **route** section listing all waypoints with
  altitude / speed constraints; active waypoint
  highlighted.

See [Aircraft Panel](/docs/interface/aircraft-panel) for
the full details.

## Layer toggles

The **LAYERS tab** has buttons for every visualization
layer — click to toggle:

- **TRAIL** — trailing cyan lines behind each aircraft
  (requires the sim to record trails).
- **ROUTE** — the magenta FMS route of the selected
  aircraft.
- **LABEL** — floating callsign / FL / speed labels.
- **VEL VECTOR** — 1-minute velocity leader lines.
- **PZ** — 3D protected-zone cylinders (green / orange
  / red by conflict state).
- **APT** — airport markers.
- **WPT** — waypoint markers.

## Unit system

Click the gear **⚙** in the top-right. Under **Units**
pick one of:

- **Aviation** (default) — knots, feet, flight levels.
- **SI** — m/s, meters.
- **Imperial** — mph, feet.

The choice is remembered between sessions. Every speed
shown in the app updates immediately.

## Next steps

- [**Toolbar & Tabs**](/docs/interface/toolbar) — every
  control in every tab.
- [**Aircraft Panel**](/docs/interface/aircraft-panel) —
  the full panel breakdown.
- [**Scenario Editor**](/docs/interface/scenario-editor) —
  build and version your own scenarios.
- [**Area Tools**](/docs/interface/area-tools) — draw
  deletion boxes / polygons / circles.
- [**Visual Conventions**](/docs/interface/visual-conventions) —
  what every color and symbol means.

Or jump straight to the underlying simulator in
[Simulation Overview](/docs/simulation-overview).
