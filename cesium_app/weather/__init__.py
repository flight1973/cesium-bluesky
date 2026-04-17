"""Weather data integration.

Adapters for aviationweather.gov, NOAA NODD / AWS
Open Data (NEXRAD, HRRR, GOES), and ECMWF.  Each
source module exposes a ``fetch`` + ``cache`` surface
that the REST layer in :mod:`cesium_app.api.weather`
consumes.

First-pass scope: METARs from aviationweather.gov.
SIGMETs, AIRMETs, PIREPs, NEXRAD, HRRR, GOES are
tracked in ``project_weather_data.md``.
"""
