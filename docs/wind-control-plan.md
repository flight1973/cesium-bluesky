# Wind Control — Implementation Plan

## How BlueSky represents wind

BlueSky's `Windfield` class (`bluesky/traffic/windfield.py`) stores
wind as a collection of **scattered definition points**, each with
a full **vertical profile** on a fixed 100 ft altitude grid
(0 → 45,000 ft, 451 levels). There is no single regular grid by
default — horizontal interpolation between points uses
inverse-distance-squared weighting. When a plugin loads gridded
meteorological data (GFS/ECMWF), it populates enough points to
form a regular grid and BlueSky switches to
`scipy.interpolate.RegularGridInterpolator`.

Per-point state:
- `vnorth[nalt, nvec]` — N component (m/s) at each altitude level
- `veast[nalt, nvec]`  — E component (m/s)
- `lat[nvec], lon[nvec]` — position of each definition point
- `winddim` — `0=none, 1=constant, 2=2D, 3=3D`

Per-aircraft state (refreshed every sim step):
- `bs.traf.windnorth[i]`, `bs.traf.windeast[i]` — wind sampled at
  that aircraft's current lat/lon/alt (m/s)

Aircraft physics (`traffic.update_gnd()`):
```
vn, ve = wind.getdata(lat, lon, alt)
applywind = alt > 50 ft
gsnorth   = tas·cos(hdg) + vn·applywind
gseast    = tas·sin(hdg) + ve·applywind
gs        = √(gsnorth² + gseast²)
trk       = atan2(gseast, gsnorth)
```
**TAS is untouched**; wind bends track and scales ground speed.
This is already visible to us — the WCA we just shipped picks up
any wind-induced heading/track split.

## Stack commands we'll wrap

| Command | Purpose |
|---|---|
| `WIND lat lon dir spd` | Uniform / 2D point (no altitude) |
| `WIND lat lon alt₁ dir₁ spd₁ alt₂ dir₂ spd₂ ...` | 3D profile at one point |
| `WIND lat lon DEL` | Clear all wind |
| `GETWIND lat lon [alt]` | Probe wind at a position |
| `WINDGFS lat0 lon0 lat1 lon1 [yyyy mm dd hh]` | Load NOAA GFS |
| `WINDECMWF lat0 lon0 lat1 lon1 [yyyy mm dd hh]` | Load ECMWF ERA5 |

Units — BlueSky accepts **knots** and **°true** for direction and
**feet** for altitude in the `WIND` command argument parser.
Internally everything becomes m/s. Our API and UI must support
**three unit systems**, selectable per-request and per-user:

| System | Speed | Altitude | Direction |
|---|---|---|---|
| **aviation** (default) | kt | ft / FL | °true |
| **si** | m/s | m | °true |
| **imperial** | mph | ft | °true |

- REST bodies accept `{value, unit}` pairs *or* a top-level
  `units: "aviation" | "si" | "imperial"` that applies to all
  scalar fields in the request. Default = `aviation` when absent.
- REST responses mirror whatever the client asked for, with a
  `units` field echoed back for round-trip clarity. Internal
  storage is always m/s and m.
- The UI has a global unit-system toggle (settings panel) that
  controls the defaults everywhere wind values are shown — the
  WIND tab editors and any vector-layer labels.

## Phase 1 — Read access (no sim mutation)

**Backend:** `cesium_app/api/wind.py`

- `GET /api/wind/info` → `{dim, npoints, points: [{lat, lon, has_profile}]}`
  - Reads `bs.traf.wind.winddim`, `.lat`, `.lon`, shapes of `vnorth`.
- `GET /api/wind/sample?lat=..&lon=..&alt=..` →
  `{north_ms, east_ms, dir_deg, speed_kt}`
  - Calls `bs.traf.wind.getdata(np.array([lat]), np.array([lon]),
    np.array([alt*FT]))`, converts vectors to dir/speed.
- `GET /api/aircraft/{acid}/wind` →
  `{north_ms, east_ms, dir_deg, speed_kt, wca_deg}`
  - Reads `bs.traf.windnorth[idx]`, `bs.traf.windeast[idx]`; WCA
    computed from `hdg - trk`.

**Collector extension:** include `windnorth` and `windeast`
arrays in ACDATA so Phase 5's wind-vector layer can render
without extra REST round-trips, and so the aircraft side panel
can show wind without a per-panel REST call.

**Frontend:**
- Aircraft **side panel**: add a `WIND` row below BANK. Format
  `W 270°/28 kt` (met convention — direction wind is *from*),
  or `--` when the wind field is empty at this aircraft's
  position. Respects the global unit-system toggle.
- **Floating aircraft label** (the callsign/FL/speed block on
  the map): **no wind** here. Label stays scannable.

## Phase 2 — Write access (uniform wind first)

**Backend:**

- `POST /api/wind/uniform` — body `{direction_deg, speed_kt}` →
  stacks `WIND 0 0 {dir} {spd}` (position is irrelevant for
  uniform wind; any lat/lon with no altitude becomes the global
  2D field).
- `DELETE /api/wind` → stacks `WIND 0 0 DEL` (clears the field).

**Frontend:** new dedicated **WIND** tab in the toolbar —
sibling to SIM/LAYERS/VIEW/AREAS. Contents:
- Direction slider (0–359°, met convention) + numeric input
- Speed input with unit selector (kt / m/s / mph)
- Altitude selector (optional; leaving it blank = 2D field)
- [SET] + [CLEAR]
- Live readout: current `winddim` and
  sample-at-camera-center shown in the selected unit system
- Eventually (Phase 3) grows to host the point/profile editor;
  (Phase 4) a "Load real weather" sub-section

This gets us 80% of typical use cases (uniform flow for testing
crab angle, conflict geometry under wind, resolution behavior).

## Phase 3 — Point-and-profile editor

**Backend:**

- `POST /api/wind/points` — body `{lat, lon, profile: [{alt_ft?,
  direction_deg, speed_kt}]}` → stacks one `WIND lat lon ...`
  with either flat (2D) or triplet (3D) form.
- `GET /api/wind/profile?lat=..&lon=..` → `{altitudes_ft[],
  direction_deg[], speed_kt[]}` by sampling the field at every
  1000 ft from 0–45,000 ft (indexing `bs.traf.wind.vnorth[:, k]`
  for the nearest-neighbor point is cheap, but prefer calling
  `getdata()` at each altitude for consistency with what aircraft
  actually experience).

**Frontend:**
- Click on map with the WIND tab active → drops a wind pin.
- Sidebar editor shows the point's profile as a small table +
  sparkline. Edit rows, save.
- Existing pins render as Cesium entities (pin icon + labeled
  "WIND") with a right-click delete.

## Phase 4 — Real weather (GFS / ECMWF)

**Backend:**

- `POST /api/wind/load-gfs` — body `{bbox: [lat0, lon0, lat1,
  lon1], datetime_utc?}` → stacks `WINDGFS ...`. Returns
  immediately; plugin loads async and reports progress via a new
  `WINDLOAD` WebSocket topic (plugin already logs to stack echo,
  so piggy-back on the ECHO topic if that's simpler).
- `POST /api/wind/load-ecmwf` — analogous.
- Both require the plugins to be enabled; add
  `GET /api/wind/plugins` → `{gfs_available, ecmwf_available}`
  by testing `bs.plugin.Plugin` registry.

**Frontend:** in the WIND tab, a "Load real weather" section
with bbox drawn on the map, date picker, and [GFS]/[ECMWF]
buttons. Credentials for ECMWF CDS API need a config item — skip
on first pass and document in README.

## Phase 5 — Visualization

Part of the core ask — not optional. Once the field is populated:

- **Wind vector layer** — sample on a camera-follow grid (say
  0.5° × 0.5°) at camera-center altitude and draw short arrows
  with `PolylineCollection`. Redraw on camera-idle + altitude
  slider change.
- **Barb layer** — standard met barbs (pennants = 50 kt, full
  barbs = 10 kt, half = 5 kt) instead of plain arrows. Higher
  fidelity, more work — ship arrows first, barbs as a follow-up.

Toggle under the LAYERS tab. Altitude-for-sampling control
lives in the WIND tab (defaults to camera center altitude, or
camera altitude if looking straight down).

## Phase 6 — Scenario integration

The scenario editor already round-trips stack commands. Nothing
new needed — a user can write `WIND ...` / `WINDGFS ...` into a
`.scn`. Bonus: add a "Save current wind to scenario" helper that
emits `WIND` lines for each point in `bs.traf.wind`.

## Open questions

1. **Met vs aerodynamic direction convention.** BlueSky's `WIND`
   expects the direction wind is **from** (270 = westerly,
   matches METAR convention). The aircraft vector math above uses
   "wind toward" components. Make sure the REST layer and UI
   stick to met convention for humans and convert once at the
   boundary. *(Verify in `windsim.py` — the direction parsing
   may already be from-convention; the storage is clearly
   to-convention via `veast`/`vnorth` being added to TAS.)*
2. **Single global field vs per-aircraft overrides.** BlueSky
   has one global `bs.traf.wind`. That's fine — matches real
   atmosphere. No per-aircraft override endpoint needed.
3. **Units.** Three systems supported (aviation/si/imperial)
   with aviation as the default. Internal storage is always
   m/s + m; conversion happens at the REST boundary.

## Build order

**First PR — Phase 1 + 2 bundled:**
- `cesium_app/api/wind.py` with `GET /info`, `GET /sample`,
  `GET /aircraft/{acid}/wind`, `POST /uniform`, `DELETE /`.
- `windnorth`/`windeast` added to ACDATA.
- Aircraft side panel: new `WIND` row (met convention).
- New **WIND** tab in the toolbar with direction, speed
  (unit-selectable: kt / m/s / mph), optional altitude, SET and
  CLEAR buttons, and a live readout of `winddim` +
  sample-at-camera-center.
- Unit system plumbing: `units` field on REST bodies + global
  unit-system toggle stubbed (defaults to aviation).

**Follow-ups, in order:**
1. Phase 3 (point/profile editor with map pins).
2. Phase 5 (wind-vector layer — arrows first, barbs later).
3. Phase 4 (real weather GFS/ECMWF loaders).
4. Phase 6 (scenario integration — "save wind to scenario").
