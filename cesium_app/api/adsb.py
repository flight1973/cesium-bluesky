"""Local ADS-B (Mode-S Beast) data feed configuration.

Wraps BlueSky's built-in ``DATAFEED`` plugin
(``bluesky/plugins/adsbfeed.py``) with REST endpoints so
the frontend can configure the Mode-S Beast host/port and
turn the feed on/off without typing stack commands.

The plugin exposes a module-level ``reader`` object; we
reach into it to read connection status and update the
destination host/port dynamically.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/adsb", tags=["adsb"])


class AdsbConfig(BaseModel):
    host: str = Field("", description="Mode-S Beast hostname or IP")
    port: int = Field(0, ge=0, le=65535)


def _settings():
    import bluesky
    return bluesky.settings


def _reader():
    """Return the DATAFEED plugin's reader, or None."""
    try:
        from bluesky.plugins import adsbfeed
        return adsbfeed.reader
    except Exception:  # plugin may not be loaded yet
        return None


def _connected() -> bool:
    r = _reader()
    if r is None:
        return False
    try:
        return bool(r.isConnected())
    except Exception:
        return False


def _aircraft_count() -> int:
    r = _reader()
    if r is None:
        return 0
    try:
        return len(r.acpool)
    except Exception:
        return 0


@router.get("/config")
async def get_config() -> dict:
    s = _settings()
    return {
        "host": getattr(s, "modeS_host", ""),
        "port": int(getattr(s, "modeS_port", 0)),
        "connected": _connected(),
        "plugin_loaded": _reader() is not None,
        "tracked_aircraft": _aircraft_count(),
    }


@router.post("/config")
async def set_config(cfg: AdsbConfig) -> dict:
    s = _settings()
    # Ensure the attributes exist (plugin normally sets
    # defaults; if it hasn't loaded yet, create them).
    s.set_variable_defaults(modeS_host="", modeS_port=0)
    s.modeS_host = cfg.host
    s.modeS_port = int(cfg.port)
    return {
        "host": s.modeS_host,
        "port": s.modeS_port,
        "connected": _connected(),
    }


@router.post("/toggle")
async def toggle_feed(request: Request, on: bool) -> dict:
    """Turn the DATAFEED plugin on or off.

    When ``on=True`` the plugin will use the currently
    configured ``modeS_host``/``modeS_port`` to connect.
    Host/port should be set via ``POST /api/adsb/config``
    before enabling.
    """
    s = _settings()
    host = getattr(s, "modeS_host", "")
    port = int(getattr(s, "modeS_port", 0))
    if on and (not host or port <= 0):
        raise HTTPException(
            400,
            "modeS_host and modeS_port must be set before "
            "enabling DATAFEED",
        )
    bridge = request.app.state.bridge
    cmd = "DATAFEED ON" if on else "DATAFEED OFF"
    bridge.stack_command(cmd)
    return {
        "command": cmd,
        "host": host,
        "port": port,
    }


@router.get("/status")
async def status() -> dict:
    """Lightweight status poll for the UI indicator."""
    return {
        "connected": _connected(),
        "tracked_aircraft": _aircraft_count(),
    }
