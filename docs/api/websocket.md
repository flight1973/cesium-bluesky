# WebSocket Protocol

Live simulation data streams over a single WebSocket
endpoint with a **topic-multiplexed** protocol. One
connection carries every live data channel — ACDATA,
SIMINFO, TRAILS, CMDLOG, ECHO — and the client
subscribes to whichever topics it cares about.

## Endpoint

```
ws://<host>:<port>/ws/sim
```

Cesium-BlueSky's frontend connects automatically on
page load. For custom clients, `wscat` works for
ad-hoc testing:

```
wscat -c ws://localhost:8000/ws/sim
```

## Message framing

All messages are JSON. Server → client messages use:

```json
{"topic": "ACDATA", "data": { ... }}
```

Client → server messages use an `action` field:

```json
{"action": "subscribe", "topics": ["ACDATA", "SIMINFO"]}
{"action": "unsubscribe", "topics": ["TRAILS"]}
{"action": "command", "command": "HDG KL204 090"}
```

## Subscription model

On connect, the client receives **nothing** until it
subscribes. This keeps bandwidth usage tight — if you
only need SIMINFO, you don't pay the 5 Hz ACDATA cost.

Subscribe:
```json
{"action": "subscribe", "topics": ["ACDATA", "SIMINFO"]}
```

Unsubscribe:
```json
{"action": "unsubscribe", "topics": ["ACDATA"]}
```

Subscriptions are additive; sending `subscribe` multiple
times broadens your topic set.

## Topics

### `ACDATA` — aircraft state (5 Hz)

Parallel arrays indexed by aircraft. Published every
200 ms.

**Shape:**
```json
{
  "topic": "ACDATA",
  "data": {
    "simt": 123.45,
    "id": ["KL204", "BA815"],
    "lat": [52.3, 52.1],
    "lon": [4.8, 5.2],
    "alt": [10668.0, 10668.0],
    "tas": [128.6, 128.6],
    "cas": [115.4, 115.4],
    "gs": [132.5, 132.5],
    "trk": [90.0, 270.0],
    "hdg": [95.0, 265.0],
    "vs": [0.0, 0.0],
    "inconf": [false, false],
    "inlos": [false, false],
    "bank": [0.0, 0.0],
    "bank_limit": [25.0, 25.0],
    "windnorth": [0.0, 0.0],
    "windeast": [15.43, 15.43],
    "nconf_cur": 0,
    "nconf_tot": 3,
    "nlos_cur": 0,
    "nlos_tot": 0,
    "translvl": 1828.8
  }
}
```

Units are SI internally (m, m/s, degrees). The frontend
converts on display based on the unit system.

### `SIMINFO` — simulation state (1 Hz)

```json
{
  "topic": "SIMINFO",
  "data": {
    "simt": 450.0,
    "simdt": 0.05,
    "utc": "2026-04-13 00:07:30",
    "dtmult": 1.0,
    "ntraf": 12,
    "state": 1,
    "state_name": "OP",
    "scenname": "demo"
  }
}
```

`state_name` is one of `INIT / OP / HOLD / END`.

### `TRAILS` — new trail segments (1 Hz, when active)

Only published when `TRAIL ON` is active in the sim.

```json
{
  "topic": "TRAILS",
  "data": {
    "traillat0": [52.3, 52.1],
    "traillon0": [4.8, 5.2],
    "traillat1": [52.31, 52.09],
    "traillon1": [4.82, 5.19]
  }
}
```

Each segment is one pair of endpoints. The frontend
accumulates them into a rolling polyline collection.

### `CMDLOG` — command audit stream (real-time)

Every command submitted to `bluesky.stack.stack()`,
from any source, appears here in real time.

```json
{
  "topic": "CMDLOG",
  "data": {
    "simt": 120.0,
    "utc": "2026-04-13T00:02:00",
    "sender": "local",
    "command": "HDG KL204 090"
  }
}
```

`sender` is `"local"` for REST/WebSocket clients in the
same process, or an 8-hex-char sender id for other
clients.

### `ECHO` — stack command responses (real-time)

The sim's response text for each command it processes.
Routed back via this topic so callers who sent a
command via REST or WebSocket can see the sim's reply.

```json
{
  "topic": "ECHO",
  "data": {"text": "KL204: heading set to 090"}
}
```

## Client → server actions

### `subscribe`

Add topics to your subscription set.

```json
{"action": "subscribe", "topics": ["ACDATA"]}
```

### `unsubscribe`

Remove topics.

```json
{"action": "unsubscribe", "topics": ["ACDATA"]}
```

### `command`

Submit a stack command — equivalent to
`POST /api/commands`.

```json
{"action": "command", "command": "HDG KL204 090"}
```

The sim runs the command on the next tick and the
response flows back as an `ECHO` message (if you're
subscribed).

## Connection management

The frontend implements auto-reconnect with exponential
backoff via `frontend/src/services/websocket.ts`. For
custom clients:

- Reconnect on disconnect.
- **Resubscribe on reconnect** — subscriptions are
  per-connection, not persisted server-side.
- Expect brief interruptions during sim resets.

## Performance

- **ACDATA frame cost** ≈ 20 floats × `ntraf` arrays,
  serialized via `orjson` with
  `OPT_SERIALIZE_NUMPY`. At 5 Hz and 1,000 aircraft
  that's ~200 KB/s uncompressed.
- **Per-message deflate** is enabled — achieves ~5×
  compression on typical payloads, bringing the above
  down to ~40 KB/s.
- **Backpressure** — if a client's send buffer fills,
  the broadcast loop drops the oldest message rather
  than blocking. This is intentional: a stuck client
  shouldn't freeze the sim.

## NaN handling

Some BlueSky arrays can contain NaN / Inf values
(e.g., `tcpamax` when no conflicts exist). The server's
JSON encoder converts NaN / Inf to `null` on the way
out, so clients see consistent JSON. Expect the
occasional `null` in numeric arrays.

## Debugging

To watch every command flow by:

```
wscat -c ws://localhost:8000/ws/sim
> {"action":"subscribe","topics":["CMDLOG", "ECHO"]}
```

To see raw state:

```
> {"action":"subscribe","topics":["ACDATA", "SIMINFO"]}
```

Pair with `GET /api/cmdlog?limit=50` to see the last
50 commands right now plus whatever new ones arrive.

## See also

- [REST Endpoints](/docs/api/rest) — for command
  submission and one-shot queries.
- [Stack Commands](/docs/stack-commands) — what you
  can send via the `command` action.
- [Simulation Overview](/docs/simulation-overview) —
  how the sim loop publishes data.
