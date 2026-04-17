# Area Tools

BlueSky supports **deletion areas** — 2D shapes with
optional altitude bands that define the boundary of the
simulated airspace. Any aircraft leaving the active area
is automatically deleted. Cesium-BlueSky adds a graphical
drawing toolbar so you can sketch areas directly on the
globe.

Enable by selecting the **AREAS tab** in the main
toolbar — the area-drawing toolbar appears separately
underneath.

## Area types

### BOX — axis-aligned rectangle

Click two corners on the globe. BlueSky creates an
axis-aligned rectangle spanning lat/lon bounds.

Stack equivalent: `BOX <name>,<lat1>,<lon1>,<lat2>,<lon2>`.

### POLY — polygon

Click vertices in sequence; **double-click** to close
the polygon. Minimum 3 vertices. Polygon winding can be
clockwise or counter-clockwise.

Stack equivalent: `POLY <name>,<lat1>,<lon1>,<lat2>,<lon2>,...`.

### CIRCLE — circular area

Click the center, then a second point on the
circumference (radius picked by the distance between
clicks).

Stack equivalent:
`CIRCLE <name>,<lat>,<lon>,<radius_nm>`.

## Altitude band

Every shape can have an **optional altitude band** —
top and bottom altitudes that limit the 3D volume:

- Without a band: the area is an infinite vertical
  column (bottom = 0, top = Kármán line at 100 km).
- With a band: a finite altitude slab, useful for
  sector volumes (e.g., `FL100–FL200`).

The area toolbar has **Top** and **Bottom** inputs that
accept `FL350`, `35000`, `10000ft`, etc. Leave blank
for no limit.

Cesium-BlueSky renders areas as 3D volumes in the
viewer, so the altitude band is visibly enforced — you
can tell from the geometry alone where the area starts
and ends vertically.

## Activating an area

Drawing a shape defines it but doesn't activate
deletion. Two activation paths:

1. **Create + activate in one step** — tick the
   "activate after drawing" checkbox before you draw.
2. **Create, then activate later** — click the shape's
   name in the areas panel and pick **Activate**.

When active, `bs.traf` deletes any aircraft leaving the
shape each tick. Stack equivalent: `AREA <name>`;
`AREA OFF` deactivates without deleting the shape.

Only **one area is active** at a time — activating a new
one automatically deactivates the previous.

## Visual rendering

- **Defined area** — semi-transparent cyan fill with a
  darker cyan outline.
- **Active area** — same, but the outline is brighter
  and pulsed.
- **Rendering is 3D** — top and bottom surfaces are
  drawn at the configured altitudes, so you can see the
  volume from any camera angle.

Areas remain visible when the AREAS tab is not active —
they're a globe feature, not a tab-scoped overlay.

## Areas panel (list view)

Click **Areas Panel** (or the manage button in the area
toolbar) to open a sidebar listing every shape:

- Shape name, type (BOX / POLY / CIRCLE), altitude band.
- **Activate / Deactivate** per shape.
- **Delete** — removes the shape (`DEL <name>`).

## REST API

The full CRUD surface is at `/api/areas/*`:

- `GET /api/areas` — list all shapes + active area.
- `POST /api/areas/box` / `poly` / `circle` — create a
  shape; `activate: true` in the body also activates it.
- `POST /api/areas/activate` — set the active shape.
- `POST /api/areas/deactivate` — turn off deletion
  (shape stays defined).
- `DELETE /api/areas/{name}` — remove a shape.

See [REST Endpoints](/docs/api/rest) for full details.

## Persistence

Areas are **sim-local state**. They're reset whenever
the sim resets (button, `RESET` command, or `IC` of a
scenario). To make an area persistent:

- Put the shape definitions at `00:00:00.00` in a
  scenario file, or
- Save the shape via the backend and programmatically
  recreate on reset.

## Typical workflow

1. Select the **AREAS tab**.
2. Pick **BOX** in the area toolbar.
3. Enter a name (e.g., `SECTOR1`).
4. Optionally set top / bottom altitudes.
5. Tick **activate after drawing** if you want deletion
   enabled immediately.
6. Click two corners on the globe.
7. The shape appears; if activated, aircraft straying
   outside will be deleted.

## Tips

- **Use big margins** — drawing tight to traffic causes
  spurious deletions when aircraft turn near the
  boundary. Give ~10 NM buffer.
- **Name meaningfully** — names appear in the console,
  logs, and scenario files. `SECTOR_EHAM_UPPER` beats
  `AREA1`.
- **Versionable via scenarios** — if you want a
  reproducible airspace boundary, put the `BOX` /
  `POLY` / `CIRCLE` command into a scenario file.
