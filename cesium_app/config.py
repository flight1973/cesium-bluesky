"""Application configuration."""
from pathlib import Path

from pydantic_settings import BaseSettings

# Default workdir: the bluesky source tree
# (contains scenarios, plugins, etc.)
_DEFAULT_WORKDIR: str = str(
    Path(__file__).resolve().parent.parent / "bluesky"
)


class Settings(BaseSettings):
    """Cesium-BlueSky application settings.

    Attributes:
        host: Bind address for the HTTP server.
        port: Port number for the HTTP server.
        cesium_ion_token: Cesium Ion API access token.
        scenario_file: Optional scenario to load on startup.
        bluesky_workdir: Path to the BlueSky working directory.
    """

    host: str = "0.0.0.0"
    port: int = 8000
    cesium_ion_token: str = ""
    scenario_file: str | None = None
    bluesky_workdir: str = _DEFAULT_WORKDIR

    model_config = {"env_prefix": "CESIUM_BLUESKY_"}


settings = Settings()
