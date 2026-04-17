# Cesium-BlueSky Documentation

Welcome. This site documents **Cesium-BlueSky** — a
modern, browser-based 3D virtual-twin interface for the
[BlueSky CNS/ATM Open Air Traffic Simulator][bluesky]
developed at TU Delft. The BlueSky simulation engine runs
untouched; we wrap it in a FastAPI + CesiumJS web
application and add the visualizations, editors, and
controls that make it a practical airspace twin.

[bluesky]: https://github.com/TUDelft-CNS-ATM/bluesky

## What's here

### Using the interface

How to drive Cesium-BlueSky as a user — the tabs,
panels, shortcuts, and visualizations we've built on top
of BlueSky:

- [**Getting Started**](/docs/interface/getting-started) —
  a 5-minute tour of the interface.
- [**Viewer & 3D Globe**](/docs/interface/viewer) — 3D
  vs. 2D, navigation, imagery, terrain.
- [**Toolbar & Tabs**](/docs/interface/toolbar) — SIM,
  LAYERS, VIEW, AREAS, WIND.
- [**Aircraft Panel**](/docs/interface/aircraft-panel) —
  HDG/TRK/WCA, BANK, WIND, IAS/CAS/GS, and autopilot
  SET controls.
- [**Scenario Editor**](/docs/interface/scenario-editor) —
  text-mode editing with versioning.
- [**Area Tools**](/docs/interface/area-tools) — drawing
  BOX, POLY, and CIRCLE deletion areas.
- [**Camera Modes**](/docs/interface/camera-modes) —
  chase and cockpit (pilot) views.
- [**Layers**](/docs/interface/layers) — trails, routes,
  labels, velocity vectors, PZ rings, airports,
  waypoints.
- [**Settings & Units**](/docs/interface/settings) — the
  gear menu, aviation/SI/imperial units.
- [**Visual Conventions**](/docs/interface/visual-conventions) —
  colors, label formats, and what every on-screen
  symbol means.

### BlueSky concepts

How the underlying simulator works:

- [**Simulation Overview**](/docs/simulation-overview) —
  main loop, time, traffic arrays.
- [**Stack Commands**](/docs/stack-commands) — the
  command language, aliases, dispatch.
- [**Scenario Files**](/docs/scenario-files) — `.scn`
  format and playback.

### BlueSky systems

- [**Autopilot & FMS**](/docs/autopilot) — LNAV, VNAV,
  selected values.
- [**Conflict Detection & Resolution**](/docs/asas) —
  ASAS, protected zones, CPA.
- [**Resolution Methods**](/docs/reso-methods) — MVP,
  EBY, SSD.
- [**Wind**](/docs/wind) — how BlueSky models wind.

### API reference

For scripting and building custom clients:

- [**REST Endpoints**](/docs/api/rest) — every `/api/*`
  route with request / response shape.
- [**WebSocket Protocol**](/docs/api/websocket) —
  topics, message format, subscription model.

### Live reference — auto-generated

Pulled from the running sim, so always up to date:

- [**Commands**](/docs/ref/commands) — every stack
  command including plugin-added ones.
- [**Resolvers**](/docs/ref/resolvers) — active and
  available RESO classes.
- [**Detectors**](/docs/ref/detectors) — active and
  available CD classes.
- [**Plugins**](/docs/ref/plugins) — loaded vs.
  available plugins.

### Plans & design notes

Working notes for features in progress:

- [Smooth Banking](/docs/plans/smooth-banking)
- [Wind Control](/docs/plans/wind-control)

## About this project

Cesium-BlueSky is a research / tooling project. Our goal
is to turn BlueSky from a standalone simulator into a
**virtual twin of the airspace** — a high-fidelity
digital replica you can drive, edit, visualize in 3D,
and connect to real weather and real scenarios.

The simulation physics are unchanged — BlueSky does that
job well. What we add:

- A modern 3D browser interface with realistic
  altitude-scaled rendering, protected-zone volumes,
  conflict / LoS coloring, trails, routes, and
  waypoint constraint display.
- Tabbed controls so the common operations (run/hold,
  scenario switch, layer toggles, area drawing, wind
  setting) are always one click away.
- A text-mode scenario editor with version tracking so
  scenarios are plain `.scn` files you can edit, diff,
  and commit.
- A REST + WebSocket API so the same sim can be driven
  by a browser, a script, or a future voice-ATC layer.
- Aviation / SI / Imperial unit selection applied
  uniformly everywhere speeds or distances are shown.
- This documentation site itself — a web-rendered
  reference that grows as we add features.

BlueSky is © TU Delft CNS/ATM group, licensed under
GPL-3.0. The simulation foundation is documented in
their [paper][paper]. This project is a web-interface
layer built on top under the same license.

[paper]: https://doi.org/10.2514/6.2016-3842
