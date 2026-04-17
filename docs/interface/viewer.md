# Viewer & 3D Globe

The central viewer is a [CesiumJS][cesium] scene
rendering aircraft, routes, protected zones, and any
active areas on a 3D globe. It supports 3D (perspective)
and 2D (top-down) modes and exposes navigation,
imagery, and terrain controls from the **VIEW tab** of
the toolbar.

[cesium]: https://cesium.com/platform/cesiumjs/

## 3D vs 2D

Click the **2D / 3D** button in the VIEW tab to swap
scene modes:

- **3D** (default) — full globe with altitude-scaled
  aircraft and perspective camera. Best for visualizing
  vertical separation and climb/descent profiles.
- **2D** — orthographic top-down, like a traditional
  radar display. Altitudes are flattened — useful for
  pure horizontal geometry.

All visualization layers work in both modes.

## Navigation

Mouse controls:

| Action | Effect |
|---|---|
| **Left-drag** | Pan the camera |
| **Right-drag / middle-drag** | Tilt / rotate |
| **Wheel** | Zoom in / out |
| **Left-click aircraft** | Select aircraft (fly to + panel) |
| **Left-click globe** | Deselect (in normal mode) |
| **Left-click globe** | Add vertex (in area-drawing mode) |
| **Double-click** | Finish area drawing |

The **camera-controls** overlay (bottom-left of the
viewer) shows the current tilt angle and camera altitude,
with buttons to tilt straight down or reset to the
default oblique view.

The **scale bar** (bottom-right) shows distance per pixel
at the current zoom, automatically switching units to
match the selected unit system.

## Altitude exaggeration

Aircraft altitudes are in feet, but the globe is hundreds
of kilometers across. At true scale, a 35,000-ft cruise
is visually indistinguishable from the surface. The
**Alt Exag** slider in the VIEW tab multiplies the
displayed altitude by 1–50× (default **10×**) so
vertical separation is actually visible.

Aircraft positions for conflict detection, routes, and
all physics remain at true altitude — exaggeration is
purely visual.

## Imagery

The **Imagery** dropdown in the VIEW tab picks the
satellite / map layer rendered on the globe:

- **CARTO Dark** (default, no Ion token needed) —
  neutral dark basemap, easy on the eyes.
- **CARTO Light** — light basemap variant.
- **Bing Aerial** — high-resolution satellite imagery
  (requires Cesium Ion token).
- **Bing Aerial with Labels** — as above with place
  names.

When no Ion token is configured, the Ion-required
options are visible but greyed out.

## Terrain

The **Terrain** dropdown offers:

- **Flat** (default) — ellipsoid only, no terrain.
  Fastest, and matches what BlueSky's autopilot assumes.
- **Cesium World Terrain** — global elevation data
  (requires Ion token).

Terrain is cosmetic — BlueSky's aircraft physics don't
interact with terrain height. Aircraft at `FL050` are
drawn at 5,000 ft above the ellipsoid regardless of
mountains below.

## Cesium Ion token

Some imagery / terrain options require a free Cesium
Ion account:

1. Click **Set Ion Token** in the VIEW tab.
2. Paste your token (get one at <https://ion.cesium.com/>).
3. The page upgrades the dropdown options.

The token is stored in `localStorage`, so it persists
across reloads. Cesium-BlueSky is fully functional
without Ion — the Ion integration is an opt-in upgrade.

## Default view

On load, the camera starts over **EHAM (Amsterdam
Schiphol)** at roughly 300 km altitude, looking straight
down. To reset back to this view, pick **RESET** in the
SIM tab, then click anywhere on the globe to clear
selection.

When you select an aircraft, the camera flies to it at
~100 km altitude, straight down. When you pick a
[camera mode](/docs/interface/camera-modes), the camera
attaches to the aircraft and updates on every frame.

## Visual layers

What the globe can show is governed by the
[LAYERS tab](/docs/interface/layers):

- Aircraft icons (always on).
- Trails, routes, labels, velocity vectors.
- PZ cylinders (green / orange / red).
- Airport and waypoint markers.
- Deletion-area polygons.

## Performance

At 5 Hz ACDATA updates with a few hundred aircraft,
Cesium renders smoothly on modern laptops. Above ~2,000
aircraft you'll see the frame rate drop because every
aircraft is a separate entity — a future optimization
would be to batch them with `PointPrimitiveCollection` /
`BillboardCollection`. For the research scale BlueSky is
typically used at, current rendering is comfortable.
