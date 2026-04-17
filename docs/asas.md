# Conflict Detection & Resolution

BlueSky separates the **detection** of losses of
separation from the **resolution** of them. Detection
answers *"are these two aircraft going to get too close?"*;
resolution answers *"what maneuver fixes it?"*. Either
can be active independently.

The whole system is usually called **ASAS** — Airborne
Separation Assurance System — which is historical; some
stack commands still use that name.

## Protected Zone (PZ)

Each aircraft carries a protected zone: a cylinder around
it that no other aircraft should enter.

- **Horizontal radius** — `bs.traf.cd.rpz[i]`, default
  **5 NM**, set per-aircraft or globally via
  `ZONER <nm>` (aliases `PZR`, `RPZ`).
- **Half-height** — `bs.traf.cd.hpz[i]`, default
  **1000 ft**, set via `ZONEDH <ft>` (alias `PZH`).

Two aircraft are in **loss of separation** (LoS) if the
horizontal distance is less than `max(rpz_i, rpz_j)`
AND the vertical distance is less than
`max(hpz_i, hpz_j)`. Both conditions must hold; altitude
separation alone keeps them legal.

In Cesium-BlueSky's UI, PZ cylinders are rendered as 3D
volumes around each aircraft — green when safe, orange
when in predicted conflict, red during loss of
separation.

## Conflict Detection (CDMETHOD / ASAS)

A **conflict** is a predicted loss of separation within
a look-ahead window — not yet happening, but will happen
if nothing changes. `bs.traf.cd` holds the detector; the
main switch:

```
ASAS ON          # enable detection (selects first registered method)
ASAS OFF         # disable
CDMETHOD STATEBASED   # choose a specific detector
```

(`ASAS` is an alias for `CDMETHOD`.)

### Look-ahead

`DTLOOK <seconds>` sets how far ahead to project (default
**300 s** — 5 minutes). Shorter means you'll only see
imminent conflicts; longer means earlier warning but more
false positives if aircraft change trajectory.

### Detector output

Each step, the detector populates:

- `cd.confpairs` — list of `(acid_i, acid_j)` tuples in
  predicted conflict.
- `cd.lospairs` — pairs currently in loss of separation.
- `cd.confpairs_unique` — deduplicated (order-independent)
  set.
- `cd.tcpa[i]` — time to closest point of approach for
  each conflict pair.
- `cd.inconf[i]` — boolean, `True` if aircraft `i` is in
  any conflict.
- `cd.tcpamax[i]` — max TCPA across an aircraft's
  conflicts (for severity ranking).

Cesium-BlueSky broadcasts `inconf` and derived `inlos`
arrays in the ACDATA WebSocket frame so the frontend can
color aircraft appropriately without re-running
detection.

### Detectors available

- `STATEBASED` (default) — linear projection of current
  position + velocity. Straight-line assumption. Pure
  Python.
- `CSTATEBASED` — same algorithm, C++ implementation.
  Faster on large fleets, identical results.

Plugins can register new detectors by subclassing
`ConflictDetection`. See the [live detectors
reference](/docs/ref/detectors).

## Conflict Resolution (RESO)

When detection flags a conflict, a **resolver** can
override the autopilot to avoid it. The active resolver:

```
RESO MVP         # default built-in
RESO EBY         # plugin (run PLUGIN LOAD EBY first)
RESO SSD         # plugin (PLUGIN LOAD SSD, needs pyclipper)
RESO OFF         # detect but don't resolve
```

A resolver implements one method:

```python
def resolve(self, conf, ownship, intruder):
    # returns (newtrack, newgs, newvs, newalt)
```

Per aircraft: if the resolver decides to override, the
autopilot obeys `newtrack/gs/vs/alt`; otherwise the
aircraft continues on its planned target. The
`bs.traf.cr.active[i]` boolean array flags which aircraft
are currently being steered by the resolver.

### Tuning knobs

- `RFACH <factor>` — horizontal resolution buffer
  (`1.01` = resolve to 1% outside PZ; `<1.0` = partial
  maneuver).
- `RFACV <factor>` — vertical resolution buffer.
- `RMETHH BOTH / SPD / HDG / OFF` — which horizontal
  axes MVP is allowed to use.
- `RMETHV ON / OFF` — whether MVP can use vertical.
- `NORESO <acid>` — exclude an aircraft from being
  avoided (everyone ignores it).
- `RESOOFF <acid>` — stop an aircraft from resolving
  (follows its plan regardless of conflicts).
- `PRIORULES ON <code>` — priority rules; the code
  depends on the active resolver (MVP uses FF1/LAY1
  etc., SSD uses RS1..RS9).

See the [Resolution Methods guide](/docs/reso-methods)
for details on each algorithm.

## Typical workflow

A realistic sequence in a scenario:

```
# Set up separation requirements
ZONER 3          # 3 NM instead of default 5
ZONEDH 500       # 500 ft vertical
DTLOOK 180       # 3 minute look-ahead

# Enable detection and resolution
ASAS ON
RESO MVP
RFACH 1.10       # resolve to 10% outside PZ

# Priority: climbing traffic has right-of-way
PRIORULES ON FF3
```

In Cesium-BlueSky's SIM tab, the **ASAS ON/OFF button**
reflects the current CD method (green when on). The
**RESO dropdown** lists every registered resolver plus
`OFF`. The **"+ Load plugin…"** dropdown appears when
RESO-providing plugins (`EBY`, `SSD`) are available but
not yet loaded.

## Visualization

Cesium-BlueSky renders the whole system live:

- **PZ cylinders** — 3D extruded ellipses around each
  aircraft at `alt ± hpz`, radius `rpz`. Green normally,
  orange when in predicted conflict, red during loss of
  separation.
- **Conflict counts** — status bar shows
  `Conflicts: current/total` and `LoS: current/total`.
- **Aircraft color** — green (clear), orange
  (conflict), red (LoS).
- **Route** — if an aircraft is resolving, its commanded
  track may differ from its planned route. The
  `bs.traf.cr.active` flag surfaces this to the UI.

## Related reading

- [Resolution Methods](/docs/reso-methods) — deep dive
  on MVP, EBY, and SSD algorithms.
- [live Detectors](/docs/ref/detectors) — current
  registered CD classes.
- [live Resolvers](/docs/ref/resolvers) — current
  registered CR classes.
