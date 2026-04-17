# Toolbar & Tabs

The toolbar lives in the top-left of the viewer and
groups controls by purpose. Tabs along the top switch
between control groups; only the active tab's row is
visible at any time.

Tabs: **SIM · LAYERS · VIEW · AREAS · WIND**

## SIM

Simulation lifecycle and scenario control.

| Control | Purpose |
|---|---|
| **OP** | Run the simulation (green when running). |
| **HOLD** | Pause the simulation (green when held). |
| **RESET** | Clear all aircraft, routes, trails, and areas. Also clears the aircraft panel, FMS panel, and renders. |
| **Scenario…** | Dropdown of available `.scn` files grouped by source. Picking one runs `IC <filename>` and resets first. |
| **Speed** | Wall-clock multiplier: `0.5× / 1× / 2× / 5× / 10× / 20×`. |
| **EDIT SCENARIO** | Opens the scenario editor. |
| **ASAS ON/OFF** | Toggles conflict detection. Green when active. Tooltip shows the active CD method. |
| **RESO** | Dropdown for the active resolution method (OFF / MVP / plugin-loaded methods). |
| **+ Load plugin…** | (Conditional) Dropdown listing RESO plugins that can be loaded — picking one sends `PLUGIN LOAD <name>`. |

The scenario dropdown syncs with the running scenario
name in SIMINFO — if a scenario is loaded via console or
another client, the dropdown updates automatically.

See [Conflict Detection & Resolution](/docs/asas) for
what ASAS and RESO actually do, and
[Resolution Methods](/docs/reso-methods) for the
algorithms.

## LAYERS

Toggles for the visualization layers. Each button shows
as "on" (green border) or "off" (grey border); click to
toggle:

| Layer | What it shows |
|---|---|
| **TRAIL** | Cyan trailing polylines behind each aircraft (needs `TRAIL ON` in the sim — the button handles that). |
| **ROUTE** | Magenta FMS route of the selected aircraft. |
| **LABEL** | Floating callsign / flight-level / speed blocks next to each aircraft. |
| **VEL VECTOR** | Velocity vector leader lines projecting 1 minute ahead of each aircraft. |
| **PZ** | 3D protected-zone cylinders around each aircraft. Color reflects conflict state. |
| **APT** | Airport markers (zoom-filtered). |
| **WPT** | Waypoint markers (zoom-filtered). |

For each layer's visual conventions see
[Visual Conventions](/docs/interface/visual-conventions).

## VIEW

Camera and environment controls.

| Control | Purpose |
|---|---|
| **2D / 3D** | Toggle orthographic vs. perspective scene. |
| **Alt Exag** | Vertical exaggeration multiplier (1–50×, default 10×). |
| **Imagery** | Basemap selector (CARTO dark, Bing aerial, …). Ion-gated options are greyed out without a token. |
| **Terrain** | Terrain selector (flat, Cesium World Terrain). |
| **Set Ion Token** | Enter a Cesium Ion access token to unlock premium imagery / terrain. Button shows `Ion ✓` when a token is set. |

See [Viewer & 3D Globe](/docs/interface/viewer) for
navigation controls and camera behavior.

## AREAS

The AREAS tab shows a hint; the actual area-drawing
toolbar appears separately in the viewer when this tab
is active. Use it to draw **BOX**, **POLY**, and
**CIRCLE** deletion areas.

See [Area Tools](/docs/interface/area-tools) for the
full drawing workflow.

## WIND

Wind control.

| Control | Purpose |
|---|---|
| **From: __°** | Wind direction in degrees true, METAR convention (wind comes from this direction). |
| **Speed: __** | Wind speed, in the unit system's native speed unit (kt / m/s / mph). Label updates with unit system. |
| **Alt (ft, blank=all):** | Optional altitude in feet. Leave blank for 2D (altitude-independent) wind. |
| **SET** | Submit the wind. Issues `WIND 0 0 [alt] dir spd` to the sim. |
| **CLEAR** | Clear all wind (`WIND 0 0 DEL`). |

A small readout on the right shows the current field's
state: `(no wind)`, `constant field, 1 pt`, etc.

Wind is always entered / displayed using **METAR
convention** — the direction the wind is *coming from*,
not the direction it's blowing to. So `270°/30` means
a 30-unit westerly wind.

See [Wind](/docs/wind) for how BlueSky uses this input
internally, and [Wind Control](/docs/plans/wind-control)
for the plan for the point/profile editor and GFS/ECMWF
integration.

## Backend state polling

Every ~2 seconds the toolbar polls `GET /api/state` and
resyncs:

- Trail layer on/off flag.
- ASAS method name + available methods.
- RESO method name + available methods.
- List of RESO plugins available but not loaded.

So if a command issued elsewhere (console, scenario
file, another browser tab) changes any of these, the
toolbar button states catch up on the next poll.
