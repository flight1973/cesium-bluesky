/**
 * Public-source radar and satellite imagery overlays.
 *
 * - **Radar**: Iowa State University IEM NEXRAD mosaic
 *   (WSR-88D base reflectivity at surface).
 * - **Satellite**: NASA GIBS GOES-East ABI Band 13
 *   (clean infrared window at ~10.3 µm).
 *
 * Both are served as XYZ tile pyramids in Web
 * Mercator.  We add them as Cesium ``ImageryLayer``s
 * on top of the basemap with partial opacity, so the
 * user can still see airports / airspace / aircraft
 * through the weather.
 *
 * Basemap switches in ``viewer.ts`` call
 * ``imageryLayers.removeAll()`` which would wipe
 * these overlays too, so the manager exposes
 * ``reapply()`` to re-attach whatever the user had
 * enabled.  ``main.ts`` invokes this on
 * ``imagery-change``.
 */
import {
  ArcGisMapServerImageryProvider,
  ImageryLayer,
  UrlTemplateImageryProvider,
  Viewer,
  WebMapServiceImageryProvider,
  WebMercatorTilingScheme,
} from 'cesium';

/** Named tile overlays beyond the base radar + sat. */
export type WxTileId =
  | 'mrms'         // NWS MRMS high-res radar (ArcGIS)
  | 'goes-vis'     // IEM GOES visible (WMS)
  | 'spc-outlook'  // NWS SPC convective outlook (ArcGIS)
  | 'wwa'          // NWS Watches/Warnings/Advisories (ArcGIS)
  | 'ndfd-temp'    // NWS NDFD temperature (ArcGIS)
  | 'snow'         // NWS Snow Analysis (ArcGIS)
  | 'smoke';       // NWS Surface Smoke (ArcGIS)

const _NWS = 'https://mapservices.weather.noaa.gov';

const WX_TILE_SPECS: Record<WxTileId, {
  label: string;
  url: string;
  type: 'arcgis' | 'wms' | 'xyz';
  wmsLayer?: string;
  alpha: number;
}> = {
  mrms: {
    label: 'NWS MRMS Radar',
    url: `${_NWS}/eventdriven/rest/services/radar/radar_base_reflectivity/MapServer`,
    type: 'arcgis',
    alpha: 0.65,
  },
  'goes-vis': {
    label: 'GOES Visible',
    url: 'https://mesonet.agron.iastate.edu/cgi-bin/wms/goes/conus_vis.cgi',
    type: 'wms',
    wmsLayer: 'goes_conus_vis',
    alpha: 0.55,
  },
  'spc-outlook': {
    label: 'SPC Storm Outlook',
    url: `${_NWS}/vector/rest/services/outlooks/SPC_wx_outlks/MapServer`,
    type: 'arcgis',
    alpha: 0.6,
  },
  wwa: {
    label: 'Watches / Warnings',
    url: `${_NWS}/eventdriven/rest/services/WWA/watch_warn_adv/MapServer`,
    type: 'arcgis',
    alpha: 0.5,
  },
  'ndfd-temp': {
    label: 'Temperature Forecast',
    url: `${_NWS}/raster/rest/services/NDFD/NDFD_temp/MapServer`,
    type: 'arcgis',
    alpha: 0.45,
  },
  snow: {
    label: 'Snow Analysis',
    url: `${_NWS}/raster/rest/services/snow/NOHRSC_Snow_Analysis/MapServer`,
    type: 'arcgis',
    alpha: 0.5,
  },
  smoke: {
    label: 'Surface Smoke',
    url: `${_NWS}/raster/rest/services/air_quality/ndgd_smoke_sfc_1hr_avg_time/ImageServer`,
    type: 'arcgis',
    alpha: 0.5,
  },
};


export class WeatherImageryManager {
  private radarLayer: ImageryLayer | null = null;
  private satLayer: ImageryLayer | null = null;
  private radarWanted = false;
  private satWanted = false;
  /** Selected timestamp (ISO UTC) or null for latest. */
  private currentTime: string | null = null;
  /** Named tile overlay layers. */
  private _wxLayers = new Map<WxTileId, ImageryLayer>();
  private _wxWanted = new Set<WxTileId>();

  constructor(private viewer: Viewer) {}

  radarVisible(): boolean { return this.radarWanted; }
  satelliteVisible(): boolean { return this.satWanted; }

  /** Available named tile overlay specs for the UI. */
  static tileSpecs(): Array<{ id: WxTileId; label: string }> {
    return (Object.entries(WX_TILE_SPECS) as
      [WxTileId, typeof WX_TILE_SPECS[WxTileId]][]).map(
      ([id, s]) => ({ id, label: s.label }),
    );
  }

  /** Toggle a named tile overlay on/off. */
  async setTileVisible(id: WxTileId, on: boolean): Promise<void> {
    if (on) {
      this._wxWanted.add(id);
      if (!this._wxLayers.has(id)) {
        await this._addTile(id);
      }
    } else {
      this._wxWanted.delete(id);
      const layer = this._wxLayers.get(id);
      if (layer) {
        this.viewer.imageryLayers.remove(layer);
        this._wxLayers.delete(id);
      }
    }
  }

  isTileVisible(id: WxTileId): boolean {
    return this._wxWanted.has(id);
  }

  setTileOpacity(id: WxTileId, alpha: number): void {
    const layer = this._wxLayers.get(id);
    if (layer) layer.alpha = Math.max(0, Math.min(1, alpha));
  }

  setRadarVisible(on: boolean): void {
    this.radarWanted = on;
    if (on && !this.radarLayer) {
      this.radarLayer = this._addRadar();
    } else if (!on && this.radarLayer) {
      this.viewer.imageryLayers.remove(this.radarLayer);
      this.radarLayer = null;
    }
  }

  setSatelliteVisible(on: boolean): void {
    this.satWanted = on;
    if (on && !this.satLayer) {
      this.satLayer = this._addSatellite();
    } else if (!on && this.satLayer) {
      this.viewer.imageryLayers.remove(this.satLayer);
      this.satLayer = null;
    }
  }

  /** Re-attach layers the user still wants after a
   *  basemap change (which calls removeAll on the
   *  imagery collection). */
  reapply(): void {
    this.radarLayer = null;
    this.satLayer = null;
    this._wxLayers.clear();
    if (this.radarWanted) {
      this.radarLayer = this._addRadar();
    }
    if (this.satWanted) {
      this.satLayer = this._addSatellite();
    }
    for (const id of this._wxWanted) {
      void this._addTile(id);
    }
  }

  /** Overlap-swap delay in ms.  Keeps the old layer
   *  visible while the new one starts fetching tiles,
   *  so the user doesn't see a flash through to the
   *  basemap during frame changes. */
  private static readonly SWAP_DELAY_MS = 400;

  /** Manually refresh the current layers — useful as
   *  a periodic "show latest data" timer.  Rebuilds
   *  providers so Cesium fetches fresh tiles. */
  refresh(): void {
    if (this.radarLayer) this._swapRadar();
    if (this.satLayer) this._swapSatellite();
  }

  /** Current selected time (ISO UTC, or null for live). */
  getTime(): string | null {
    return this.currentTime;
  }

  /** Select a historical timestamp (null = latest). */
  setTime(iso: string | null): void {
    if (iso === this.currentTime) return;
    this.currentTime = iso;
    if (this.radarLayer) this._swapRadar();
    if (this.satLayer) this._swapSatellite();
  }

  /** Add the new radar layer on top, then remove the
   *  previous after a short delay so the transition
   *  overlaps rather than flashing. */
  private _swapRadar(): void {
    const old = this.radarLayer;
    this.radarLayer = this._addRadar();
    if (old) {
      setTimeout(() => {
        this.viewer.imageryLayers.remove(old);
      }, WeatherImageryManager.SWAP_DELAY_MS);
    }
  }

  private _swapSatellite(): void {
    const old = this.satLayer;
    this.satLayer = this._addSatellite();
    if (old) {
      setTimeout(() => {
        this.viewer.imageryLayers.remove(old);
      }, WeatherImageryManager.SWAP_DELAY_MS);
    }
  }

  private _addRadar(): ImageryLayer {
    // IEM supports historical frames via the
    // ``lstr=<iso>`` query param; without it the
    // endpoint serves the latest available.
    let url = 'https://mesonet.agron.iastate.edu/cache/'
      + 'tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png';
    if (this.currentTime) {
      const enc = encodeURIComponent(this.currentTime);
      url += `?lstr=${enc}`;
    }
    const provider = new UrlTemplateImageryProvider({
      url,
      tilingScheme: new WebMercatorTilingScheme(),
      minimumLevel: 0,
      maximumLevel: 10,
      credit: '© Iowa State University / NWS NEXRAD',
    });
    const layer = this.viewer.imageryLayers
      .addImageryProvider(provider);
    layer.alpha = 0.7;
    return layer;
  }

  private _addSatellite(): ImageryLayer {
    // GIBS encodes time in the URL path.  For live
    // data use today's UTC date; for historical use
    // the user-selected timestamp's date.  GOES-East
    // Band 13 publishes ~every 10 min but the layer
    // metadata accepts the full ISO timestamp.
    const dtStr = this.currentTime
      ?? new Date().toISOString();
    const datePart = dtStr.slice(0, 10);  // YYYY-MM-DD
    const url = 'https://gibs.earthdata.nasa.gov/wmts/'
      + 'epsg3857/best/GOES-East_ABI_Band13_Clean_Infrared/'
      + `default/${datePart}/GoogleMapsCompatible_Level6/`
      + '{z}/{y}/{x}.png';
    const provider = new UrlTemplateImageryProvider({
      url,
      tilingScheme: new WebMercatorTilingScheme(),
      minimumLevel: 0,
      maximumLevel: 6,
      credit: 'NASA GIBS / NOAA GOES-East IR',
    });
    const layer = this.viewer.imageryLayers
      .addImageryProvider(provider);
    layer.alpha = 0.55;
    return layer;
  }

  /** Add a named tile overlay using the spec table. */
  private async _addTile(id: WxTileId): Promise<void> {
    const spec = WX_TILE_SPECS[id];
    if (!spec) return;
    try {
      let layer: ImageryLayer;
      switch (spec.type) {
        case 'arcgis': {
          const p = await ArcGisMapServerImageryProvider
            .fromUrl(spec.url);
          layer = this.viewer.imageryLayers
            .addImageryProvider(p);
          break;
        }
        case 'wms': {
          const p = new WebMapServiceImageryProvider({
            url: spec.url,
            layers: spec.wmsLayer || '',
            parameters: {
              transparent: true,
              format: 'image/png',
            },
          });
          layer = this.viewer.imageryLayers
            .addImageryProvider(p);
          break;
        }
        case 'xyz':
        default: {
          const p = new UrlTemplateImageryProvider({
            url: spec.url,
            tilingScheme: new WebMercatorTilingScheme(),
          });
          layer = this.viewer.imageryLayers
            .addImageryProvider(p);
          break;
        }
      }
      layer.alpha = spec.alpha;
      this._wxLayers.set(id, layer);
    } catch (err) {
      console.warn(
        `Weather tile ${id} failed:`, err,
      );
    }
  }
}
