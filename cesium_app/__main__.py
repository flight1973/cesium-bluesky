"""Run the Cesium-BlueSky service directly: python -m cesium_app"""
import uvicorn
from cesium_app.config import settings

uvicorn.run(
    "cesium_app.main:app",
    host=settings.host,
    port=settings.port,
    log_level="info",
)
