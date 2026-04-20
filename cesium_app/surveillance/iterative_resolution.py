"""Iterative conflict resolution.

Pairwise resolution methods (MVP, SSD, VO, ORCA, …) resolve
one conflict at a time without considering downstream
effects.  When you turn aircraft A to dodge B, that new
heading can put A into conflict with C.  Measured secondary
conflict creation (from our 10-algorithm sweep):

    Social Force 8, VO 10, Dubins 12, SSD 17, ORCA 29,
    MVP 32, Eby 36, Swarm 37, Boids 46.

The iterative resolver re-runs CD+resolution on the
post-advisory projected state, folds any new advisories
into the accumulated set, and repeats until the conflict
set converges (or we hit the iteration cap).

The output is the same shape as a single-pass call:

    {callsign: {
        'new_hdg', 'new_spd_kt', 'new_vs_fpm',
        'dhdg_deg', 'dspd_kt', 'dvs_fpm',
        'row_status', 'iterations', 'stages',
    }}

The ``iterations`` field records at which pass (1-based)
the final advisory for that aircraft was produced; the
``stages`` field is a list of ``{dhdg, dspd}`` increments
from each pass so UI/debug tooling can see how the advisory
accumulated.
"""
from __future__ import annotations

import logging
from copy import copy
from typing import Any

from cesium_app.surveillance.conflict_detect import detect_conflicts
from cesium_app.surveillance.right_of_way import apply_row
from cesium_app.surveillance import resolution as reso_registry

logger = logging.getLogger(__name__)

# Hard caps: total deflection accumulated across iterations.
MAX_CUMULATIVE_DHDG_DEG = 60.0
MAX_CUMULATIVE_DSPD_KT = 100.0

DEFAULT_MAX_ITERATIONS = 5


def _apply_advisory_to_item(item: dict, adv: dict) -> dict:
    """Return a copy of ``item`` with new_hdg/new_spd applied.

    This is the projected state the next CD pass sees.
    """
    projected = copy(item)
    new_hdg = adv.get('new_hdg')
    new_spd = adv.get('new_spd_kt')
    if new_hdg is not None:
        projected['trk_deg'] = float(new_hdg)
    if new_spd is not None:
        projected['gs_kt'] = float(new_spd)
    return projected


def _accumulate_advisory(
    base: dict | None,
    new: dict,
    iteration: int,
) -> dict:
    """Combine an earlier advisory with a new one.

    ``dhdg`` and ``dspd`` are summed relative to the
    ORIGINAL state (they already are — each advisory in a
    pass is computed against the CURRENT projected state,
    so the new ``new_hdg`` absorbs previous deflections).

    So the rule is: the newer advisory's ``new_hdg`` /
    ``new_spd`` wins, but we recompute ``dhdg`` / ``dspd``
    relative to the original baseline so callers see the
    total deflection, not just the last increment.
    """
    merged = dict(new)
    if base is None:
        merged['iterations'] = iteration
        merged['stages'] = [{
            'iter': iteration,
            'dhdg': new.get('dhdg_deg', 0.0),
            'dspd': new.get('dspd_kt', 0.0),
        }]
        return merged
    stages = list(base.get('stages', []))
    stages.append({
        'iter': iteration,
        'dhdg': new.get('dhdg_deg', 0.0),
        'dspd': new.get('dspd_kt', 0.0),
    })
    merged['iterations'] = iteration
    merged['stages'] = stages
    return merged


def _clamp_cumulative(
    adv: dict,
    original_trk: float,
    original_gs: float,
) -> dict:
    """Cap the total deviation from the original baseline.

    Prevents iterative divergence (advisory chasing a
    never-converging optimum) and bounds pilot workload.
    """
    new_hdg = float(adv.get('new_hdg', original_trk))
    new_spd = float(adv.get('new_spd_kt', original_gs))

    dhdg = _wrap180(new_hdg - original_trk)
    dspd = new_spd - original_gs

    if abs(dhdg) > MAX_CUMULATIVE_DHDG_DEG:
        dhdg = MAX_CUMULATIVE_DHDG_DEG * (1 if dhdg > 0 else -1)
        new_hdg = (original_trk + dhdg) % 360
        adv['new_hdg'] = round(new_hdg, 1)
    if abs(dspd) > MAX_CUMULATIVE_DSPD_KT:
        dspd = MAX_CUMULATIVE_DSPD_KT * (1 if dspd > 0 else -1)
        new_spd = original_gs + dspd
        adv['new_spd_kt'] = round(new_spd, 0)

    adv['dhdg_deg'] = round(dhdg, 1)
    adv['dspd_kt'] = round(dspd, 1)
    return adv


def _wrap180(x: float) -> float:
    while x > 180:
        x -= 360
    while x < -180:
        x += 360
    return x


def resolve_iterative(
    items: list[dict],
    initial_conflicts: dict,
    method: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> tuple[dict[str, dict], dict[str, Any]]:
    """Run CD+resolution to convergence.

    Args:
        items: Aircraft list from the surveillance feed.
        initial_conflicts: Output of conflict_detect on items.
        method: Resolution method (None = current registry).
        max_iterations: Hard cap on passes.

    Returns:
        (advisories, stats) where stats includes:
            iterations: total passes run
            initial_conflicts: count at start
            final_conflicts: count in the projected state
                             after last advisory
            converged: bool — True if final == 0 OR
                       advisory set stabilized
    """
    # Index original baseline for cumulative deflection caps.
    original_by_id: dict[str, tuple[float, float]] = {}
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        original_by_id[cid] = (
            float(ac.get('trk_deg') or 0.0),
            float(ac.get('gs_kt') or 0.0),
        )

    # First pass — resolve the conflicts that CD already found.
    raw = reso_registry.resolve(items, initial_conflicts, method=method)
    advisories = apply_row(items, initial_conflicts, raw)
    # Annotate with iteration/stage bookkeeping.
    advisories = {
        cid: _accumulate_advisory(None, adv, 1)
        for cid, adv in advisories.items()
    }

    iteration = 1
    converged = len(advisories) == 0

    projected = items
    last_adv_keys: set[str] = set(advisories.keys())

    while iteration < max_iterations and not converged:
        # Build the next projected state by applying
        # every current advisory on top of the ORIGINAL
        # baseline (not the last projection), so cumulative
        # caps work against the true deviation.
        projected = []
        for ac in items:
            cid = ac.get('callsign') or ac.get('icao24', '?')
            if cid in advisories:
                projected.append(
                    _apply_advisory_to_item(ac, advisories[cid]),
                )
            else:
                projected.append(ac)

        # Re-run CD on the projected state.
        next_conflicts = detect_conflicts(projected)
        if next_conflicts.get('nconf_cur', 0) == 0:
            converged = True
            break

        iteration += 1
        raw = reso_registry.resolve(
            projected, next_conflicts, method=method,
        )
        pass_adv = apply_row(projected, next_conflicts, raw)

        if not pass_adv:
            # Nothing new to add — bail out, we'll never
            # clear the remaining conflicts with this method.
            break

        # Merge new advisories into the accumulated set.
        any_meaningful_change = False
        for cid, new_adv in pass_adv.items():
            prev = advisories.get(cid)
            merged = _accumulate_advisory(
                prev, new_adv, iteration,
            )
            orig_trk, orig_gs = original_by_id.get(cid, (0.0, 0.0))
            merged = _clamp_cumulative(merged, orig_trk, orig_gs)
            # Detect meaningful changes so we can stop
            # when advisories have gone flat.
            if prev is None:
                any_meaningful_change = True
            else:
                d_hdg = abs(
                    float(merged.get('new_hdg', 0))
                    - float(prev.get('new_hdg', 0))
                )
                d_spd = abs(
                    float(merged.get('new_spd_kt', 0))
                    - float(prev.get('new_spd_kt', 0))
                )
                if d_hdg > 0.5 or d_spd > 1.0:
                    any_meaningful_change = True
            advisories[cid] = merged

        # Convergence check: no meaningful changes this pass.
        if not any_meaningful_change:
            converged = True
        last_adv_keys = set(advisories.keys())

    # Run one more CD on the FINAL projected state to
    # report residual conflicts.
    final_projected = []
    for ac in items:
        cid = ac.get('callsign') or ac.get('icao24', '?')
        if cid in advisories:
            final_projected.append(
                _apply_advisory_to_item(ac, advisories[cid]),
            )
        else:
            final_projected.append(ac)
    final_conflicts = detect_conflicts(final_projected)

    stats = {
        'iterations': iteration,
        'initial_conflicts': initial_conflicts.get('nconf_cur', 0),
        'final_conflicts': final_conflicts.get('nconf_cur', 0),
        'converged': converged
            or final_conflicts.get('nconf_cur', 0) == 0,
        'advisories_issued': len(advisories),
        'method': method or reso_registry.get_method(),
    }
    return advisories, stats
