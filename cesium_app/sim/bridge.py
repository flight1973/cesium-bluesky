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

from cesium_app.sim.smooth_bank import SmoothBankController
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


def _compute_bank_deg(
    idx: int,
    bank_controller=None,
) -> float:
    """Current bank angle in degrees (signed).

    Positive = right bank, negative = left.  Returns 0
    when the aircraft is wings-level.

    With a ``SmoothBankController`` supplied, reads the
    smoothly-integrated bank directly (authoritative
    source).  Without one, falls back to BlueSky's
    discrete model: magnitude from ``ap.turnphi`` (or
    ``ap.bankdef``), sign from the heading-to-target
    delta.
    """
    if bank_controller is not None:
        return bank_controller.get_bank_deg_signed(idx)
    try:
        import numpy as np
        ap = bs.traf.ap
        eps = float(getattr(bs.traf, 'eps', 1e-6))
        turnphi = float(np.asarray(ap.turnphi[idx]).item())
        bankdef = float(np.asarray(ap.bankdef[idx]).item())
        phi = turnphi if turnphi > eps * eps else bankdef
        target = float(np.asarray(ap.trk[idx]).item())
        current = float(np.asarray(bs.traf.hdg[idx]).item())
        delhdg = (target - current + 180) % 360 - 180
        if abs(delhdg) < 0.5:
            return 0.0
        sign = 1 if delhdg > 0 else -1
        return float(np.degrees(phi) * sign)
    except (AttributeError, IndexError, ValueError):
        return 0.0


def _compute_bank_limit_deg(idx: int) -> float:
    """Configured bank limit for this aircraft, in degrees."""
    try:
        import numpy as np
        val = np.asarray(bs.traf.ap.bankdef[idx]).item()
        return float(np.degrees(val))
    except (AttributeError, IndexError, ValueError):
        return 25.0


def _compute_pitch_deg(idx: int) -> float:
    """Current pitch attitude in degrees (signed).

    Positive = nose up, negative = nose down.  Kinematic
    approximation from the flight-path angle:
        sin(γ) = VS / TAS
    We use the flight-path angle as a proxy for pitch.
    A true pitch measurement would add angle of attack
    (typically 2–5° at cruise), which BlueSky doesn't
    model.  Accurate enough for display and for the
    planned chase/pilot camera views.
    """
    import math
    try:
        import numpy as np
        tas = float(np.asarray(bs.traf.tas[idx]).item())
        vs = float(np.asarray(bs.traf.vs[idx]).item())
        if tas < 0.1:
            return 0.0
        ratio = max(-1.0, min(1.0, vs / tas))
        return float(math.degrees(math.asin(ratio)))
    except (AttributeError, IndexError, ValueError):
        return 0.0


def _get_wind_north(idx: int) -> float:
    """Sampled north wind component (m/s) for aircraft idx."""
    try:
        return float(bs.traf.windnorth[idx])
    except (AttributeError, IndexError):
        return 0.0


def _get_wind_east(idx: int) -> float:
    """Sampled east wind component (m/s) for aircraft idx."""
    try:
        return float(bs.traf.windeast[idx])
    except (AttributeError, IndexError):
        return 0.0


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
        # Roll-rate-aware turn dynamics, replacing
        # BlueSky's discrete bank model.  Installed in
        # start(); tick()ed in _run_loop before every
        # bs.sim.update() so turnphi reflects the smooth
        # bank magnitude when BlueSky computes turn rate.
        self.bank_controller = SmoothBankController()

        # Rolling log of commands submitted to the stack.
        # Captured from ALL sources: REST, WS, scenario files.
        self._cmd_log: collections.deque = collections.deque(
            maxlen=500,
        )
        self._cmd_log_lock = threading.Lock()
        self._cmd_listeners: list[Callable[[dict], Any]] = []

        # Shadow list of user-defined wind points, kept in
        # sync by parsing every WIND command that flows
        # through the stack.  Each entry:
        #   {"lat", "lon", "altitude_ft" (float|None),
        #    "direction_deg", "speed_kt"}
        # Populated from the command log hook below so
        # points defined via REST, WS, scenario file, or
        # typed in the console are all captured.
        self._wind_points: list[dict] = []
        self._wind_points_lock = threading.Lock()
        # When set, the next WIND command processed by
        # ``_maybe_update_wind_points`` records points
        # with this origin string instead of the default
        # ``"user"``.  Used by the METAR-import path to
        # tag auto-generated points.
        self._pending_origin: str | None = None

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
        self.bank_controller.install()
        self.collector.bank_controller = self.bank_controller
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
            "bank": _compute_bank_deg(
                idx, self.bank_controller,
            ),
            "bank_limit": _compute_bank_limit_deg(idx),
            "pitch": _compute_pitch_deg(idx),
            "yaw": float(bs.traf.hdg[idx]),
            "wind_north_ms": _get_wind_north(idx),
            "wind_east_ms": _get_wind_east(idx),
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

        # Keep the defined-wind-points shadow list in
        # sync — catches WIND commands from any source.
        self._maybe_update_wind_points(cmd)

        # NOTE: PAN commands are no longer intercepted
        # here — they're handled per-client on the
        # frontend so one browser's ``PAN KDFW`` doesn't
        # reset every other user's view.  The resolver
        # is still exposed via REST
        # (``/api/pan/resolve``) for frontend use.

        # Notify listeners (e.g. WS broadcaster).
        for cb in list(self._cmd_listeners):
            try:
                cb(entry)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Command listener failed: %s", exc,
                )

    def _maybe_update_wind_points(self, cmd: str) -> None:
        """Parse a WIND command and update the shadow list.

        Also handles the custom origin marker used by the
        METAR-import path: when a command is prefixed with
        ``# origin=<tag>`` on the previous line or starts
        with the tag we set via ``_pending_origin``, the
        resulting wind point records that origin.
        Everything else (REST, console, scenario files,
        internal BlueSky code) defaults to origin="user".
        """
        parts = cmd.strip().replace(",", " ").split()
        if not parts or parts[0].upper() != "WIND":
            return
        try:
            lat = float(parts[1])
            lon = float(parts[2])
            tail = parts[3:]

            if tail and tail[0].upper() == "DEL":
                with self._wind_points_lock:
                    self._wind_points.clear()
                return

            origin = self._pending_origin or "user"

            with self._wind_points_lock:
                if len(tail) == 2:
                    # 2D form: dir spd
                    self._wind_points.append({
                        "lat": lat,
                        "lon": lon,
                        "altitude_ft": None,
                        "direction_deg": float(tail[0]),
                        "speed_kt": float(tail[1]),
                        "origin": origin,
                    })
                elif len(tail) >= 3 and len(tail) % 3 == 0:
                    # 3D form: triplets of (alt, dir, spd)
                    for i in range(0, len(tail), 3):
                        self._wind_points.append({
                            "lat": lat,
                            "lon": lon,
                            "altitude_ft": float(tail[i]),
                            "direction_deg": float(tail[i + 1]),
                            "speed_kt": float(tail[i + 2]),
                            "origin": origin,
                        })
        except (ValueError, IndexError):
            # Malformed WIND command — BlueSky will reject
            # it with its own error; don't mutate state.
            pass

    def get_wind_points(self) -> list[dict]:
        """Return a copy of the defined wind points."""
        with self._wind_points_lock:
            return [dict(p) for p in self._wind_points]

    # ── PAN target resolution ────────────────────────

    def _resolve_pan_target(
        self,
        identifier: str,
    ) -> dict | None:
        """Resolve identifier to lat/lon/view-alt/kind.

        Lookup order: aircraft → airport → waypoint →
        lat,lon pair.  Returns None if no match.
        """
        ident = identifier.upper().strip()

        # 1. Aircraft by callsign.
        try:
            idx = bs.traf.id2idx(ident)
            if idx >= 0:
                return {
                    "kind": "aircraft",
                    "lat": float(bs.traf.lat[idx]),
                    "lon": float(bs.traf.lon[idx]),
                    "alt_m_view": 100_000.0,
                }
        except (AttributeError, IndexError):
            pass

        # 2. Airport by ICAO.
        try:
            aptid = list(bs.navdb.aptid)
            if ident in aptid:
                i = aptid.index(ident)
                return {
                    "kind": "airport",
                    "lat": float(bs.navdb.aptlat[i]),
                    "lon": float(bs.navdb.aptlon[i]),
                    "alt_m_view": 50_000.0,
                }
        except (AttributeError, IndexError, ValueError):
            pass

        # 3. Waypoint / navaid.
        try:
            wpid = list(bs.navdb.wpid)
            if ident in wpid:
                i = wpid.index(ident)
                return {
                    "kind": "waypoint",
                    "lat": float(bs.navdb.wplat[i]),
                    "lon": float(bs.navdb.wplon[i]),
                    "alt_m_view": 100_000.0,
                }
        except (AttributeError, IndexError, ValueError):
            pass

        # 4. Explicit lat,lon.
        if "," in identifier:
            parts = [p.strip() for p in identifier.split(",")]
            if len(parts) == 2:
                try:
                    lat = float(parts[0])
                    lon = float(parts[1])
                    if (
                        -90 <= lat <= 90
                        and -180 <= lon <= 180
                    ):
                        return {
                            "kind": "latlon",
                            "lat": lat,
                            "lon": lon,
                            "alt_m_view": 50_000.0,
                        }
                except ValueError:
                    pass
        return None

    def delete_wind_point(
        self,
        lat: float,
        lon: float,
        altitude_ft: float | None,
    ) -> bool:
        """Delete one defined wind point.

        BlueSky does not support deleting a single wind
        point — ``WIND ... DEL`` clears the whole field.
        So we clear and replay every remaining point.

        Returns True if the point was found and removed,
        False otherwise.
        """
        with self._wind_points_lock:
            def _matches(p: dict) -> bool:
                return (
                    abs(p["lat"] - lat) < 1e-4
                    and abs(p["lon"] - lon) < 1e-4
                    and p["altitude_ft"] == altitude_ft
                )

            kept = [
                p for p in self._wind_points
                if not _matches(p)
            ]
            if len(kept) == len(self._wind_points):
                return False
            # Clear the shadow; the replayed WIND
            # commands will rebuild it via the hook.
            self._wind_points.clear()

        # Clear all wind in the sim, then replay.
        self.stack_command("WIND 0 0 DEL")
        # Group by (lat, lon): 2D points first (single
        # command each), then 3D triplets for same
        # (lat, lon) coalesced into one command.
        from collections import defaultdict
        pts_2d = [p for p in kept if p["altitude_ft"] is None]
        pts_3d = [p for p in kept if p["altitude_ft"] is not None]

        self._replay_wind_points(pts_2d, pts_3d)
        return True

    def _replay_wind_points(
        self,
        pts_2d: list[dict],
        pts_3d: list[dict],
    ) -> None:
        """Re-stack a list of wind points.

        Each point is stacked with its recorded origin
        so the shadow list keeps user / metar origins
        correctly.  Callers should hold the relevant
        lock *before* mutating ``_wind_points`` and
        then call this without the lock (stack_command
        doesn't need the wind lock).
        """
        from collections import defaultdict
        for p in pts_2d:
            self._pending_origin = p.get("origin", "user")
            self.stack_command(
                f"WIND {p['lat']:.4f} {p['lon']:.4f} "
                f"{p['direction_deg']:.1f} "
                f"{p['speed_kt']:.1f}"
            )
            self._pending_origin = None

        by_pos: dict[
            tuple[float, float, str], list[dict],
        ] = defaultdict(list)
        for p in pts_3d:
            origin = p.get("origin", "user")
            key = (
                round(p["lat"], 4),
                round(p["lon"], 4),
                origin,
            )
            by_pos[key].append(p)

        for (plat, plon, origin), plist in by_pos.items():
            plist_sorted = sorted(
                plist, key=lambda q: q["altitude_ft"] or 0,
            )
            triplets = " ".join(
                f"{p['altitude_ft']:.0f} "
                f"{p['direction_deg']:.1f} "
                f"{p['speed_kt']:.1f}"
                for p in plist_sorted
            )
            self._pending_origin = origin
            self.stack_command(
                f"WIND {plat} {plon} {triplets}"
            )
            self._pending_origin = None

    def import_metar_winds(
        self,
        observations: list[dict],
    ) -> int:
        """Replace METAR-origin wind points with a new set.

        ``observations`` items: {icao, lat, lon,
        wdir_deg, wspd_kt}.  Missing wind → skipped.

        Keeps user-origin points intact by clearing all
        wind and replaying the non-METAR subset plus
        the new METAR observations.  Returns the count
        of METAR winds actually stacked.
        """
        with self._wind_points_lock:
            user_pts = [
                p for p in self._wind_points
                if not (p.get("origin", "user"))
                .startswith("metar")
            ]
            self._wind_points.clear()

        # Clear all wind on the sim side.
        self.stack_command("WIND 0 0 DEL")

        # Replay user-origin points.
        user_2d = [
            p for p in user_pts
            if p["altitude_ft"] is None
        ]
        user_3d = [
            p for p in user_pts
            if p["altitude_ft"] is not None
        ]
        self._replay_wind_points(user_2d, user_3d)

        # Stack new METAR winds as 2D points.
        count = 0
        for obs in observations:
            try:
                lat = float(obs["lat"])
                lon = float(obs["lon"])
                wdir = obs.get("wdir_deg")
                wspd = obs.get("wspd_kt")
                if wdir is None or wspd is None:
                    continue
                # AWC returns "VRB" or numeric strings;
                # our normalized shape uses ints/floats.
                if not isinstance(wdir, (int, float)):
                    continue
                if not isinstance(wspd, (int, float)):
                    continue
                if wspd < 1:
                    # Effectively calm — don't pollute
                    # the field with zero-speed points.
                    continue
                icao = str(obs.get("icao") or "?")
                self._pending_origin = f"metar:{icao}"
                self.stack_command(
                    f"WIND {lat:.4f} {lon:.4f} "
                    f"{float(wdir):.1f} {float(wspd):.1f}"
                )
                self._pending_origin = None
                count += 1
            except (KeyError, TypeError, ValueError):
                continue
        return count

    def clear_metar_winds(self) -> int:
        """Remove METAR-origin wind points; keep user."""
        with self._wind_points_lock:
            user_pts = [
                p for p in self._wind_points
                if not (p.get("origin", "user"))
                .startswith("metar")
            ]
            removed = len(self._wind_points) - len(user_pts)
            self._wind_points.clear()
        self.stack_command("WIND 0 0 DEL")
        user_2d = [
            p for p in user_pts
            if p["altitude_ft"] is None
        ]
        user_3d = [
            p for p in user_pts
            if p["altitude_ft"] is not None
        ]
        self._replay_wind_points(user_2d, user_3d)
        return removed

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
                # Integrate smooth bank before BlueSky
                # runs its traffic update — we write
                # turnphi here, BlueSky reads it there.
                if bs.sim.state == bs.OP:
                    self.bank_controller.tick(
                        float(bs.sim.simdt),
                    )
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
