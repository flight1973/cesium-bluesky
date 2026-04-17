# Wind

BlueSky models wind as a **3D scalar field** sampled
every simulation step at each aircraft's position. The
sampled wind vector is added to the aircraft's true
airspeed to produce ground speed and track, leaving TAS
itself unchanged.

This page covers how it works internally. For the
browser-based wind control plan, see
[Wind Control](/docs/plans/wind-control).

## Data structure

`bs.traf.wind` is a **`Windfield`** instance
(`bluesky/traffic/windfield.py`) storing scattered
lat/lon definition points, each with a full vertical
profile:

- **Altitude grid**: fixed 100 ft resolution,
  0 → 45,000 ft (451 levels).
- **Definition points**: arbitrary lat/lon positions.
  You can have 1 (uniform wind), a handful, or
  hundreds.
- **Components per point**: `vnorth[nalt, nvec]`,
  `veast[nalt, nvec]` — north and east wind in m/s at
  each altitude level for each point.

The **`winddim`** attribute tells you the field's shape:

| Value | Meaning |
|---|---|
| 0 | No wind defined |
| 1 | Single point (effectively uniform) |
| 2 | 2D field (multiple points, altitude-independent) |
| 3 | 3D field (points have vertical profiles) |

## Setting wind — stack commands

```
WIND lat lon dir spd                         # 2D point (no altitude)
WIND lat lon alt₁ dir₁ spd₁ alt₂ dir₂ spd₂   # 3D profile at one point
WIND lat lon DEL                             # clear all wind
GETWIND lat lon [alt]                        # probe the field
```

- `dir` — direction wind is coming **from**, in degrees
  true (METAR convention). 270 = westerly.
- `spd` — knots.
- `alt` — feet.

For a uniform westerly at 30 kt everywhere:
```
WIND 0 0 270 30
```
The lat/lon arguments are required but irrelevant when
the field is 2D with only one point — BlueSky applies it
globally.

## Real weather — plugin loaders

Two plugins load real forecast data:

- **`WINDGFS`** — NOAA Global Forecast System. Loads a
  bounding box at a specific UTC.
  ```
  PLUGIN LOAD WINDGFS
  WINDGFS 35 -10 55 15 2024 1 15 12   # Europe, Jan 15 2024 12:00 UTC
  ```
- **`WINDECMWF`** — ECMWF ERA5 reanalysis (requires CDS
  API credentials).
  ```
  PLUGIN LOAD WINDECMWF
  WINDECMWF 35 -10 55 15 2024 1 15 12
  ```

Both plugins populate the `Windfield` with enough points
to form a regular grid, at which point BlueSky switches
to `scipy.interpolate.RegularGridInterpolator` for
efficient queries. They auto-reload every hour while
active, so long-running simulations track a realistic
evolving atmosphere.

## What aircraft feel

Each step, in `Traffic.update_gnd()`:

```python
vn, ve = self.wind.getdata(self.lat, self.lon, self.alt)
self.windnorth[:], self.windeast[:] = vn, ve
applywind = self.alt > 50 * ft      # only above 50 ft AGL

self.gsnorth = self.tas * cos(hdg) + vn * applywind
self.gseast  = self.tas * sin(hdg) + ve * applywind
self.gs      = sqrt(gsnorth² + gseast²)
self.trk     = atan2(gseast, gsnorth)
```

Key properties:

- **TAS is invariant** — wind doesn't change true
  airspeed. The aircraft's engine/performance model is
  unaffected.
- **GS and track are modified** — ground speed is the
  vector sum of TAS (in heading direction) and wind;
  track is the direction of that sum vector.
- **Not applied below 50 ft AGL** — avoids spurious wind
  during takeoff/landing where nothing physical is yet
  responding to it.
- **All aircraft, every step** — vectorized numpy
  operation; negligible cost regardless of fleet size.

The per-aircraft sample is exposed at
`bs.traf.windnorth[i]` / `bs.traf.windeast[i]` and ships
on the ACDATA WebSocket frame as parallel arrays.

## Heading, track, and crab

Wind is the reason `hdg` and `trk` diverge. In calm air
they're equal. With wind, the aircraft must **crab** —
point its nose into the wind slightly — to fly the
desired track:

```
wca = hdg - trk       (wind correction angle)
```

For a cruise aircraft at 250 kt TAS with a 50 kt
crosswind from the west:
```
wca = asin(50 / 250) ≈ 11.5°
```
Flying a 090° track requires heading ~101.5° (nosing into
the westerly).

Cesium-BlueSky's aircraft side panel shows this
explicitly: `H101° / T090° (WCA 11°R)` when non-trivial,
or just `090°` when calm.

## Interpolation

`Windfield.getdata(lat, lon, alt)` interpolates:

- **3D regular grid** (plugin-loaded data) — uses
  `RegularGridInterpolator` for trilinear interpolation.
  `fill_value=0` outside the loaded bounds — aircraft
  outside the bbox get no wind, not extrapolated wind.
- **2D scattered points** (multiple `WIND` commands) —
  inverse-distance-squared weighting horizontally;
  altitude interpolation via each point's fixed
  altitude column.
- **1D (constant)** — all positions get the same vector,
  independent of altitude.
- **0D (none)** — returns zeros.

The altitude axis is fixed at 100 ft spacing, which is
fine for most aircraft physics but coarse for boundary-
layer phenomena. BlueSky isn't a meteorological
simulator — the wind field exists to make aircraft
ground-speed modeling realistic, not to study weather.

## REST API (Cesium-BlueSky)

Cesium-BlueSky wraps the commands with a small REST
surface — see the [Wind Control
plan](/docs/plans/wind-control) for the full design, but
the key endpoints are:

- `GET /api/wind/info` — field dimension and
  definition-point summary.
- `GET /api/wind/sample?lat=..&lon=..&altitude_ft=..` —
  probe any position.
- `GET /api/wind/aircraft/{acid}` — wind sampled at a
  specific aircraft (what it actually felt).
- `POST /api/wind/uniform` — set a uniform global wind.
- `DELETE /api/wind` — clear the field.

All accept a `units` selector (`aviation`, `si`,
`imperial`) and always use METAR "from" direction
convention.

## Related reading

- [Simulation Overview](/docs/simulation-overview) — per-
  step physics context.
- [Autopilot & FMS](/docs/autopilot) — why wind causes
  HDG ≠ TRK.
- [Wind Control plan](/docs/plans/wind-control) —
  browser UI design.
