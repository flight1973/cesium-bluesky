# REST Endpoints

Cesium-BlueSky exposes a JSON REST API for every
sim operation. All endpoints accept and return JSON
(Pydantic-validated for typed routes). Prefix for all
routes: `/api`.

## Health

### `GET /api/health`

Service health check. Used by monitoring and load
balancers.

**Response:**
```json
{"status": "healthy", "sim_running": true}
```

### `GET /api/config/cesium`

Returns the configured Cesium Ion token (if any). The
frontend uses this to decide whether to enable Ion
imagery / terrain.

**Response:** `{"ion_token": "..."}` or
`{"ion_token": null}`.

## Simulation control

### `POST /api/sim/op`

Start / resume the simulation. Equivalent to stack `OP`.

### `POST /api/sim/hold`

Pause the simulation. Equivalent to stack `HOLD`.

### `POST /api/sim/reset`

Reset the simulation — deletes all aircraft, clears
routes, trails, areas. Equivalent to stack `RESET`.

### `POST /api/sim/ff`

Fast-forward the simulation.

**Body:** `{"seconds": 60}` — advance 60 sim seconds
as fast as possible. Omit for "until next event."

### `POST /api/sim/dtmult`

Set the wall-clock speed multiplier.

**Body:** `{"multiplier": 5.0}` — run at 5× real time.

### `GET /api/sim/info`

Current simulation state.

**Response:**
```json
{
  "simt": 450.0,
  "simdt": 0.05,
  "utc": "2026-04-13 00:07:30",
  "dtmult": 1.0,
  "ntraf": 12,
  "state": 1,
  "state_name": "OP",
  "scenname": "demo"
}
```

## State flags

### `GET /api/state`

Backend toggle state for UI synchronization. Polled by
the toolbar every 2 seconds.

**Response:**
```json
{
  "trails_active": true,
  "area_active": "SECTOR1",
  "asas_method": "STATEBASED",
  "asas_methods": ["OFF", "STATEBASED", "CSTATEBASED"],
  "reso_method": "MVP",
  "reso_methods": ["OFF", "MVP"],
  "reso_plugins_available": ["EBY", "SSD"]
}
```

## Commands

### `POST /api/commands`

Submit a raw stack command.

**Body:** `{"command": "HDG KL204 090"}`

**Response:**
```json
{
  "success": true,
  "command": "HDG KL204 090",
  "message": "Command queued"
}
```

The command is queued on the sim thread. The reply
is an acknowledgement, not the sim's response — to
see the sim's echo, subscribe to the `ECHO` WebSocket
topic.

### `GET /api/commands/list`

All registered stack commands with brief, docstring,
and argument annotations.

### `POST /api/cmd/{name}`

Typed endpoint per command, auto-generated from the
registry. `name` can be any canonical name or alias.

**Example:** `POST /api/cmd/HDG`
with body `{"args": ["KL204", 90]}` →
stacks `HDG KL204 90`.

## Command log

### `GET /api/cmdlog?limit=100`

Rolling audit log of every command submitted to
`bluesky.stack.stack()` from **any** source (REST,
WebSocket, scenario file, internal BlueSky code).
Default limit 100, max 500.

**Response:** list of
```json
{
  "simt": 123.45,
  "utc": "2026-04-13T00:02:03",
  "sender": "local",
  "command": "HDG KL204 090"
}
```

Also available as the `CMDLOG` WebSocket topic (live
stream).

## Aircraft

### `GET /api/aircraft`

Snapshot of all traffic arrays.

**Response:**
```json
{
  "id": ["KL204", "BA815"],
  "lat": [52.3, 52.1],
  "lon": [4.8, 5.2],
  "alt": [10668.0, 10668.0],
  "tas": [128.6, 128.6],
  "cas": [115.4, 115.4],
  "gs": [132.5, 132.5],
  "trk": [90.0, 270.0],
  "vs": [0.0, 0.0]
}
```

### `GET /api/aircraft/{acid}`

Single aircraft basic state.

### `GET /api/aircraft/{acid}/detail`

Full aircraft detail including autopilot selected
values, bank, wind, and FMS route.

### `GET /api/aircraft/{acid}/route`

FMS route waypoints for one aircraft.

### `GET /api/aircraft/{acid}/wind`

Wind sampled at this aircraft's position.

**Query:** `?units=aviation|si|imperial` (default
aviation).

**Response:**
```json
{
  "acid": "KL204",
  "direction_deg": 270.0,
  "speed": 30.0,
  "units": "aviation",
  "unit_label": "kt",
  "north_ms": 0.0,
  "east_ms": 15.43
}
```

### Aircraft CRUD and autopilot

Typed shortcuts (all POST):

- `POST /api/aircraft` — body
  `{acid, type, lat, lon, hdg, alt, spd}` → `CRE`.
- `DELETE /api/aircraft/{acid}` → `DEL`.
- `POST /api/aircraft/{acid}/hdg` — body `{heading}`.
- `POST /api/aircraft/{acid}/alt` — body `{altitude}`.
- `POST /api/aircraft/{acid}/spd` — body `{speed}`.
- `POST /api/aircraft/{acid}/lnav` — body `{on: bool}`.
- `POST /api/aircraft/{acid}/vnav` — body `{on: bool}`.
- `POST /api/aircraft/{acid}/addwpt` — body
  `{name, alt?, spd?}`.

## Scenarios

### `GET /api/scenarios`

Categorized list of available scenarios.

**Response:**
```json
{
  "Built-in": [{"filename": "demo.scn", "name": "demo"}],
  "User": [{"filename": "mytest.scn", "name": "mytest"}]
}
```

### `POST /api/scenarios/load`

**Body:** `{"filename": "demo.scn"}` → stacks
`IC demo.scn`.

### `GET /api/scenarios/text?filename=demo.scn`

Raw text contents of a scenario file.

### `POST /api/scenarios/save-text`

Save a scenario file. User workdir only — built-ins
return 403.

**Body:**
```json
{"filename": "mytest.scn", "content": "00:00:00>OP\n..."}
```

### `GET /api/scenarios/versions?filename=demo.scn`

Find every `<stem>_v*.scn` variant.

## Navigation data

### `GET /api/navdata/airports?bounds=lat1,lon1,lat2,lon2&zoom=1`

Airports in a lat/lon bounding box, filtered by zoom
tier.

### `GET /api/navdata/waypoints?bounds=...&zoom=...`

Waypoints in a bounding box.

### `GET /api/navdata/search?q=EHAM`

Search by ICAO / name prefix.

## Areas

### `GET /api/areas`

Every defined shape plus the currently active area.

### `POST /api/areas/box`

**Body:** `{name, lat1, lon1, lat2, lon2, top?, bottom?, activate?}`.

### `POST /api/areas/poly`

**Body:** `{name, coords: [[lat, lon], ...], top?, bottom?, activate?}`.

### `POST /api/areas/circle`

**Body:** `{name, lat, lon, radius, top?, bottom?, activate?}`.

### `POST /api/areas/activate`

**Body:** `{name}` → stack `AREA <name>`.

### `POST /api/areas/deactivate`

Stack `AREA OFF`.

### `DELETE /api/areas/{name}`

Delete a shape.

## Wind

All wind endpoints accept a `units` selector
(`aviation`, `si`, `imperial`) that interprets input
speeds and formats output. Direction is always degrees
true (METAR "from" convention).

### `GET /api/wind/info`

Wind field metadata and definition points.

### `GET /api/wind/sample?lat=..&lon=..&altitude_ft=..&units=aviation`

Probe the wind field at any position.

### `GET /api/wind/aircraft/{acid}?units=aviation`

Wind sampled at a specific aircraft.

### `POST /api/wind/uniform`

**Body:**
```json
{
  "direction_deg": 270.0,
  "speed": 30.0,
  "altitude_ft": null,
  "units": "aviation"
}
```

### `DELETE /api/wind`

Clear all wind (`WIND 0 0 DEL`).

## Documentation

### `GET /docs/`

Documentation site (HTML). Not `/api/docs` because
this is a user-facing rendered page.

### `GET /docs/{slug:path}`

Render a specific docs page — markdown or
auto-generated.

## Errors

All errors return JSON:

```json
{"detail": "Aircraft 'XYZ' not found"}
```

HTTP status codes follow REST conventions:

- **200** — success.
- **201** — resource created.
- **400** — bad request (malformed body).
- **404** — resource not found.
- **422** — validation error (Pydantic).
- **500** — server error.

## See also

- [WebSocket Protocol](/docs/api/websocket) — for
  live data streaming.
- [Stack Commands](/docs/stack-commands) — the
  underlying command language every endpoint sits on.
- [Live Commands reference](/docs/ref/commands) — the
  complete list of what you can send via `/api/commands`.
