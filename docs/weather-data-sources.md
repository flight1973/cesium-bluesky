# Weather Data Sources for Cesium / Cesium for Unity

Comprehensive catalog of weather data sources organized by
phenomenon, covering both **tile/imagery services** (WMS /
WMTS / ArcGIS MapServer — for Cesium globe overlays) and
**GeoJSON endpoints** (for structured feature rendering in
Cesium or Cesium for Unity).

All sources listed are **free and public** unless marked
otherwise.  Sources requiring credentials are noted with 🔑.

---

## GetCapabilities URL Notes

**IEM (Iowa State Mesonet)** — all WMS GetCapabilities
confirmed working (HTTP 200).  Append
`?service=WMS&version=1.1.1&request=GetCapabilities`
to any IEM WMS base URL.

**NWS (mapservices.weather.noaa.gov)** — ArcGIS REST
services declare `supportedExtensions: WMSServer` in
their metadata, but the WMS endpoint returns HTTP 400
on programmatic GetCapabilities probes as of April
2026.  **Use the ArcGIS REST URL directly** with
Cesium's `ArcGisMapServerImageryProvider` — this is
the primary supported consumption path and doesn't
need WMS.

**nowCOAST** — WMS endpoints returning HTTP 403 as of
April 2026 (domain may have migrated to
`new.nowcoast.noaa.gov`).  ArcGIS REST access still
works.

---

## 1. RADAR / PRECIPITATION (Reflectivity)

### Tile / Imagery Services

| Service | URL | Protocol | GetCapabilities | Refresh | Coverage | Notes |
|---|---|---|---|---|---|---|
| **NWS MRMS Radar** | `mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity/MapServer` | ArcGIS REST | Use REST directly (`?f=json` for metadata) | 5 min | CONUS + PR + HI + AK + GU | Best quality; MRMS composited from all WSR-88D radars |
| **NWS MRMS Radar (time-enabled)** | `mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity_time/ImageServer` | ArcGIS REST | Use REST directly | 5 min | Same | 4-hour time slider window |
| **nowCOAST NEXRAD** | `nowcoast.noaa.gov/arcgis/rest/services/nowcoast/radar_meteo_imagery_nexrad_time/MapServer` | ArcGIS REST | Use REST directly | 5 min | CONUS | Alternative endpoint; same MRMS data |
| **IEM NEXRAD Base Reflectivity** | `mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q.cgi` | WMS 1.1.1 | ✅ `…/n0q.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | 5 min | CONUS | Iowa State Mesonet; very reliable |
| **IEM NEXRAD Base Reflectivity (XYZ tiles)** | `mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png` | XYZ tiles | n/a (tile URL, no capabilities) | 5 min | CONUS | Drop-in for `UrlTemplateImageryProvider` |
| **IEM NEXRAD (time-enabled WMS-T)** | `mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi` | WMS-T | ✅ `…/n0q-t.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | Historical | CONUS | Replay past radar |
| **IEM Net Echo Tops** | `mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/eet.cgi` | WMS | ✅ `…/eet.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | 5 min | CONUS | Echo top heights — useful for convective depth |
| **IEM Storm Total Precip** | `mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/dta.cgi` | WMS | ✅ `…/dta.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | 5 min | CONUS | Accumulated precipitation |
| **IEM 1-Hour Precip** | `mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/daa.cgi` | WMS | ✅ `…/daa.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | Hourly | CONUS | Short-duration accumulation |
| **NWS MRMS QPE** | `mapservices.weather.noaa.gov/raster/rest/services/obs/mrms_qpe/ImageServer` | ArcGIS REST | Use REST directly | Hourly | CONUS | Quantitative Precipitation Estimate |
| **NWS RFC QPE** | `mapservices.weather.noaa.gov/raster/rest/services/obs/rfc_qpe/MapServer` | ArcGIS REST | Use REST directly | Hourly | CONUS | River Forecast Center estimates |
| **OpenWeatherMap Precipitation** | `tile.openweathermap.org/map/precipitation_new/{z}/{x}/{y}.png?appid={key}` | XYZ tiles | n/a (tile URL) | 10 min | Global | 🔑 Free tier (1M req/mo) |

### GeoJSON / Feature Endpoints

| Endpoint | URL | Data | Refresh |
|---|---|---|---|
| (Radar data is raster-only; no GeoJSON equivalent) | — | — | — |

---

## 2. CONVECTIVE ACTIVITY (Thunderstorms / Severe Weather)

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **NWS SPC Convective Outlooks** | `mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/MapServer` | ArcGIS REST | 4× daily | CONUS |
| **NWS SPC Mesoscale Discussions** | `mapservices.weather.noaa.gov/vector/rest/services/outlooks/spc_mesoscale_discussion/MapServer` | ArcGIS REST | As issued | CONUS |
| **NWS Watches/Warnings/Advisories** | `mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer` | ArcGIS REST | Minutes | CONUS |
| **nowCOAST Severe Watches** | `nowcoast.noaa.gov/arcgis/rest/services/nowcoast/wwa_meteoceanhydro_shortduration_hazards_watches_time/MapServer` | ArcGIS REST / WMS | Minutes | CONUS |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **SIGMETs (Convective)** | `aviationweather.gov/api/data/airsigmet?format=geojson` | Convective SIGMETs — polygon boundaries, hazard qualifier | ✅ | 5 min |
| **CWAs** | `aviationweather.gov/api/data/cwa?format=geojson` | Center Weather Advisories — short-term convective hazards | ✅ | 5 min |
| **International SIGMETs** | `aviationweather.gov/api/data/isigmet?format=geojson` | TC / TS / embedded CB — polygon + movement | ✅ | 15 min |
| **G-AIRMETs** | `aviationweather.gov/api/data/gairmet?format=geojson` | Graphical AIRMETs incl. thunderstorm areas | ✅ | 3 hr |
| **TCF (Convective Forecast)** | `aviationweather.gov/api/data/tcf?format=geojson` | TFM Convective Forecast (US + S. Canada) | ✅ | Hourly |

---

## 3. TURBULENCE

### Tile / Imagery Services

| Service | URL | Protocol | Notes |
|---|---|---|---|
| **AWC GFA Turbulence layers** | Internal to aviationweather.gov GFA tool | Not directly exposed as WMS | Viewable in the GFA web app; scraping the internal tile URL is possible but unsupported |
| **NOAA WAFS (World Area Forecast System)** | `aviationweather.gov/wifs/` | GRIB2 gridded data (not tiles) | 🔑 WIFS API for gridded icing/turb/CB forecasts; requires processing to render as tiles |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **SIGMETs (Turbulence)** | `aviationweather.gov/api/data/airsigmet?format=geojson` | TURB-qualified SIGMETs — polygon + altitude band | ✅ | 5 min |
| **G-AIRMETs (Turbulence)** | `aviationweather.gov/api/data/gairmet?format=geojson` | Graphical AIRMET turbulence areas | ✅ | 3 hr |
| **PIREPs (Turbulence)** | `aviationweather.gov/api/data/pirep?format=geojson` | Pilot reports with TB qualifier — 3D points | ✅ | 2 min |

---

## 4. ICING

### Tile / Imagery Services

| Service | URL | Protocol | Notes |
|---|---|---|---|
| **NOAA WAFS Icing Forecast** | `aviationweather.gov/wifs/` | GRIB2 gridded | 🔑 Gridded icing severity/probability by FL; needs tiling pipeline |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **SIGMETs (Icing)** | `aviationweather.gov/api/data/airsigmet?format=geojson` | ICE-qualified SIGMETs — polygon + altitude | ✅ | 5 min |
| **G-AIRMETs (Icing)** | `aviationweather.gov/api/data/gairmet?format=geojson` | Graphical AIRMET icing areas | ✅ | 3 hr |
| **PIREPs (Icing)** | `aviationweather.gov/api/data/pirep?format=geojson` | Pilot reports with IC qualifier — 3D points | ✅ | 2 min |

---

## 5. CEILING & VISIBILITY (IFR Conditions)

### Tile / Imagery Services

| Service | URL | Protocol | Notes |
|---|---|---|---|
| **AWC GFA Ceiling & Visibility** | Internal to GFA tool | Not directly exposed as WMS | Forecast ceilings / visibility at FL surface through FL120 |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **METARs** | `aviationweather.gov/api/data/metar?format=geojson` | Station observations — ceiling, visibility, flight category (VFR/MVFR/IFR/LIFR) | ✅ | 5 min |
| **TAFs** | `aviationweather.gov/api/data/taf?format=geojson` | Forecast ceiling + visibility per time block | ✅ | 30 min |
| **G-AIRMETs (IFR)** | `aviationweather.gov/api/data/gairmet?format=geojson` | IFR / mountain-obscuration areas | ✅ | 3 hr |

---

## 6. TEMPERATURE

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **NWS NDFD Temperature** | `mapservices.weather.noaa.gov/raster/rest/services/NDFD/NDFD_temp/MapServer` | ArcGIS REST | 6 hr | CONUS |
| **NWS SST (Sea Surface Temp)** | `mapservices.weather.noaa.gov/raster/rest/services/climate/cpc_wkly_sst/MapServer` | ArcGIS REST | Weekly | Global ocean |
| **OpenWeatherMap Temperature** | `tile.openweathermap.org/map/temp_new/{z}/{x}/{y}.png?appid={key}` | XYZ tiles | 10 min | Global | 🔑 |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **METARs** | `aviationweather.gov/api/data/metar?format=geojson` | Surface temp + dewpoint per station | ✅ | 5 min |
| **TAFs** | `aviationweather.gov/api/data/taf?format=geojson` | (No temp directly; inferred from forecast blocks) | ✅ | 30 min |

---

## 7. WIND

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **OpenWeatherMap Wind** | `tile.openweathermap.org/map/wind_new/{z}/{x}/{y}.png?appid={key}` | XYZ tiles | 10 min | Global | 🔑 |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **METARs** | `aviationweather.gov/api/data/metar?format=geojson` | Surface wind direction + speed + gust | ✅ | 5 min |
| **TAFs** | `aviationweather.gov/api/data/taf?format=geojson` | Forecast wind per block (dir / spd / gust) | ✅ | 30 min |
| **PIREPs** | `aviationweather.gov/api/data/pirep?format=geojson` | Wind at altitude from pilot reports | ✅ | 2 min |

---

## 8. VOLCANIC ASH / SMOKE / AIR QUALITY

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **NWS Surface Smoke (1-hr avg)** | `mapservices.weather.noaa.gov/raster/rest/services/air_quality/ndgd_smoke_sfc_1hr_avg_time/ImageServer` | ArcGIS REST | Hourly | CONUS |
| **NWS Vertically Integrated Smoke** | `mapservices.weather.noaa.gov/raster/rest/services/air_quality/ndgd_smoke_vert_1hr_avg_time/ImageServer` | ArcGIS REST | Hourly | CONUS |
| **NWS Dust Surface** | `mapservices.weather.noaa.gov/raster/rest/services/air_quality/ndgd_dust_sfc_time/ImageServer` | ArcGIS REST | Hourly | CONUS |
| **NWS PM2.5 (fine particulate)** | `mapservices.weather.noaa.gov/raster/rest/services/air_quality/ndgd_apm25_hr01/ImageServer` | ArcGIS REST | Hourly | CONUS |
| **NWS Ozone** | `mapservices.weather.noaa.gov/raster/rest/services/air_quality/ndgd_ozone_1hr_avg_time/ImageServer` | ArcGIS REST | Hourly | CONUS |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **International SIGMETs (VA)** | `aviationweather.gov/api/data/isigmet?format=geojson` | Volcanic ash SIGMETs — polygon + movement + altitude | ✅ | 15 min |

---

## 9. SATELLITE IMAGERY (Clouds)

### Tile / Imagery Services

| Service | URL | Protocol | GetCapabilities | Refresh | Coverage | Notes |
|---|---|---|---|---|---|---|
| **IEM GOES Visible** | `mesonet.agron.iastate.edu/cgi-bin/wms/goes/conus_vis.cgi` | WMS | ✅ `…/conus_vis.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | 5 min | CONUS | Daytime only |
| **IEM GOES IR** | `mesonet.agron.iastate.edu/cgi-bin/wms/goes/conus_ir.cgi` | WMS | ✅ `…/conus_ir.cgi?service=WMS&version=1.1.1&request=GetCapabilities` | 15 min | CONUS | Day + night |
| **nowCOAST Satellite** | `nowcoast.noaa.gov/arcgis/rest/services/nowcoast/sat_meteo_imagery_time/MapServer` | ArcGIS REST | Use REST directly | 15 min | CONUS + adjacent | GOES-16/17/18 composite |
| **OpenWeatherMap Clouds** | `tile.openweathermap.org/map/clouds_new/{z}/{x}/{y}.png?appid={key}` | XYZ tiles | n/a (tile URL) | 10 min | Global | 🔑 |

---

## 10. SNOW / ICE (Surface)

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **NWS Snow Analysis** | `mapservices.weather.noaa.gov/raster/rest/services/snow/NOHRSC_Snow_Analysis/MapServer` | ArcGIS REST | Daily | CONUS |
| **NWS IMS Snow/Ice (1km)** | `mapservices.weather.noaa.gov/raster/rest/services/obs/usnic_ims_snow_ice_1km/ImageServer` | ArcGIS REST | Daily | Northern Hemisphere |

---

## 11. HAZARD OUTLOOKS / WATCHES / WARNINGS

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **NWS Watches/Warnings/Advisories** | `mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer` | ArcGIS REST + FeatureServer | Minutes | US |
| **NWS SPC Storm Outlooks** | `mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/MapServer` | ArcGIS REST | 4× daily | CONUS |
| **NWS CPC Weather Hazards** | `mapservices.weather.noaa.gov/vector/rest/services/hazards/cpc_weather_hazards/MapServer` | ArcGIS REST | Daily | CONUS |
| **NWS Precip Hazards** | `mapservices.weather.noaa.gov/vector/rest/services/hazards/wpc_precip_hazards/MapServer` | ArcGIS REST | 6 hr | CONUS |
| **NWS Flash Flood Guidance** | `mapservices.weather.noaa.gov/raster/rest/services/precip/rfc_gridded_ffg/MapServer` | ArcGIS REST | Hourly | CONUS |

---

## 12. SURFACE OBSERVATIONS (Multi-Phenomenon)

### Tile / Imagery Services

| Service | URL | Protocol | Refresh | Coverage |
|---|---|---|---|---|
| **NWS Surface Obs** | `mapservices.weather.noaa.gov/vector/rest/services/obs/surface_obs/MapServer` | ArcGIS REST | 5 min | US |
| **NWS Local Storm Reports** | `mapservices.weather.noaa.gov/vector/rest/services/obs/nws_local_storm_reports/MapServer` | ArcGIS REST | As reported | US |

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **METARs** | `aviationweather.gov/api/data/metar?format=geojson` | All surface wx: temp, dewpoint, wind, vis, ceiling, altimeter, wx phenomena, flight cat | ✅ | 5 min |
| **PIREPs** | `aviationweather.gov/api/data/pirep?format=geojson` | All-phenomenon pilot reports at altitude | ✅ | 2 min |
| **Station Info** | `aviationweather.gov/api/data/stationinfo?format=geojson` | Reporting station metadata (coords, elevation, network) | ✅ | Static |
| **Airport Info** | `aviationweather.gov/api/data/airport?format=geojson` | Airport reference data | ✅ | Static |
| **NAVAID Info** | `aviationweather.gov/api/data/navaid?format=geojson` | Navigation aid reference data | ✅ | Static |

---

## 13. MIS (Meteorological Impact Statements)

### GeoJSON / Feature Endpoints (AWC)

| Endpoint | URL | Data | GeoJSON? | Refresh |
|---|---|---|---|---|
| **MIS** | `aviationweather.gov/api/data/mis?format=raw` | Free-form text bulletins from CWSU forecasters | ❌ (raw text only) | Hourly |

---

## Complete AWC GeoJSON Endpoint Summary

All endpoints at `https://aviationweather.gov/api/data/`:

| Endpoint | GeoJSON? | What it carries | Status in our app |
|---|---|---|---|
| `/metar` | ✅ | Surface observations | ✅ Ingested + rendered |
| `/taf` | ✅ | Terminal forecasts (time-blocked) | ✅ Ingested + airport panel |
| `/pirep` | ✅ | Pilot reports (3D points) | ✅ Ingested + 3D rendered |
| `/airsigmet` | ✅ | SIGMETs + AIRMETs (polygons) | ✅ Ingested + rendered |
| `/gairmet` | ✅ | Graphical AIRMETs (polygons) | ✅ Ingested + rendered |
| `/isigmet` | ✅ | International SIGMETs (polygons) | ✅ Ingested + rendered |
| `/cwa` | ✅ | Center Weather Advisories (polygons) | ✅ Ingested + rendered |
| `/tcf` | ✅ | TFM Convective Forecast | 🔲 Not yet ingested |
| `/mis` | ❌ | Meteorological Impact Statements | ✅ Ingested (raw text) |
| `/stationinfo` | ✅ | Observation station metadata | ✅ Ingested + green badges |
| `/airport` | ✅ | Airport reference data | 🔲 Not yet ingested (using CIFP) |
| `/navaid` | ✅ | NAVAID reference data | 🔲 Not yet ingested (using CIFP) |

---

## Integration Notes

### A. Tile / Imagery Services → Cesium JS

Three provider classes handle every source type.

**ArcGIS MapServer** (NWS, nowCOAST, FAA charts):

```javascript
// Cesium JS docs: https://cesium.com/learn/cesiumjs/ref-doc/ArcGisMapServerImageryProvider.html
const provider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
    'https://mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity/MapServer'
);
const layer = viewer.imageryLayers.addImageryProvider(provider);
layer.alpha = 0.7;  // semi-transparent overlay
```

Cesium auto-reads the service metadata (`?f=json`), discovers the tile scheme,
extent, zoom levels, and attribution.  No GetCapabilities parsing needed.

**WMS** (IEM NEXRAD, IEM GOES):

```javascript
// Cesium JS docs: https://cesium.com/learn/cesiumjs/ref-doc/WebMapServiceImageryProvider.html
const provider = new Cesium.WebMapServiceImageryProvider({
    url: 'https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q.cgi',
    layers: 'nexrad-n0q-900913',  // from GetCapabilities <Layer><Name>
    parameters: {
        transparent: true,
        format: 'image/png',
    },
});
viewer.imageryLayers.addImageryProvider(provider);
```

Discover available layer names from the GetCapabilities XML:
`…/n0q.cgi?service=WMS&version=1.1.1&request=GetCapabilities`

For **WMS-T** (time-enabled; e.g., `n0q-t.cgi`), pass the `TIME` parameter:

```javascript
parameters: { transparent: true, format: 'image/png', TIME: '2026-04-15T18:00:00Z' }
```

**XYZ Tiles** (IEM cached tiles, OpenWeatherMap):

```javascript
// Cesium JS docs: https://cesium.com/learn/cesiumjs/ref-doc/UrlTemplateImageryProvider.html
const provider = new Cesium.UrlTemplateImageryProvider({
    url: 'https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png',
});
viewer.imageryLayers.addImageryProvider(provider);
```

### B. Tile / Imagery Services → Cesium for Unity

Cesium for Unity provides raster overlay components that attach to a
`Cesium3DTileset` (typically the globe terrain tileset).

**ArcGIS MapServer:**

```csharp
// Cesium for Unity docs:
// https://cesium.com/learn/cesium-unity/ref-doc/class_cesium_for_unity_1_1_cesium_ion_raster_overlay.html
// (Use CesiumWebMapTileServiceRasterOverlay for generic tile services)
// For ArcGIS specifically: fetch tile URL pattern from the REST metadata
// and use CesiumUrlTemplateRasterOverlay with the /tile/{z}/{y}/{x} pattern.
var overlay = gameObject.AddComponent<CesiumUrlTemplateRasterOverlay>();
overlay.templateUrl = "https://mapservices.weather.noaa.gov/eventdriven/rest/services/"
    + "radar/radar_base_reflectivity/MapServer/tile/{z}/{y}/{x}";
overlay.maximumLevel = 10;
```

**WMS:**

```csharp
// Cesium for Unity docs:
// https://cesium.com/learn/cesium-unity/ref-doc/class_cesium_for_unity_1_1_cesium_web_map_service_raster_overlay.html
var overlay = gameObject.AddComponent<CesiumWebMapServiceRasterOverlay>();
overlay.baseUrl = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q.cgi";
overlay.layers = "nexrad-n0q-900913";
overlay.tileWidth = 256;
overlay.tileHeight = 256;
```

**XYZ Tiles:**

```csharp
var overlay = gameObject.AddComponent<CesiumUrlTemplateRasterOverlay>();
overlay.templateUrl = "https://mesonet.agron.iastate.edu/cache/tile.py/"
    + "1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png";
```

### C. GeoJSON Features → Cesium JS

Our existing pattern: fetch from AWC, normalize to flat dicts, render as
Cesium `Entity` objects via entity-manager classes.

```javascript
// Fetch + render SIGMETs as 3D-extruded polygons
const res = await fetch('/api/weather/airsigmets');
const data = await res.json();
for (const item of data.items) {
    const positions = item.coords.map(([lat, lon]) =>
        Cesium.Cartesian3.fromDegrees(lon, lat, 0));
    viewer.entities.add({
        polygon: {
            hierarchy: new Cesium.PolygonHierarchy(positions),
            material: Cesium.Color.RED.withAlpha(0.25),
            height: item.bottom_ft * 0.3048 * altScale,
            extrudedHeight: item.top_ft * 0.3048 * altScale,
        },
    });
}

// Fetch + render PIREPs as 3D-positioned points
const pirepRes = await fetch('/api/weather/pireps?bounds=30,-105,38,-90');
const pireps = await pirepRes.json();
for (const p of pireps.items) {
    viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.alt_ft * 0.3048),
        point: { pixelSize: 8, color: Cesium.Color.ORANGE },
        label: { text: `${p.ac_type} FL${p.fl_100ft}`, font: '10px monospace' },
    });
}
```

### D. GeoJSON Features → Cesium for Unity

**Option 1 — Via Cesium for Unity's `CesiumGeoJsonComponent`** (if available
in your version; check release notes):

```csharp
// Load GeoJSON from a URL or string, Cesium handles positioning
var geoJson = gameObject.AddComponent<CesiumGeoJsonComponent>();
geoJson.url = "https://your-server/api/weather/airsigmets?format=geojson_native";
```

**Option 2 — Manual: parse GeoJSON in C# and position GameObjects
on the Cesium globe** (works with any Cesium for Unity version):

```csharp
using CesiumForUnity;
using Unity.Mathematics;

// 1. Fetch GeoJSON from your backend
string json = await httpClient.GetStringAsync(
    "https://your-server/api/weather/pireps?bounds=30,-105,38,-90");
var pireps = JsonConvert.DeserializeObject<PirepResponse>(json);

// 2. Get the CesiumGeoreference on your globe
var geoRef = FindObjectOfType<CesiumGeoreference>();

// 3. For each feature, create a positioned GameObject
foreach (var p in pireps.items) {
    var go = Instantiate(pirepPrefab);  // your marker prefab
    // Convert WGS84 (lon, lat, alt) → Unity world position
    double3 ecef = CesiumWgs84Ellipsoid.LongitudeLatitudeHeightToEarthCenteredEarthFixed(
        new double3(p.lon, p.lat, p.alt_ft * 0.3048));
    double3 unity = geoRef.TransformEarthCenteredEarthFixedPositionToUnity(ecef);
    go.transform.position = new Vector3((float)unity.x, (float)unity.y, (float)unity.z);
}
```

**For polygon features** (SIGMETs, CWAs, airspace):

```csharp
// Build a mesh from the polygon ring coordinates
var ring = sigmet.coords;  // List<double[]> of [lat, lon]
var vertices = new List<Vector3>();
foreach (var pt in ring) {
    double3 ecef = CesiumWgs84Ellipsoid.LongitudeLatitudeHeightToEarthCenteredEarthFixed(
        new double3(pt[1], pt[0], bottomFt * 0.3048));
    double3 unity = geoRef.TransformEarthCenteredEarthFixedPositionToUnity(ecef);
    vertices.Add(new Vector3((float)unity.x, (float)unity.y, (float)unity.z));
}
// Triangulate + assign to a MeshFilter/MeshRenderer with a
// semi-transparent material.  For extruded 3D volumes, duplicate
// the ring at topFt and connect the two rings with quads.
```

**Option 3 — Skip Cesium entirely for GeoJSON overlay** (pure Unity):

If your GeoJSON features are small (< 500 km extent), you can render
them in Unity's local coordinate space and rely on
`CesiumGeoreference` only for the anchor point:

```csharp
// Anchor the feature's centroid on the globe
var centroid = ComputeCentroid(ring);
var anchorGo = new GameObject("SIGMET_anchor");
var anchor = anchorGo.AddComponent<CesiumGlobeAnchor>();
anchor.longitudeLatitudeHeight = new double3(centroid.lon, centroid.lat, 0);
// Child mesh is positioned relative to the anchor in Unity's local space
var meshGo = Instantiate(polygonPrefab, anchorGo.transform);
// Build mesh vertices as offsets from the centroid (meters)
```

This avoids double-precision issues for features near the camera
and is simpler than computing ECEF for every vertex.

### Credentials

| Source | Auth required? | Notes |
|---|---|---|
| NWS / NOAA (all mapservices + nowCOAST) | No | Public, no key |
| AWC (aviationweather.gov) | No | Public, no key; rate-limit politely |
| IEM (Iowa State Mesonet) | No | Public, no key |
| OpenWeatherMap | 🔑 Free API key | 1M requests/month free tier |
| NOAA WIFS (gridded turb/ice/CB) | 🔑 Registration | WIFS API access |

### Reference Documentation

- **Cesium JS Imagery Providers**: https://cesium.com/learn/cesiumjs/ref-doc/ImageryProvider.html
- **Cesium JS ArcGIS Provider**: https://cesium.com/learn/cesiumjs/ref-doc/ArcGisMapServerImageryProvider.html
- **Cesium JS WMS Provider**: https://cesium.com/learn/cesiumjs/ref-doc/WebMapServiceImageryProvider.html
- **Cesium JS URL Template Provider**: https://cesium.com/learn/cesiumjs/ref-doc/UrlTemplateImageryProvider.html
- **Cesium for Unity Raster Overlays**: https://cesium.com/learn/cesium-unity/ref-doc/class_cesium_for_unity_1_1_cesium_raster_overlay.html
- **Cesium for Unity WMS Overlay**: https://cesium.com/learn/cesium-unity/ref-doc/class_cesium_for_unity_1_1_cesium_web_map_service_raster_overlay.html
- **Cesium for Unity Globe Anchor**: https://cesium.com/learn/cesium-unity/ref-doc/class_cesium_for_unity_1_1_cesium_globe_anchor.html
- **Cesium for Unity Georeference**: https://cesium.com/learn/cesium-unity/ref-doc/class_cesium_for_unity_1_1_cesium_georeference.html

---

## Sources

- [NWS GIS Web Services](https://www.weather.gov/gis/WebServices)
- [NWS mapservices.weather.noaa.gov](https://mapservices.weather.noaa.gov/)
- [NOAA nowCOAST](https://nowcoast.noaa.gov/)
- [Iowa Environmental Mesonet OGC Services](https://mesonet.agron.iastate.edu/ogc/)
- [IEM NEXRAD Mosaics](https://mesonet.agron.iastate.edu/docs/nexrad_mosaic/)
- [AWC Data API](https://aviationweather.gov/data/api/)
- [AWC GFA Help](https://aviationweather.gov/gfa/help/)
- [NOAA WIFS API](https://aviationweather.gov/wifs/api.html)
- [OpenWeatherMap Tile Layers](https://openweathermap.org/api/weathermaps)
