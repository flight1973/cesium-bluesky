"""Pydantic models for simulation state and control."""
from pydantic import BaseModel


class SimInfo(BaseModel):
    """Current simulation state snapshot.

    Attributes:
        simt: Simulation time in seconds.
        simdt: Simulation timestep in seconds.
        utc: Simulated UTC time string.
        dtmult: Speed multiplier.
        ntraf: Number of active aircraft.
        state: Numeric state (0=INIT, 1=HOLD, 2=OP, 3=END).
        state_name: Human-readable state name.
        scenname: Name of the loaded scenario.
    """

    simt: float
    simdt: float
    utc: str
    dtmult: float
    ntraf: int
    state: int
    state_name: str
    scenname: str


class SimDtmult(BaseModel):
    """Request body for setting simulation speed.

    Attributes:
        multiplier: Speed multiplier (e.g. 2.0 = double).
    """

    multiplier: float


class SimFastForward(BaseModel):
    """Request body for fast-forwarding the simulation.

    Attributes:
        seconds: Number of seconds to fast-forward.
    """

    seconds: float
