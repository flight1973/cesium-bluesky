# Terrain Strategy — Plan

The goal: a terrain story that works **without Cesium
Ion**, supports **multiple free public DEM sources**,
is **offline-capable**, and has a **zero-setup path**
for quick starts. Achieved via a two-mode architecture
where the user picks which mode fits their needs.

## Two modes

### Mode A — Terrain Tiles (zero setup)

Cesium-BlueSky connects to the **Terrain Tiles** AWS
Open Data dataset (managed by Mapzen / Linux
Foundation; registry entry at
<https://registry.opendata.aws/terrain-tiles/>) and
streams tiles on demand. No preprocessing, no
downloads, works immediately.

- **Bucket**: `elevation-tiles-prod` (us-east-1),
  replica `elevation-tiles-prod-eu` (eu-central-1).
- **Tile formats in the bucket**:
  - **Terrarium** — PNG, RGB-encoded 16-bit heights.
    Used via a community `TerrariumTerrainProvider`
    for Cesium.
  - **Normal** — PNG normal maps for shading.
  - **GeoTIFF** — raw elevation data, readable by
    the backend for HAT computation.
- **Data sources** (blended into one global tile
  pyramid): SRTM, NED/3DEP, GMTED2010, ETOPO1
  (with bathymetry), ArcticDEM, EU-DEM, LINZ (NZ),
  UK LIDAR, Austria DGM, Norway DTM, Canada CDEM,
  Mexico INEGI, Australia DEM.
- **Licensing**: all sources permit commercial use.
  **Attribution is required** for every upstream
  source whose data we actually use, displayed in
  the UI. See
  <https://github.com/tilezen/joerd/blob/master/docs/attribution.md>
  for the canonical list.
- **AWS cost**: anonymous access is permitted
  without an AWS account, which strongly implies
  egress is sponsored, but this is not explicitly
  stated on the registry page. Treat as "likely
  free" with a worst-case of normal S3 egress rates
  (~$0.09/GB, sub-dollar at research scale — see
  earlier analysis).

**Good for:** first-time users, demos, quick evaluations,
low-traffic deployments.

**Constraints:** requires internet; depends on the
dataset staying available (it's maintained and has
been reliable for years, but no SLA); not Cesium's
native quantized-mesh format (needs a community
provider); no local cache control.

### Mode B — Self-hosted quantized-mesh (production)

The user picks a DEM source (from a documented menu of
free public datasets), downloads it, runs a build
pipeline that produces a **quantized-mesh tileset**,
and Cesium-BlueSky serves it from the same FastAPI
process at `/terrain/{z}/{x}/{y}.terrain`.

**Good for:** production deployments, air-gapped
installs, performance-sensitive use, full control.

**Constraints:** one-time setup (download + build
pipeline can take minutes for regional DEMs, hours
for global).

### Mode C — Cesium Ion (optional upgrade)

When the user has an Ion token, they can opt into
Cesium World Terrain for higher resolution than free
sources typically provide. Treated as a quality
upgrade, not a dependency; the rest of the app never
requires it.

## Source catalog

Free public DEMs the build pipeline supports:

| Source | Coverage | Resolution | Size (global) | Hosted on AWS Open Data? | Notes |
|---|---|---|---|---|---|
| **GMTED2010** | Global (land) | 30" (~1 km) | ~2.5 GB | Yes (in Terrain Tiles aggregate) | Baseline default. |
| **SRTM v3 90m** | 60°N–60°S (land) | 3" (~90 m) | ~12 GB | Yes (in Terrain Tiles aggregate) | No polar coverage. |
| **SRTM v3 30m** | 60°N–60°S (land) | 1" (~30 m) | ~350 GB | Direct USGS/NASA + Terrain Tiles | Tile by 1°×1°. |
| **Copernicus DEM GLO-90** | Global (land) | 90 m | ~90 GB | **Yes — `copernicus-dem-90m` (eu-central-1)**, Cloud-Optimized GeoTIFF | ESA license, free for general public. |
| **Copernicus DEM GLO-30** | Global (land) | 30 m | ~400 GB | **Yes — `copernicus-dem-30m` (eu-central-1)**, Cloud-Optimized GeoTIFF | Research-grade. |
| **GEBCO 2024** | Global + bathymetry | 15" (~450 m) | ~8 GB | No (not on AWS Open Data) | Download direct from gebco.net. |
| **USGS 3DEP lidar** | US only | ~10 m | large (varies) | Likely (unverified) | US high-resolution. |
| **ASTER GDEM v3** | ±83° latitude | 1" (~30 m) | ~250 GB | No | Earthdata login required. |
| **Custom GeoTIFF** | User-supplied | Variable | Variable | — | Any `rasterio`-compatible raster. |

Access patterns vary by source:

- **AWS Open Data** (Copernicus DEM, USGS 3DEP,
  GEBCO) — direct S3 reads, no auth.
- **USGS / NASA EarthData** (SRTM) — registration
  required for some tiers.
- **EarthExplorer** (USGS) — GUI + API.
- **LP DAAC** (ASTER GDEM) — registration.
- **CGIAR-CSI** (SRTM 90m pre-packaged) — direct
  HTTP.

The pipeline normalizes these into a consistent
internal format regardless of source.

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Frontend (Cesium viewer)                        │
│                                                  │
│  Mode A:  TerrariumTerrainProvider               │
│           → s3://elevation-tiles-prod/...        │
│                                                  │
│  Mode B:  CesiumTerrainProvider                  │
│           → /terrain/{z}/{x}/{y}.terrain         │
│                                                  │
│  Mode C:  CesiumTerrainProvider via Ion          │
│           → IonResource.fromAssetId(1)           │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────┐
│  FastAPI service                                 │
│                                                  │
│  GET /terrain/{z}/{x}/{y}.terrain                │
│    → serve quantized-mesh tile from              │
│      data/terrain-tiles/<source>/                │
│                                                  │
│  GET /api/terrain/config                         │
│    → current mode, source, coverage extent       │
│                                                  │
│  POST /api/terrain/build                         │
│    → kick off the build pipeline (async)         │
│                                                  │
│  GET /api/terrain/build/status                   │
│    → progress of an in-flight build              │
│                                                  │
│  Backend HAT source:                             │
│    class TerrainSource:                          │
│      elevation(lat, lon) -> float                │
│      elevation_batch(lats, lons) -> ndarray      │
│                                                  │
│    Implementations:                              │
│      FlatTerrain                                 │
│      RasterTerrain(GeoTIFF dir)  # Mode B        │
│      TerrariumProxyTerrain        # Mode A       │
└──────────────────────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────┐
│  Build pipeline (tools/build-terrain.py)         │
│                                                  │
│  Inputs:                                         │
│    --source <catalog-id | path>                  │
│    --region <bbox | country | global>            │
│    --resolution <1 | 3 | 30 | 90>  (arc-sec)     │
│    --output data/terrain-tiles/<name>/           │
│                                                  │
│  Steps:                                          │
│    1. Download source tiles (resumable, parallel)│
│    2. Merge / mosaic with gdal                   │
│    3. Reproject to EPSG:4326 if needed           │
│    4. Run cesium-terrain-builder → QM tiles      │
│    5. Write layer.json + tile tree               │
│    6. Register with service config               │
└──────────────────────────────────────────────────┘
```

## Tooling choices

**Quantized-mesh generator** (pick one):

| Tool | Language | Container | Notes |
|---|---|---|---|
| `cesium-terrain-builder` (CTB) | C++ | Official Docker image | Mature, well-tested. Recommended. |
| `tin-terrain` | Rust | `heremaps/tin-terrain` | Alternative. Faster for some inputs. |
| `py-ct` (pure Python) | Python | — | Slowest; no external deps. For fallback only. |

**DEM reading:**
- `rasterio` — Python bindings for GDAL, handles all
  our input formats.
- `numpy` — batch interpolation for backend HAT.

**Tile serving:**
- FastAPI `StaticFiles` can serve the tile tree
  directly. Add caching headers; tiles are
  immutable per build.

## User flow

### First launch (zero setup)

1. App starts; no terrain configured.
2. Defaults to **Mode A (Terrarium)** → rendering
   works immediately via AWS.
3. Backend HAT uses a **`FlatTerrain` fallback** until
   Mode B is set up; HAT returns `None` or 0.
4. UI banner: *"Terrain: Terrarium (online). For
   offline or higher precision, set up a local DEM
   in Settings."*

### Upgrade to self-hosted

1. User opens **Settings → Terrain** (new section).
2. Picks a source from a dropdown (with size /
   coverage / resolution shown).
3. Picks a region (*global*, or a bbox, or a country
   preset).
4. Clicks **Build** → pipeline starts.
5. Progress bar tracks download + build (long
   operations, possibly hours for global 30 m).
6. When done, viewer auto-switches to
   `/terrain/{source}/`; backend HAT switches to
   `RasterTerrain`.
7. User can return later to add regions or switch
   sources.

### Adding a custom source

1. User drops a GeoTIFF (or directory of GeoTIFFs)
   into `data/custom-dem/`.
2. Picks **Custom** in the dropdown, points at that
   path.
3. Pipeline treats it identically to a catalog
   source.

## Implementation phases

### Phase 1 — Mode A only (zero setup)

- Community `TerrariumTerrainProvider` adapter.
- Backend HAT is `FlatTerrain` (returns 0).
- No build pipeline yet. Just works immediately.
- Ship with a banner explaining the upgrade path.

*Effort:* small. Delivers a working 3D globe
without Ion.

### Phase 2 — Mode B with GMTED2010 baseline

- Add `RasterTerrain` backend HAT source.
- Write `tools/build-terrain.py` for GMTED2010.
- Build pipeline runs via CLI only (no UI yet).
- Serve `/terrain/{z}/{x}/{y}.terrain`.
- Backend HAT uses the same GeoTIFF directly for
  per-point lookups.

*Effort:* medium. Most of the infrastructure.

### Phase 3 — Source catalog & UI

- Expand `build-terrain.py` to handle SRTM,
  Copernicus, GEBCO, USGS 3DEP, custom.
- Add **Settings → Terrain** UI:
  - Current mode display.
  - Source dropdown + region picker.
  - Build button with progress.
- Add `POST /api/terrain/build` + status endpoint.

*Effort:* medium. The user-facing polish.

### Phase 4 — Advanced

- Region-limited builds (pick a bbox, skip global).
- Multi-source overlays (e.g., GMTED2010 baseline +
  Copernicus GLO-30 patch over Europe).
- Delta updates (patch a built tileset without
  full rebuild).
- Sharing prebuilt tilesets between users (publish
  to S3 / CDN).

*Effort:* large. Nice-to-have, not critical.

## Disk budget

Rough targets for common configurations:

- **GMTED2010 global baseline:** ~2.5 GB raw,
  ~3 GB of quantized-mesh tiles. Total ~5.5 GB.
- **SRTM 90m global:** ~12 GB raw, ~15 GB tiles.
  Total ~27 GB.
- **Copernicus GLO-30 global:** ~400 GB raw,
  ~500 GB tiles. Total ~900 GB — usually too much
  for a dev install. Build regionally.
- **Regional Europe at 30m:** ~15 GB raw, ~20 GB
  tiles. Total ~35 GB.

Documented in the terrain setup UI so users know
what they're committing to before clicking Build.

## Open questions

1. **Default mode** — Terrarium or "user must pick"
   on first launch? I'd lean Terrarium for zero
   friction, but a modal explaining the upgrade
   path is important.
2. **Where to store tilesets** — bundle `data/` in
   project root, or use `~/.cesium-bluesky/terrain/`
   so multiple checkouts share? Latter is nicer but
   adds a platform-specific path question.
3. **Background vs. foreground builds** — the
   pipeline can run hours. Should it be a
   background task inside FastAPI, a separate CLI
   users must run themselves, or a sidecar process
   the app manages? I'd lean CLI-first for control,
   API second for progress visibility.
4. **Sharing built tilesets** — a community could
   publish prebuilt GMTED2010 / SRTM 90m tilesets to
   a public bucket, skipping the build step. Worth
   a later phase.
5. **How does this compose with Ion?** — if a user
   has both a built tileset and an Ion token, does
   the viewer offer a toggle? Probably yes; the
   VIEW tab already has a Terrain dropdown — extend
   it to include Mode-B sources.
6. **Coordinate reference frames** — DEM sources
   specify elevation in different references (HAE,
   orthometric / MSL with different geoids). The
   build pipeline must convert to a consistent
   reference before producing tiles. Related to the
   [altitude references plan](project_altitude_references).
