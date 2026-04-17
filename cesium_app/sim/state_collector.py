"""Collects simulation state snapshots for WebSocket broadcasting.

The collector runs inside the simulation thread (via Timer
callbacks) to ensure consistent snapshots -- all arrays are read
from the same simulation timestep.  Snapshots are stored in a
thread-safe container that the async WebSocket broadcaster reads.
"""
import logging
import threading

import bluesky as bs
from bluesky.core.walltime import Timer
from bluesky.stack import stackbase

logger = logging.getLogger(__name__)

# Update rates (matching screenio.py constants).
ACDATA_INTERVAL_MS: int = 200   # 5 Hz
TRAILS_INTERVAL_MS: int = 1000  # 1 Hz
SIMINFO_INTERVAL_MS: int = 1000  # 1 Hz

# Map numeric sim state to human-readable name.
_STATE_NAMES: dict[int, str] = {
    bs.INIT: "INIT",
    bs.HOLD: "HOLD",
    bs.OP: "OP",
    bs.END: "END",
}


class StateCollector:
    """Collects simulation state into serializable snapshots.

    Call ``install()`` after BlueSky is initialized to register
    timer callbacks.  The async WebSocket broadcaster reads
    snapshots via ``get_latest()``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._acdata: dict | None = None
        self._trails: dict | None = None
        self._siminfo: dict | None = None
        self._acdata_seq: int = 0
        self._trails_seq: int = 0
        self._siminfo_seq: int = 0
        # Optional smooth-bank source.  When set,
        # ACDATA's bank array uses the authoritative
        # smoothly-integrated values instead of deriving
        # from BlueSky's discrete turnphi/bankdef model.
        self.bank_controller = None

    def install(self) -> None:
        """Register timer callbacks in the sim thread."""
        self._ac_timer = Timer(ACDATA_INTERVAL_MS)
        self._ac_timer.timeout.connect(self._collect_acdata)

        self._trail_timer = Timer(TRAILS_INTERVAL_MS)
        self._trail_timer.timeout.connect(
            self._collect_trails,
        )

        self._info_timer = Timer(SIMINFO_INTERVAL_MS)
        self._info_timer.timeout.connect(
            self._collect_siminfo,
        )
        logger.info("StateCollector timers installed")

    def get_latest(self) -> dict:
        """Return the latest snapshots (called from async).

        Returns:
            Dict with acdata, trails, siminfo snapshots and
            their sequence numbers.
        """
        with self._lock:
            return {
                "acdata": self._acdata,
                "acdata_seq": self._acdata_seq,
                "trails": self._trails,
                "trails_seq": self._trails_seq,
                "siminfo": self._siminfo,
                "siminfo_seq": self._siminfo_seq,
            }

    def consume_trails(self) -> dict | None:
        """Get and clear the trails snapshot.

        Returns:
            Trail segment dict, or None if no new segments.
        """
        with self._lock:
            trails = self._trails
            self._trails = None
            return trails

    # ── Timer callbacks (run in sim thread) ──────────────

    def _collect_acdata(self) -> None:
        """Snapshot aircraft state.

        Mirrors screenio.send_aircraft_data().
        """
        if bs.traf.ntraf == 0:
            snapshot = {
                "simt": bs.sim.simt,
                "id": [], "lat": [], "lon": [],
                "alt": [], "tas": [], "cas": [],
                "gs": [], "trk": [], "vs": [],
                "inconf": [], "inlos": [],
                "bank": [], "bank_limit": [],
                "windnorth": [], "windeast": [],
                "nconf_cur": 0, "nconf_tot": 0,
                "nlos_cur": 0, "nlos_tot": 0,
            }
        else:
            import numpy as np
            cd = bs.traf.cd
            ap = bs.traf.ap

            # Bank angle source: use the smooth-bank
            # controller when one is configured (it owns
            # the authoritative per-aircraft bank that it
            # already fed into BlueSky's turnphi this
            # tick).  Without a controller, fall back to
            # reconstructing bank from BlueSky's discrete
            # model — magnitude from turnphi/bankdef, sign
            # from heading delta.
            try:
                bankdef = ap.bankdef
                bank_limit_deg = np.degrees(
                    bankdef,
                ).tolist()
                if self.bank_controller is not None:
                    bank_deg = (
                        self.bank_controller
                        .get_bank_deg_signed_all()
                    )
                    # Size mismatch can briefly occur
                    # right after aircraft creation or
                    # deletion; pad or trim.
                    if len(bank_deg) != bs.traf.ntraf:
                        pad = [0.0] * bs.traf.ntraf
                        for i, v in enumerate(
                            bank_deg[:bs.traf.ntraf],
                        ):
                            pad[i] = v
                        bank_deg = pad
                else:
                    eps = getattr(bs.traf, 'eps', 1e-6)
                    turnphi = ap.turnphi
                    phi_abs = np.where(
                        turnphi > eps * eps,
                        turnphi, bankdef,
                    )
                    delhdg = (
                        (ap.trk - bs.traf.hdg + 180)
                        % 360 - 180
                    )
                    turning = np.abs(delhdg) >= 0.5
                    sign = np.sign(delhdg)
                    bank_rad = phi_abs * sign * turning
                    bank_deg = np.degrees(bank_rad).tolist()
            except (AttributeError, TypeError, ValueError):
                bank_deg = [0.0] * bs.traf.ntraf
                bank_limit_deg = [25.0] * bs.traf.ntraf

            # Build inlos[i]: true if aircraft i is in any
            # loss-of-separation pair this timestep.
            los_ids: set = set()
            for pair in getattr(cd, 'lospairs', []) or []:
                if isinstance(pair, tuple) and len(pair) >= 2:
                    los_ids.add(pair[0])
                    los_ids.add(pair[1])
            inlos = [
                ac in los_ids for ac in bs.traf.id
            ]

            # Per-aircraft wind — what the sim actually
            # used for this aircraft's GS/track calc this
            # frame.  Values are in m/s; frontend converts
            # to user units.  Missing on some BlueSky
            # versions; fall back to zeros.
            try:
                windnorth = bs.traf.windnorth.tolist()
                windeast = bs.traf.windeast.tolist()
            except AttributeError:
                windnorth = [0.0] * bs.traf.ntraf
                windeast = [0.0] * bs.traf.ntraf

            snapshot = {
                "simt": bs.sim.simt,
                "id": list(bs.traf.id),
                "lat": bs.traf.lat.tolist(),
                "lon": bs.traf.lon.tolist(),
                "alt": bs.traf.alt.tolist(),
                "tas": bs.traf.tas.tolist(),
                "cas": bs.traf.cas.tolist(),
                "gs": bs.traf.gs.tolist(),
                "trk": bs.traf.trk.tolist(),
                "hdg": bs.traf.hdg.tolist(),
                "vs": bs.traf.vs.tolist(),
                "inconf": self._safe_tolist(
                    cd, "inconf"
                ),
                "inlos": inlos,
                "bank": bank_deg,
                "bank_limit": bank_limit_deg,
                "windnorth": windnorth,
                "windeast": windeast,
                "tcpamax": self._safe_tolist(
                    cd, "tcpamax"
                ),
                "rpz": self._safe_tolist(cd, "rpz"),
                "hpz": self._safe_tolist(cd, "hpz"),
                "nconf_cur": len(cd.confpairs_unique),
                "nconf_tot": len(cd.confpairs_all),
                "nlos_cur": len(cd.lospairs_unique),
                "nlos_tot": len(cd.lospairs_all),
                # Per-pair conflict detail for the
                # conflicts panel.
                "confpairs": [
                    list(p) for p in cd.confpairs
                ] if cd.confpairs else [],
                "lospairs": [
                    list(p) for p in cd.lospairs
                ] if cd.lospairs else [],
                "conf_tcpa": (
                    cd.tcpa.tolist()
                    if hasattr(cd.tcpa, 'tolist')
                    and len(cd.tcpa) else []
                ),
                "conf_dcpa": (
                    cd.dcpa.tolist()
                    if hasattr(cd.dcpa, 'tolist')
                    and len(cd.dcpa) else []
                ),
                "translvl": float(bs.traf.translvl),
            }

        with self._lock:
            self._acdata = snapshot
            self._acdata_seq += 1

    def _collect_trails(self) -> None:
        """Snapshot new trail segments.

        Mirrors screenio.send_trails().
        """
        trails = bs.traf.trails
        if not trails.active or len(trails.newlat0) == 0:
            return

        snapshot = {
            "traillat0": self._to_list(trails.newlat0),
            "traillon0": self._to_list(trails.newlon0),
            "traillat1": self._to_list(trails.newlat1),
            "traillon1": self._to_list(trails.newlon1),
        }
        trails.clearnew()

        with self._lock:
            self._trails = snapshot
            self._trails_seq += 1

    def _collect_siminfo(self) -> None:
        """Snapshot simulation info.

        Mirrors screenio.send_siminfo().
        """
        state_name = _STATE_NAMES.get(
            bs.sim.state, "UNKNOWN"
        )
        snapshot = {
            "simt": bs.sim.simt,
            "simdt": bs.sim.simdt,
            "utc": str(
                bs.sim.utc.replace(microsecond=0)
            ),
            "dtmult": bs.sim.dtmult,
            "ntraf": bs.traf.ntraf,
            "state": bs.sim.state,
            "state_name": state_name,
            "scenname": stackbase.get_scenname(),
        }

        with self._lock:
            self._siminfo = snapshot
            self._siminfo_seq += 1

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _safe_tolist(obj: object, attr: str) -> list:
        """Read an attribute as a list, or [] if missing."""
        if not hasattr(obj, attr):
            return []
        return getattr(obj, attr).tolist()

    @staticmethod
    def _to_list(arr: object) -> list:
        """Convert a numpy array or sequence to a list."""
        if hasattr(arr, 'tolist'):
            return arr.tolist()
        return list(arr)
