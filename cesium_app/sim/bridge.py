"""SimBridge: Wraps BlueSky simulation in a background thread.

The bridge initializes BlueSky in detached mode (no ZMQ networking),
runs the simulation loop in a daemon thread, and exposes methods for
queuing commands and reading state that are safe to call from
FastAPI's async handlers.
"""
import collections
import datetime
import logging
from pathlib import Path
import threading
from typing import Any, Callable

import bluesky as bs
from bluesky.core.walltime import Timer

from cesium_app.sim.state_collector import StateCollector

logger = logging.getLogger(__name__)

# Map numeric sim state to human-readable name.
_STATE_NAMES: dict[int, str] = {
    bs.INIT: "INIT",
    bs.HOLD: "HOLD",
    bs.OP: "OP",
    bs.END: "END",
}


def _state_name(state: int) -> str:
    """Convert a numeric simulation state to its name."""
    return _STATE_NAMES.get(state, f"UNKNOWN({state})")


def _compute_bank_deg(idx: int) -> float:
    """Current bank angle in degrees (signed).

    Positive = right bank, negative = left.  Returns 0
    when the aircraft is not turning.
    """
    try:
        import numpy as np
        ap = bs.traf.ap
        eps = getattr(bs.traf, 'eps', 1e-6)
        phi = (
            ap.turnphi[idx] if ap.turnphi[idx]
            > eps * eps else ap.bankdef[idx]
        )
        delhdg = (
            (ap.hdg[idx] - bs.traf.hdg[idx] + 180)
            % 360 - 180
        )
        sign = 1 if delhdg > 0 else -1 if delhdg < 0 else 0
        if not bool(bs.traf.swhdgsel[idx]):
            return 0.0
        return float(np.degrees(phi) * sign)
    except (AttributeError, IndexError):
        return 0.0


def _compute_bank_limit_deg(idx: int) -> float:
    """Configured bank limit for this aircraft, in degrees."""
    try:
        import numpy as np
        return float(
            np.degrees(bs.traf.ap.bankdef[idx]),
        )
    except (AttributeError, IndexError):
        return 25.0


def _sender_label(sender_id: object) -> str:
    """Format a sender id (bytes or None) for display."""
    if sender_id is None:
        return "local"
    if isinstance(sender_id, bytes):
        return sender_id.hex()[:8]
    return str(sender_id)


class SimBridge:
    """Manages the BlueSky simulation lifecycle.

    Runs the simulation in a background thread and provides a
    thread-safe API for commands and state reads.

    Usage::

        bridge = SimBridge()
        bridge.start()
        bridge.stack_command("CRE KL204 B738 52 4 180 FL350 280")
        info = bridge.get_sim_info()
        bridge.stop()
    """

    def __init__(
        self,
        scenario_file: str | None = None,
        workdir: str | None = None,
    ) -> None:
        self._thread: threading.Thread | None = None
        self._scenario_file = scenario_file
        self._workdir = workdir
        self._started = threading.Event()
        self._initialized = False
        self.collector = StateCollector()

        # Rolling log of commands submitted to the stack.
        # Captured from ALL sources: REST, WS, scenario files.
        self._cmd_log: collections.deque = collections.deque(
            maxlen=500,
        )
        self._cmd_log_lock = threading.Lock()
        self._cmd_listeners: list[Callable[[dict], Any]] = []

    def start(self) -> None:
        """Initialize BlueSky and start the sim loop thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("SimBridge already running")
            return

        # Initialize BlueSky in the main thread so singletons
        # are set up before any API calls can arrive.
        workdir = Path(self._workdir) if self._workdir else None
        logger.info(
            "Initializing BlueSky in detached mode "
            "(workdir=%s)",
            workdir,
        )
        bs.init(
            mode='sim',
            detached=True,
            scenfile=self._scenario_file,
            workdir=workdir,
        )
        self._initialized = True
        self.collector.install()
        self._install_command_log_hook()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="bluesky-sim",
            daemon=True,
        )
        self._thread.start()
        self._started.wait(timeout=5.0)
        logger.info("SimBridge started")

    def stop(self) -> None:
        """Signal the sim to quit and wait for the thread."""
        if not self._initialized:
            return
        logger.info("Stopping SimBridge")
        bs.sim.quit()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                logger.warning("Sim thread did not exit cleanly")
        self._thread = None
        logger.info("SimBridge stopped")

    def stack_command(self, cmdline: str) -> None:
        """Queue a command for the next simulation cycle.

        Safe to call from any thread. CPython's GIL makes
        list.append atomic, and bluesky.stack.stack() only
        appends to Stack.cmdstack.
        """
        from bluesky import stack
        stack.stack(cmdline)

    def get_sim_info(self) -> dict:
        """Read current simulation state.

        Returns:
            Dict with simt, simdt, utc, dtmult, ntraf, state,
            state_name, and scenname keys.
        """
        if not self._initialized:
            return {"state": "not_initialized"}

        from bluesky.stack import stackbase
        return {
            "simt": bs.sim.simt,
            "simdt": bs.sim.simdt,
            "utc": str(bs.sim.utc.replace(microsecond=0)),
            "dtmult": bs.sim.dtmult,
            "ntraf": bs.traf.ntraf,
            "state": bs.sim.state,
            "state_name": _state_name(bs.sim.state),
            "scenname": stackbase.get_scenname(),
        }

    def get_aircraft_data(self) -> dict:
        """Read all aircraft state arrays as Python lists.

        Returns:
            Dict with id, lat, lon, alt, tas, cas, gs, trk,
            and vs arrays.
        """
        if not self._initialized or bs.traf.ntraf == 0:
            return {
                "id": [], "lat": [], "lon": [], "alt": [],
                "tas": [], "cas": [], "gs": [],
                "trk": [], "vs": [],
            }

        return {
            "id": list(bs.traf.id),
            "lat": bs.traf.lat.tolist(),
            "lon": bs.traf.lon.tolist(),
            "alt": bs.traf.alt.tolist(),
            "tas": bs.traf.tas.tolist(),
            "cas": bs.traf.cas.tolist(),
            "gs": bs.traf.gs.tolist(),
            "trk": bs.traf.trk.tolist(),
            "vs": bs.traf.vs.tolist(),
        }

    def get_aircraft_by_id(self, acid: str) -> dict | None:
        """Read state for a single aircraft by callsign.

        Args:
            acid: Aircraft callsign (case-insensitive).

        Returns:
            Dict with aircraft state, or None if not found.
        """
        if not self._initialized:
            return None
        idx = bs.traf.id2idx(acid.upper())
        if idx < 0:
            return None
        return {
            "acid": bs.traf.id[idx],
            "lat": float(bs.traf.lat[idx]),
            "lon": float(bs.traf.lon[idx]),
            "alt": float(bs.traf.alt[idx]),
            "tas": float(bs.traf.tas[idx]),
            "cas": float(bs.traf.cas[idx]),
            "gs": float(bs.traf.gs[idx]),
            "trk": float(bs.traf.trk[idx]),
            "vs": float(bs.traf.vs[idx]),
        }

    def get_aircraft_detail(self, acid: str) -> dict | None:
        """Read full detail for one aircraft.

        Includes current state, autopilot targets, origin,
        destination, and route waypoints.

        Args:
            acid: Aircraft callsign (case-insensitive).

        Returns:
            Dict with full aircraft detail, or None.
        """
        if not self._initialized:
            return None
        idx = bs.traf.id2idx(acid.upper())
        if idx < 0:
            return None
        ap = bs.traf.ap
        route = ap.route[idx]
        # Find orig/dest from route wptype list.
        orig = next(
            (n for n, t in zip(route.wpname, route.wptype)
             if t == 2), ap.orig[idx] if ap.orig else "",
        )
        dest = next(
            (n for n, t in zip(route.wpname, route.wptype)
             if t == 3), ap.dest[idx] if ap.dest else "",
        )
        return {
            "acid": bs.traf.id[idx],
            "actype": bs.traf.type[idx],
            "lat": float(bs.traf.lat[idx]),
            "lon": float(bs.traf.lon[idx]),
            "alt": float(bs.traf.alt[idx]),
            "tas": float(bs.traf.tas[idx]),
            "cas": float(bs.traf.cas[idx]),
            "gs": float(bs.traf.gs[idx]),
            "trk": float(bs.traf.trk[idx]),
            "hdg": float(bs.traf.hdg[idx]),
            "vs": float(bs.traf.vs[idx]),
            "orig": orig,
            "dest": dest,
            "sel_hdg": float(ap.trk[idx]),
            "sel_alt": float(ap.alt[idx]),
            "sel_spd": float(ap.spd[idx]),
            "sel_vs": float(ap.vs[idx]),
            "lnav": bool(bs.traf.swlnav[idx]),
            "vnav": bool(bs.traf.swvnav[idx]),
            "bank": _compute_bank_deg(idx),
            "bank_limit": _compute_bank_limit_deg(idx),
            "route": {
                "iactwp": route.iactwp,
                "wpname": list(route.wpname),
                "wplat": list(route.wplat),
                "wplon": list(route.wplon),
                "wpalt": list(route.wpalt),
                "wpspd": list(route.wpspd),
            },
        }

    def get_route_data(self, acid: str) -> dict | None:
        """Read route/FMS data for a single aircraft.

        Args:
            acid: Aircraft callsign (case-insensitive).

        Returns:
            Dict with route waypoints, or None if not found.
        """
        if not self._initialized:
            return None
        idx = bs.traf.id2idx(acid.upper())
        if idx < 0:
            return None
        route = bs.traf.ap.route[idx]
        return {
            "acid": acid.upper(),
            "iactwp": route.iactwp,
            "aclat": float(bs.traf.lat[idx]),
            "aclon": float(bs.traf.lon[idx]),
            "wplat": list(route.wplat),
            "wplon": list(route.wplon),
            "wpalt": list(route.wpalt),
            "wpspd": list(route.wpspd),
            "wpname": list(route.wpname),
        }

    @property
    def is_running(self) -> bool:
        """Whether the simulation thread is alive."""
        return (
            self._thread is not None
            and self._thread.is_alive()
        )

    # ── Command log ──────────────────────────────────────

    def get_command_log(
        self,
        limit: int = 100,
    ) -> list[dict]:
        """Return the most recent N log entries."""
        with self._cmd_log_lock:
            items = list(self._cmd_log)
        return items[-limit:]

    def add_command_listener(
        self,
        cb: Callable[[dict], Any],
    ) -> None:
        """Register a callback invoked on each logged cmd."""
        self._cmd_listeners.append(cb)

    def remove_command_listener(
        self,
        cb: Callable[[dict], Any],
    ) -> None:
        """Remove a listener callback."""
        if cb in self._cmd_listeners:
            self._cmd_listeners.remove(cb)

    def _install_command_log_hook(self) -> None:
        """Patch bluesky.stack.stack to log all commands.

        Every command submitted to the stack — via REST, WS,
        scenario files, or internal BlueSky code — flows
        through bluesky.stack.stack().  We wrap it to log
        each command with its sender_id and simt.
        """
        from bluesky import stack as bs_stack

        original_stack = bs_stack.stack
        bridge_self = self

        def wrapped_stack(*cmdlines: str, sender_id=None):
            for cmdline in cmdlines:
                cleaned = (cmdline or "").strip()
                if not cleaned:
                    continue
                for line in cleaned.split(";"):
                    line = line.strip()
                    if line:
                        bridge_self._record_command(
                            line, sender_id,
                        )
            return original_stack(
                *cmdlines, sender_id=sender_id,
            )

        bs_stack.stack = wrapped_stack

    def _record_command(
        self,
        cmd: str,
        sender_id: object,
    ) -> None:
        """Add a command to the rolling log and notify."""
        entry = {
            "simt": float(bs.sim.simt),
            "utc": datetime.datetime.utcnow().isoformat(
                timespec="seconds",
            ),
            "sender": (
                _sender_label(sender_id)
            ),
            "command": cmd,
        }
        with self._cmd_log_lock:
            self._cmd_log.append(entry)

        # Notify listeners (e.g. WS broadcaster).
        for cb in list(self._cmd_listeners):
            try:
                cb(entry)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Command listener failed: %s", exc,
                )

    # ── Private ──────────────────────────────────────────

    def _run_loop(self) -> None:
        """Simulation main loop (runs in background thread).

        Mirrors Simulation.run() but without installing signal
        handlers (those belong to the main thread).
        """
        logger.info("Sim loop starting")
        self._started.set()

        # Stub out UI-only ScreenIO methods that the
        # headless ScreenIO class doesn't implement.
        # Built-in scenarios use zoom (+++/---) and pan
        # which would otherwise crash the sim thread.
        self._stub_screen_methods()

        while bs.sim.state != bs.END:
            try:
                Timer.update_timers()
                bs.net.update()
                bs.sim.update()
                bs.scr.update()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "Sim loop iteration failed: %s",
                    exc, exc_info=True,
                )
                # Brief sleep to avoid tight error loop.
                import time as _time
                _time.sleep(0.1)

        logger.info("Sim loop exited")

    def _stub_screen_methods(self) -> None:
        """Add no-op stubs for UI-only ScreenIO methods.

        BlueSky's stack has commands like PAN and ZOOM
        (+++, ---) that call methods on bs.scr which
        only exist on GUI Screens, not the headless
        ScreenIO. Stub them so those commands don't
        crash the sim loop.
        """
        scr = bs.scr

        def _noop(*_args, **_kwargs):
            return True

        for method in (
            'zoom', 'pan', 'panzoom', 'setpan',
            'setzoom', 'cmdline', 'feature',
            'filteralt', 'objappend', 'show_file_dialog',
            'show_cmd_doc',
        ):
            if not hasattr(scr, method):
                setattr(scr, method, _noop)
