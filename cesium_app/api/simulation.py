"""REST endpoints for simulation control."""
from fastapi import APIRouter, Request

from cesium_app.models.simulation import SimDtmult
from cesium_app.models.simulation import SimFastForward
from cesium_app.models.simulation import SimInfo
from cesium_app.sim.bridge import SimBridge

router = APIRouter(prefix="/api/sim", tags=["simulation"])


def _bridge(request: Request) -> SimBridge:
    """Extract the SimBridge from app state."""
    return request.app.state.bridge


@router.get("/info", response_model=SimInfo)
async def get_sim_info(request: Request) -> dict:
    """Get current simulation state."""
    return _bridge(request).get_sim_info()


@router.post("/op")
async def sim_op(request: Request) -> dict:
    """Start or resume the simulation."""
    _bridge(request).stack_command("OP")
    return {"status": "ok", "command": "OP"}


@router.post("/hold")
async def sim_hold(request: Request) -> dict:
    """Pause the simulation."""
    _bridge(request).stack_command("HOLD")
    return {"status": "ok", "command": "HOLD"}


@router.post("/reset")
async def sim_reset(request: Request) -> dict:
    """Reset the simulation to initial state."""
    _bridge(request).stack_command("RESET")
    return {"status": "ok", "command": "RESET"}


@router.post("/ff")
async def sim_fast_forward(
    request: Request,
    body: SimFastForward,
) -> dict:
    """Fast-forward simulation by a number of seconds."""
    cmd = f"FF {body.seconds}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}


@router.post("/dtmult")
async def sim_dtmult(
    request: Request,
    body: SimDtmult,
) -> dict:
    """Set simulation speed multiplier."""
    cmd = f"DTMULT {body.multiplier}"
    _bridge(request).stack_command(cmd)
    return {"status": "ok", "command": cmd}
