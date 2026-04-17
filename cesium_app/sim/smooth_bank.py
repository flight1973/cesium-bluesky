"""Smooth roll-in / roll-out dynamics for BlueSky.

BlueSky's stock turn model is binary: during any turn
the aircraft banks at the full ``bankdef`` limit (25°
for most types) and drops to wings-level instantly
when the heading target is reached.  Real aircraft
have a finite **roll rate** — typically 3°/s for
airliners, more for lighter types — and they vary
bank during roll-in and roll-out.

This module adds that behavior as a **monkey-patch**
layer outside BlueSky.  Every simulation tick, before
BlueSky's ``traffic.update()`` runs, we:

1. Look at how much heading the autopilot wants to
   correct (``ap.trk − bs.traf.hdg``).
2. Pick a **target bank** — ramping from 0 at
   on-heading up to ``bankdef`` when the correction
   is larger than a rollout-angle threshold.  This is
   the turn-anticipation behavior of a real autopilot
   (roll out proportionally as the target approaches).
3. Integrate our current bank toward the target at
   the configured roll rate.
4. Write the **absolute** bank into ``ap.turnphi`` so
   BlueSky's existing turn-rate formula
   ``ω = g·tan(φ)/TAS`` uses our smooth value instead
   of the discrete ``bankdef``.

The signed bank value is kept on the controller for
the aircraft detail panel and ACDATA rendering — no
need for separate "derive from mode switches" logic
anymore, since this module is now the authoritative
source of per-aircraft bank.

See ``docs/smooth-banking-plan.md`` for the plan this
implements (Option B — BlueSky monkey-patch).
"""
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # avoid import at module load time
    pass

logger = logging.getLogger(__name__)


class SmoothBankController:
    """Maintains a smoothly-integrated per-aircraft bank.

    Thread-safety: this runs exclusively in the sim
    thread alongside BlueSky's own state.  The read-side
    accessors (``get_bank_deg_signed`` etc.) are called
    from async FastAPI handlers; Python's GIL plus numpy's
    array-read atomicity make that safe.
    """

    # Airliner-typical defaults.  A future refinement
    # looks these up per aircraft type (project_roll_rates).
    roll_rate_deg_per_s: float = 3.0
    # Heading-error threshold at which target bank
    # saturates at ``bankdef``.  Below this, target
    # bank scales linearly with |delhdg| so the
    # aircraft rolls out smoothly as it approaches the
    # target.  A larger value = gentler, earlier
    # roll-out.
    rollout_angle_deg: float = 12.0

    def __init__(self) -> None:
        # Signed bank in radians, one entry per aircraft.
        # Sign: positive = right bank, negative = left.
        self._bank: np.ndarray = np.zeros(0, dtype=float)
        self._installed: bool = False

    def install(self) -> None:
        """Mark the controller active.  Idempotent."""
        self._installed = True
        logger.info(
            "SmoothBankController installed "
            "(roll_rate=%.1f°/s, rollout=%.1f°)",
            self.roll_rate_deg_per_s,
            self.rollout_angle_deg,
        )

    def tick(self, dt: float) -> None:
        """Advance bank state by one sim step.

        Called from ``SimBridge._run_loop`` before
        ``bs.sim.update()``.  Writes ``ap.turnphi`` so
        BlueSky's own turn integration uses our bank
        magnitude.
        """
        if not self._installed or dt <= 0:
            return

        import bluesky as bs
        ntraf = bs.traf.ntraf
        if ntraf == 0:
            self._bank = np.zeros(0, dtype=float)
            return

        # Resize if the fleet grew or shrank.  This is a
        # blunt approach — aircraft that were deleted
        # mid-array cause a transient wings-level jump
        # for the next iteration — but BlueSky's
        # deletion semantics don't give us the old index
        # without more plumbing.  Acceptable for a first
        # pass; revisit when we hit visible artifacts.
        if self._bank.shape[0] != ntraf:
            new_bank = np.zeros(ntraf, dtype=float)
            n = min(self._bank.shape[0], ntraf)
            new_bank[:n] = self._bank[:n]
            self._bank = new_bank

        ap = bs.traf.ap

        # Heading error the autopilot wants to correct.
        delhdg_deg = (
            (ap.trk - bs.traf.hdg + 180) % 360 - 180
        )
        delhdg_rad = np.radians(delhdg_deg)

        # Target bank: linearly ramp from 0 to bankdef
        # as |delhdg| grows from 0 to rollout_angle.
        # Saturates at bankdef above that.  This gives
        # a clean triangular roll-in / roll-out.
        rollout_rad = np.radians(self.rollout_angle_deg)
        frac = np.clip(
            np.abs(delhdg_rad) / rollout_rad, 0.0, 1.0,
        )
        target_mag = ap.bankdef * frac
        target_bank = np.sign(delhdg_rad) * target_mag

        # Integrate toward target at the configured
        # roll rate (symmetric limit, degrees → radians).
        roll_step = np.radians(
            self.roll_rate_deg_per_s,
        ) * dt
        delta = np.clip(
            target_bank - self._bank,
            -roll_step, roll_step,
        )
        self._bank = self._bank + delta

        # Feed BlueSky.  turnphi is the positive bank
        # magnitude it uses in ω = g·tan(φ)/TAS; the
        # sign comes from its own sign(delhdg).
        ap.turnphi[:] = np.abs(self._bank)

    # ── Read accessors (called from FastAPI) ──────────

    def get_bank_rad_signed(self, idx: int) -> float:
        """Signed bank for one aircraft, in radians."""
        if idx < 0 or idx >= self._bank.shape[0]:
            return 0.0
        return float(self._bank[idx])

    def get_bank_deg_signed(self, idx: int) -> float:
        """Signed bank for one aircraft, in degrees."""
        return float(np.degrees(self.get_bank_rad_signed(idx)))

    def get_bank_deg_signed_all(self) -> list[float]:
        """Signed bank for every aircraft, in degrees."""
        return np.degrees(self._bank).tolist()
