# Simulation Overview

BlueSky runs a **discrete-time, fixed-step** simulation
of air traffic. At every simulation step the engine
integrates aircraft motion, runs conflict detection,
applies resolution maneuvers, and dispatches any queued
stack commands. Everything else — the FMS, nav database,
protected zones, wind field, performance models — is
driven off that tick.

## The main loop

At the heart of `bluesky.simulation.Simulation.run()` is:

```python
while self.state != END:
    Timer.update_timers()   # trigger any scheduled tasks
    bs.net.update()         # network I/O (no-op in detached)
    self.update()           # one sim step
    bs.scr.update()         # screen / UI callbacks
```

One `self.update()` call advances simulated time by
`simdt` (default **0.05 s** — 20 Hz). Inside that step:

1. **Stack drain** — every queued command is executed.
2. **Traffic update** — `bs.traf.update()` propagates
   each aircraft: autopilot → guidance → dynamics →
   position integration.
3. **Conflict detection** — the active CD method
   (`STATEBASED` by default) computes conflict pairs
   with look-ahead.
4. **Resolution** — if a CR method is active, it
   overrides the autopilot's track/speed/altitude
   targets for aircraft in conflict.
5. **Plugins** — registered per-step callbacks run.
6. **Scheduled timers** — any plugins or internal timers
   (like trails, performance reload, state snapshots)
   that fired this step run their callbacks.

## Time

- `bs.sim.simt` — current simulated time (seconds since
  start).
- `bs.sim.simdt` — integration step length.
- `bs.sim.dtmult` — wall-clock multiplier (1× = real
  time, 5× = five times real, `FF` fast-forwards).
- `bs.sim.utc` — calendar UTC for the simulation clock;
  advances with `simt`.

The difference between `simt` and `utc` matters:
scenarios can set a `UTC` anchor, after which every
tick increments `utc` alongside `simt` so features like
the GFS wind loader and daylight-dependent code use
realistic dates.

## The traffic arrays

All aircraft state lives in parallel numpy arrays on
`bs.traf`. This is the key design decision — **one
array per attribute, indexed by aircraft**, rather than
one object per aircraft. Vectorised numpy operations
make the physics extremely fast at scale.

Some of the arrays you'll touch most:

| Array | Units | Meaning |
|---|---|---|
| `bs.traf.id` | list[str] | Callsigns |
| `bs.traf.lat / lon` | deg | Position |
| `bs.traf.alt` | m | Altitude |
| `bs.traf.tas / cas / gs` | m/s | True / calibrated / ground speed |
| `bs.traf.trk` | deg | Ground track angle |
| `bs.traf.hdg` | deg | Heading (nose direction) |
| `bs.traf.vs` | m/s | Vertical speed |
| `bs.traf.ap.trk / alt / spd` | — | Autopilot **selected** targets |
| `bs.traf.swlnav / swvnav` | bool | LNAV / VNAV engaged |
| `bs.traf.windnorth / windeast` | m/s | Wind sampled at aircraft |

The distinction between `hdg` and `trk` is where wind
shows up — in calm air they're equal; with wind they
differ by the wind correction angle (crab).

## Components

BlueSky is organized into swappable subsystems, most of
which declare themselves `replaceable=True` so plugins
can substitute their own implementation:

- **Traffic** — state arrays, per-step propagation.
- **Autopilot** — computes speed / heading / altitude
  commands from the FMS.
- **FMS** (route) — waypoint sequencing, constraint
  evaluation.
- **Performance model** — lift / drag / thrust limits
  (BADA or OpenAP, depending on build).
- **Conflict Detection** (`CDMETHOD` / `ASAS`) — the
  active detector maintains `confpairs` and `lospairs`.
- **Conflict Resolution** (`RESO`) — consumes conflict
  pairs and commands avoidance.
- **Wind Field** — `bs.traf.wind` stores scattered
  points and serves per-aircraft samples.
- **Nav Database** — airports, waypoints, airways,
  procedures.
- **Screen** — the UI glue. BlueSky's original Qt /
  pygame GUIs subscribe here; we replace it with a
  headless `ScreenIO` and read state directly.

## How Cesium-BlueSky plugs in

This project runs BlueSky in **detached mode**
(`bs.init(mode='sim', detached=True)`), which stubs out
the ZMQ networking that normally carries data to a GUI.
The simulation runs in a background thread; FastAPI
reads arrays directly and ships them to the browser via
WebSocket. Commands travel the same path as from any
other client — through `bluesky.stack.stack()`, which
we monkey-patch to log every command (REST, WebSocket,
scenario file, internal) into a rolling audit trail.

See also:
- [Stack Commands](/docs/stack-commands) for how the
  command system dispatches.
- [Conflict Detection & Resolution](/docs/asas) for the
  detector and resolver interface.
