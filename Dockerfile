# ── Stage 1: Frontend build ──────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build
# Output: ../cesium_app/static/ (relative to frontend/)

# ── Stage 2: Python runtime ──────────────────────────
FROM python:3.12-slim AS runtime

# System deps: PROJ (pyproj/geoid), curl (healthcheck),
# GDAL (chart tiling — adds ~200 MB but keeps everything
# in one container so `docker compose up` just works).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libproj-dev proj-data curl \
    gdal-bin python3-gdal \
    libspatialindex-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps — install before copying source for
# better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY cesium_app/ ./cesium_app/
COPY bluesky/ ./bluesky/

# Copy built frontend from Stage 1
COPY --from=frontend-build /app/cesium_app/static/ ./cesium_app/static/

# Copy docs + data scaffolding
COPY docs/ ./docs/
COPY data/ddr2/README.md data/ddr2/.gitignore ./data/ddr2/

# Download EGM2008 geoid grid (~80 MB) at build time
# so it's baked into the image.  Falls back gracefully
# if the download fails (geoid stub returns N=0).
RUN mkdir -p data/proj_grids && \
    projsync --file us_nga_egm08_25.tif \
    --target-dir data/proj_grids 2>/dev/null || \
    echo "Geoid download failed; HAE≡MSL until grid is installed"

# Ensure both cesium_app and the bluesky subdir
# (which nests its own bluesky/ Python package)
# are importable.
ENV PYTHONPATH=/app:/app/bluesky

# Default port
EXPOSE 8000

# Health check — /api/health returns {"status":"healthy"}
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with uvicorn.  Use --workers for production;
# default 1 is fine for dev/demo.
CMD ["uvicorn", "cesium_app.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
