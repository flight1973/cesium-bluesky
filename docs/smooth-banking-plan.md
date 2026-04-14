# Smooth Roll-In/Roll-Out Banking — Implementation Plan

## Current behavior (BlueSky upstream)

BlueSky's turn model is **binary** — during any timestep
where the aircraft's heading differs from the autopilot
target by more than the turn rate allows, the bank is
instantly at `ap.bankdef` (e.g. 25°). When the heading
matches target, bank drops instantly to 0.

There is **no roll rate**, no gradual roll-in, no
proportional banking. The `ap.turnphi` array exists but
is set per-waypoint, not dynamically.

## Desired physics

A real aircraft rolls smoothly between wings-level and its
max bank angle with a **roll rate** (typically 3–5°/s for
airliners, 10–15°/s for light aircraft). The bank angle
during a turn is proportional to the required turn rate:

```
tan(φ) = ω·V / g     →    φ = atan(ω·V / g)
```

Where:
- φ = bank angle (rad)
- ω = turn rate (rad/s)
- V = true airspeed (m/s)
- g = 9.81 m/s²

For a gentle 10° heading correction, bank might only be
5° at standard cruise speed. For a sharp reversal, bank
saturates at the configured max (25° for airliners).

## Implementation options

### Option A — Frontend-only derivation (quick win, merged now)

Do nothing on the sim side. In the frontend's aircraft
manager, track `prevHdg` and `prevSimt` per aircraft. On
each ACDATA frame:

```
dt = simt - prevSimt
dhdg = shortestAngleDelta(hdg, prevHdg)
omega = toRad(dhdg) / dt
phi = atan(omega * tas / g)
phi = clamp(phi, -bankLimit, +bankLimit)
// Smooth with EMA to hide 5Hz quantization:
displayBank = 0.7 * displayBank + 0.3 * phi
```

**Pros:** Zero sim-side changes. Works with any BlueSky
version. Gives visually smooth bank for rendering.
**Cons:** Value is derived, not authoritative. If we need
bank for control/logging purposes it's noisy.

### Option B — BlueSky monkey-patch (medium effort)

Override `bs.traf.update()` or install a pre-update hook
that maintains a continuous `bs.traf.bank` numpy array:

```
target_bank = atan(target_turnrate * tas / g)
bank_err = target_bank - current_bank
roll_rate_max = 3° / s  (configurable per AC type)
delta = clip(bank_err, -roll_rate_max*dt, +roll_rate_max*dt)
bs.traf.bank += delta
// Use this bank in the existing turnrate calculation
// instead of the discrete on/off model.
```

Replace BlueSky's line in `traffic.py` that computes
`turnrate` to use the continuous `bank` array instead of
`turnphi`/`bankdef`. This keeps BlueSky's semantics while
making the dynamics smooth.

**Pros:** Authoritative. Affects LOS/conflict detection
correctly during rolls.
**Cons:** We'd be overriding BlueSky internals. Risks
breakage on BlueSky updates. Might need to be re-applied
after every scenario reset.

### Option C — Upstream PR to BlueSky (best long-term)

Submit a PR adding a `SmoothBank` performance option:

1. Add `self.bank` to `Traffic` as a state variable
2. Add `self.roll_rate_max` from performance model
3. Replace discrete on/off in `traffic.update()` with the
   continuous integrator from Option B
4. Add `BANKRATE acid rate` stack command to override
5. Tests in `tests/traffic/test_smooth_bank.py`

**Pros:** Everyone benefits, including research papers
that use BlueSky. No local monkey-patching.
**Cons:** Review cycle. May want to be opt-in behind a
config flag (`performance_model='openap_smooth'`).

## Recommended sequence

1. **Now:** Option A on the frontend — get smooth visuals
   immediately. Add `bs.traf.bank` to ACDATA when the
   discrete model says "turning", else computed bank from
   heading delta when observable.
2. **Soon:** Option B as a plugin — self-contained
   `cesium_app/sim/smooth_bank.py` that monkey-patches on
   init. Gives us authoritative smooth bank for FMS
   displays and future autopilot modeling.
3. **When stable:** Option C — submit upstream.

## Roll rate defaults

Typical values to start with (configurable per aircraft
type via perf model later):

| Type | Roll rate | Max bank |
|---|---|---|
| Light GA | 10°/s | 45° |
| Turboprop | 6°/s | 30° |
| Regional jet | 5°/s | 25° |
| Heavy jet | 3°/s | 25° |

## Visual rendering (independent)

Regardless of which option, the aircraft icon can be
rendered tilted by the bank angle. For the 2D icon
rendering, this means rotating the silhouette around the
fuselage axis — a CSS `transform: rotate3d(0, 1, 0, Xdeg)`
equivalent via Cesium billboard settings, or switching
to a simple GLTF model that supports the full HPR
orientation.

Note: at low bank angles (< ~5°) the visual tilt is
indistinguishable on a typical radar display, so focus
on correct rendering when bank > 10°.
