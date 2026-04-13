"""Pydantic models for aircraft data."""
from pydantic import BaseModel


class AircraftCreate(BaseModel):
    """Request body for creating a new aircraft.

    Attributes:
        acid: Aircraft callsign (e.g. "KL204").
        actype: ICAO aircraft type code (e.g. "B738").
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        hdg: Initial heading in degrees.
        alt: Initial altitude in feet.
        spd: Initial speed in knots CAS or Mach.
    """

    acid: str
    actype: str = "B738"
    lat: float
    lon: float
    hdg: float = 0.0
    alt: float = 0.0
    spd: float = 0.0


class AircraftState(BaseModel):
    """Current state of a single aircraft.

    Attributes:
        acid: Aircraft callsign.
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        alt: Altitude in meters.
        tas: True airspeed in m/s.
        cas: Calibrated airspeed in m/s.
        gs: Ground speed in m/s.
        trk: Track angle in degrees.
        vs: Vertical speed in m/s.
    """

    acid: str
    lat: float
    lon: float
    alt: float
    tas: float
    cas: float
    gs: float
    trk: float
    vs: float


class AircraftSetValue(BaseModel):
    """Request body for HDG, ALT, SPD, VS commands.

    Attributes:
        value: The target value to set.
    """

    value: float


class AircraftToggle(BaseModel):
    """Request body for LNAV/VNAV toggles.

    Attributes:
        on: Whether to enable (True) or disable (False).
    """

    on: bool = True


class AddWaypoint(BaseModel):
    """Request body for adding a waypoint to a route.

    Attributes:
        wpname: Waypoint name or ICAO identifier.
        alt: Optional altitude constraint in feet.
        spd: Optional speed constraint in knots.
    """

    wpname: str
    alt: float | None = None
    spd: float | None = None


class RouteData(BaseModel):
    """Flight plan / route data for an aircraft.

    Attributes:
        acid: Aircraft callsign.
        iactwp: Index of the active waypoint.
        aclat: Current aircraft latitude.
        aclon: Current aircraft longitude.
        wplat: Waypoint latitudes.
        wplon: Waypoint longitudes.
        wpalt: Waypoint altitude constraints in meters.
        wpspd: Waypoint speed constraints in m/s.
        wpname: Waypoint names.
    """

    acid: str
    iactwp: int
    aclat: float
    aclon: float
    wplat: list[float]
    wplon: list[float]
    wpalt: list[float]
    wpspd: list[float]
    wpname: list[str]
