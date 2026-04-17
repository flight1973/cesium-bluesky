# Cesium-BlueSky

A modern, browser-based 3D interface for the
[BlueSky CNS/ATM Open Air Traffic Simulator][bluesky]
developed at TU Delft. Cesium-BlueSky wraps BlueSky's
battle-tested simulation engine in a FastAPI + CesiumJS web
application, and adds the instrumentation, visualization,
and editing tools needed to use the sim as a **virtual twin
of the airspace** rather than a standalone research tool.

[bluesky]: https://github.com/TUDelft-CNS-ATM/bluesky

## What this is

BlueSky is the simulation core — aircraft dynamics, flight
management, conflict detection, resolution algorithms, nav
database, stack-command language, 123+ commands. It runs
untouched, in-process, in a background thread.

On top of that, Cesium-BlueSky adds:

- **A 3D globe interface** (CesiumJS) replacing BlueSky's
  pygame / Qt GUIs — satellite and terrain imagery,
  realistic altitude scaling, chase / pilot-seat camera
  modes, 2D / 3D toggle, scale bar, camera tilt readouts.
- **Faithful airspace visualisation** — aircraft with
  heading / track / bank rendering, protected-zone (PZ)
  cylinders as 3D volumes, conflict and loss-of-separation
  colouring, velocity vectors, trails, route lines with
  waypoint constraints, deletion-area polygons.
- **A tabbed control panel** covering simulation lifecycle,
  layer toggles, view preferences, area tools, and wind.
- **A text-mode scenario editor** with versioning (`_v2`,
  `_v3`, …) — scenarios are plain `.scn` files, editable
  and diffable.
- **A wind-control system** (in progress) — uniform wind,
  point / profile editor, live readout of the field and
  real-weather loading from NOAA GFS / ECMWF forecasts.
- **Aviation, SI, and Imperial units** — global toggle
  under the settings gear, applied wherever speeds or
  distances are shown.
- **REST + WebSocket API** for every sim operation, so the
  same engine can be driven by a browser, a scripted
  client, or a voice-command frontend (planned).

## Virtual twin goals

The direction of the project is to turn the BlueSky sim
into a high-fidelity digital replica of real-world
airspace. That means closing the gap between simulation
behaviour and what you'd see if you were looking at the
same airspace through real sensors:

- **Realistic physics** — heading vs track with wind
  correction, bank-dependent turn rate, real altitude /
  density effects on airspeed, true indicated airspeed
  modelling (planned).
- **Real weather** — GFS / ECMWF forecast ingestion so
  scenarios can reproduce actual conditions on a given
  date.
- **Voice ATC** (planned) — voice commands with aircraft
  readback, for the controller workflow.
- **Versioned scenarios** that can be committed, diffed,
  replayed, and shared.
- **Great-circle / geodesic routing** (to audit) — the
  sim's routing logic needs to match real-world
  navigation, not flat-earth shortcuts.

## Architecture

```
┌─────────────────────────────┐   ┌──────────────────────┐
│  Browser (CesiumJS + Lit)   │   │  Upstream BlueSky    │
│  ── 3D globe viewer         │   │  (TUDelft-CNS-ATM)   │
│  ── Tabbed toolbar          │   │                      │
│  ── Aircraft / FMS panels   │   │  ── Traffic arrays   │
│  ── Scenario editor         │   │  ── Stack commands   │
│  ── Settings / units        │   │  ── Nav database     │
└────────┬──────────┬─────────┘   │  ── Conflict detect. │
         │ REST     │ WS          │  ── Autopilot / FMS  │
         ▼          ▼             │  ── Wind field       │
┌─────────────────────────────┐   │                      │
│  FastAPI (cesium_app)       │   └──────────┬───────────┘
│  ── /api/sim, traffic, ...  │              │ in-process
│  ── /api/wind, areas, ...   │◀─────────────┘
│  ── /ws/sim (ACDATA, ...)   │
│  ── SimBridge: sim thread   │
│  ── StateCollector: ACDATA  │
└─────────────────────────────┘
```

BlueSky is imported as a git submodule under `bluesky/` and
initialised in `detached` mode — no ZMQ networking, no Qt.
The FastAPI layer reads sim state directly from `bs.traf` /
`bs.sim` arrays; commands go through the standard
`bluesky.stack.stack()` entry-point, which is monkey-patched
to log every command (REST, WebSocket, scenario file) into
a rolling audit trail.

## Running

Service style (auto-restart, daemon):

```
uvicorn cesium_app.main:app --host 0.0.0.0 --port 8000
```

Or via the included systemd unit / launchd plist:

- `cesium-bluesky.service` — Linux systemd
- `com.cesium-bluesky.plist` — macOS launchd

The frontend builds to `cesium_app/static/` via Vite and is
served by FastAPI on the same port. For dev, run
`npm run dev` from `frontend/` for hot reload; the dev
server proxies `/api` and `/ws` to the FastAPI backend.

A Cesium Ion token is **optional** — the UI falls back to
open basemaps (CARTO dark, Stamen) when no token is set.
The [Set Ion Token] button in the VIEW tab upgrades to
Bing aerial + Cesium World Terrain if you provide one.

## Project layout

```
cesium-bluesky/
├── bluesky/              # Upstream BlueSky (submodule)
├── cesium_app/           # FastAPI service
│   ├── api/              # REST routers
│   ├── sim/              # SimBridge, StateCollector
│   ├── ws/               # WebSocket broadcast
│   └── static/           # Built frontend artifacts
├── frontend/             # CesiumJS + Lit SPA
│   └── src/
│       ├── cesium/       # Viewer, entities, click
│       ├── services/     # WS, REST, units
│       ├── ui/           # Lit components (panels/tabs)
│       └── types/
└── docs/                 # Design plans & notes
```

## Status

This is an active research / tooling project. Core
simulation behaviour is fully functional; the 3D interface,
scenario editor, and wind-control system are being built
iteratively. See `docs/` for per-feature design documents
(smooth-banking-plan.md, wind-control-plan.md, …) and open
questions.

## Credits

BlueSky is © TU Delft CNS/ATM group and contributors,
licensed under GPL-3.0. This project is a web-interface
layer on top of that work and carries the same license.
See `bluesky/LICENSE` and the [BlueSky paper][paper] for
details on the underlying simulation.

[paper]: https://doi.org/10.2514/6.2016-3842
