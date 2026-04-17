# Conflict Resolution Methods (RESO)

BlueSky separates conflict **detection** (ASAS / CDMETHOD)
from conflict **resolution** (RESO). Detection decides
*what* pairs of aircraft will violate separation; resolution
decides *how* to maneuver them out of it.

Every resolution class inherits from
`bluesky.traffic.asas.ConflictResolution` and implements a
single method:

```python
def resolve(self, conf, ownship, intruder):
    # → (newtrack, newgs, newvs, newalt)
```

The autopilot follows these commanded values for aircraft
that are currently in a conflict and for which `swlnav` is
on. Aircraft not in any conflict continue on their plan.

The four options that ship with BlueSky are summarized
below. `MVP` is built in; `EBY` and `SSD` are plugins —
load them with `PLUGIN LOAD EBY` / `PLUGIN LOAD SSD` from
the console, or use the "Load plugin…" dropdown in the SIM
tab.

---

## OFF

Resolution disabled. Conflicts are still detected and
reported (orange PZ cylinders, conflict counts in the
status bar), but the autopilot takes no evasive action —
aircraft proceed on their assigned headings, speeds, and
altitudes. They can and will lose separation if nothing
else intervenes.

Use this when you want to:
- Observe raw conflict geometry for analysis
- Test detection algorithms without resolution interference
- Hand-fly conflicts yourself via HDG/ALT/SPD commands

Source: base class `ConflictResolution` (no resolve
override).

---

## MVP — Modified Voltage Potential

**File:** `bluesky/traffic/asas/mvp.py` (built in).

**Model:** Treats each conflict as a repulsive force —
analogous to two like-charged particles. For every pair
in conflict the algorithm computes the minimum velocity
change `dv` that pushes the aircraft's projected closest
point of approach (CPA) just outside the protected zone.

For each pair `(ownship, intruder)`:

1. Compute the relative position `drel` and relative
   velocity `vrel` in an earth-fixed NED frame.
2. Project to the CPA: `dcpa = drel + vrel·tcpa`.
3. Horizontal intrusion `iH = rpz − |dcpa_horiz|`.
4. The horizontal `dv` component is perpendicular to the
   relative velocity, magnitude scaled by `iH / |tcpa|`.
5. Vertical intrusion solved separately with a symmetric
   formula using HPZ.
6. Per-pair `dv` vectors are summed into the ownship's
   velocity correction.

**Priority modes** (via `PRIORULES ON <code>`):

| Code | Meaning |
|---|---|
| `FF1` | Free Flight, fully cooperative (both aircraft maneuver) |
| `FF2` | Cruising has priority (climbing/descending solves) |
| `FF3` | Climbing/descending has priority (cruising solves horizontally) |
| `LAY1` | Cruising-priority, horizontal only |
| `LAY2` | Climbing-priority, horizontal only |

**Axis constraints:**

- `RMETHH [BOTH / SPD / HDG / OFF]` — which horizontal
  degrees of freedom are allowed.
- `RMETHV [ON / OFF]` — whether vertical resolution is
  enabled.

**Characteristics:**
- Vectorized — cheap, runs at full sim rate even with
  thousands of aircraft.
- Cooperative — both aircraft share the workload when
  no priority rule dictates otherwise.
- Well-studied — the default in most BlueSky research
  publications.

**When to use:** General-purpose. If unsure, pick MVP.

---

## EBY — Algebraic Geometric Resolution

**File:** `bluesky/plugins/asas/eby.py` (plugin).

**Model:** Treats both aircraft as moving in straight
lines at constant velocity and solves **algebraically**
for the minimum `dv` that keeps the pair outside the PZ
at every future time.

For each pair:

1. Write the relative position `d` and velocity `v` in
   cartesian coordinates.
2. The intrusion `i(t) = rpz − |d + v·t|` is maximized
   over `t`.
3. Set `d/dt (i/t) = 0`, square to eliminate the `sqrt`,
   arrive at a quadratic:
   `(R²·v² − (d·v)²)·t² + 2·(d·v)·(R² − d²)·t + R²·d² − d⁴ = 0`
4. Pick the smaller positive root → `tstar`.
5. The displacement at `tstar` gives the resolution vector.

**Characteristics:**
- **Horizontal only** — no vertical component; altitude
  is untouched.
- Purely geometric — no priority rules, no axis selector.
- Symmetric — both aircraft share the `dv` (ownship gets
  `-dv_eby`, intruder gets `+dv_eby`).
- Fast and deterministic — the quadratic is solved in
  closed form.

**Limitations:**
- Assumes straight-line motion. If aircraft are turning
  (following an FMS route), the solution can be
  pessimistic or brittle.
- No vertical escape option, so two aircraft at the same
  altitude must resolve entirely horizontally.

**When to use:**
- Clean baseline comparisons (no priority confounds).
- Cruise-phase en-route scenarios where aircraft are
  essentially flying straight.
- Research on pure horizontal conflict geometry.

---

## SSD — State-Space Diagram

**File:** `bluesky/plugins/asas/ssd.py` (plugin).

**Dependency:** Requires `pyclipper` (polygon clipping
library). Install with `pip install pyclipper` if missing.

**Model:** For each aircraft, construct a **velocity
obstacle diagram** — a 2D polygon in (east, north)
velocity space showing every `(vx, vy)` that would cause
a conflict with some intruder. The complement of that
polygon is the set of safe velocities. Pick the nearest
point in the safe region to the aircraft's current
velocity (or a target velocity under a priority rule).

Implementation uses `pyclipper` to compute the Minkowski
difference of each intruder's velocity-obstacle cone with
the ownship's allowed speed range. The feasible region is
then clipped and searched for the nearest safe velocity.

**Priority modes** (via `PRIORULES ON <code>`):

| Code | Meaning |
|---|---|
| `RS1` | Shortest way out (default) |
| `RS2` | Clockwise turning only |
| `RS3` | Try heading change first, then RS1 |
| `RS4` | Try speed change first, then RS1 |
| `RS5` | Shortest from target (waypoint-aware) |
| `RS6` | Rules of the air (give-way priority by geometry) |
| `RS7` | Sequential RS1 (resolve pair-by-pair) |
| `RS8` | Sequential RS5 |
| `RS9` | Counterclockwise turning only |

**Characteristics:**
- **Horizontal only** — like EBY, altitude unchanged.
- Considers *all* intruders simultaneously — the safe
  region is the intersection of every pairwise
  avoidance polygon.
- Finds a globally optimal horizontal resolution given
  the priority rule.
- Supports "rules of the air" semantics where the
  aircraft with right-of-way keeps its trajectory.

**Limitations:**
- Computationally heavier than MVP or EBY — polygon
  clipping is `O(n log n)` per aircraft, scales to a
  few hundred aircraft comfortably but not to 10k.
- Research-grade quality — occasional edge cases where
  no solution is found (algorithm falls back to keeping
  current velocity).
- Horizontal-only, so vertical conflicts (same track,
  different altitudes converging) are not addressed.

**When to use:**
- Dense airspace where pairwise resolution under-
  performs and global awareness of all intruders is
  needed.
- Research into priority rules and rules-of-the-air
  semantics.
- Scenarios where "shortest-from-target" resolutions
  (RS5) matter — e.g., aircraft heading to a fix.

---

## Picking a method — quick guide

| Situation | Recommended |
|---|---|
| Default / general purpose | `MVP` |
| Need vertical resolutions | `MVP` (only option) |
| Want closed-form / deterministic baseline | `EBY` |
| Dense airspace, need global optimality | `SSD` |
| Rules-of-the-air semantics | `SSD` with `RS6` |
| Priority by flight phase | `MVP` with `FF2`/`FF3` |
| Passive (detect only, don't resolve) | `OFF` |

---

## Related stack commands

Useful commands that affect any resolver's behavior:

- `ZONER <nm>` / `ZONEDH <ft>` — size of the protected
  zone (radius, half-height). Default 5 nm × 1000 ft.
- `DTLOOK <sec>` — look-ahead window for conflict
  detection. Default 300 s (5 min).
- `RFACH <factor>` / `RFACV <factor>` — resolution
  buffer factors. `1.01` means resolve to 1% outside
  the PZ; `1.10` gives a 10% margin; `<1.0` maneuvers
  only a fraction of the way out.
- `NORESO <acid>` — exclude aircraft from being avoided
  (everyone ignores them).
- `RESOOFF <acid>` — stop an aircraft from resolving
  (it keeps its plan regardless of conflicts).
- `PRIORULES ON <code>` — enable priority mode (code
  depends on the resolver: `FF1..LAY2` for MVP,
  `RS1..RS9` for SSD).
