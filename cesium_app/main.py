"""FastAPI application for Cesium-BlueSky ATM simulator.

Run as a service::

    uvicorn cesium_app.main:app --host 0.0.0.0 --port 8000

Or directly::

    python -m cesium_app
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cesium_app.api import areas
from cesium_app.api import commands
from cesium_app.api import navdata
from cesium_app.api import scenario
from cesium_app.api import simulation
from cesium_app.api import state as state_api
from cesium_app.api import traffic
from cesium_app.config import settings
from cesium_app.sim.bridge import SimBridge
from cesium_app.ws import streams as ws_streams

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start BlueSky on startup, stop on shutdown.

    This makes the app behave as a proper service --
    systemd / launchd can start and stop it cleanly via
    SIGTERM.
    """
    bridge = SimBridge(
        scenario_file=settings.scenario_file,
        workdir=settings.bluesky_workdir,
    )
    bridge.start()
    app.state.bridge = bridge
    logger.info("Cesium-BlueSky service ready")

    # Start the WebSocket broadcast background task.
    broadcast_task = asyncio.create_task(
        ws_streams.broadcast_loop(app),
    )
    yield
    broadcast_task.cancel()
    bridge.stop()
    logger.info("Cesium-BlueSky service shut down")


app = FastAPI(
    title="Cesium-BlueSky",
    description=(
        "Web API for BlueSky ATM simulator "
        "with CesiumJS frontend"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS -- allow the Vite dev server during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers.
app.include_router(simulation.router)
app.include_router(commands.router)
app.include_router(traffic.router)
app.include_router(scenario.router)
app.include_router(navdata.router)
app.include_router(areas.router)
app.include_router(state_api.router)
app.include_router(ws_streams.router)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint for service monitoring."""
    bridge: SimBridge = app.state.bridge
    return {
        "status": (
            "healthy" if bridge.is_running else "degraded"
        ),
        "sim_running": bridge.is_running,
    }


@app.get("/api/config/cesium")
async def cesium_config() -> dict:
    """Return Cesium Ion token if configured.

    The frontend uses this to decide whether to enable
    Ion imagery/terrain or fall back to open basemaps.
    """
    token = settings.cesium_ion_token
    return {
        "ion_token": token if token else None,
    }


# Serve built frontend static files (after API routes).
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=_static_dir / "assets"),
        name="assets",
    )
    app.mount(
        "/cesium",
        StaticFiles(directory=_static_dir / "cesium"),
        name="cesium",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve the SPA index.html for non-API routes."""
        return FileResponse(_static_dir / "index.html")
