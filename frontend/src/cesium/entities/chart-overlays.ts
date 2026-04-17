/**
 * FAA aeronautical chart overlay manager.
 *
 * Tiles served from FAA's own ArcGIS MapServer at
 * ``tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ`` —
 * the same host we already use for Class Airspace
 * polygons.  Uses ``ArcGisMapServerImageryProvider``
 * so Cesium handles the tile numbering, extent, and
 * zoom-level bounds automatically.
 *
 * Available layers (FAA publishes only these 4 as
 * tiled map services):
 *   VFR_Sectional  — readable at z≥8
 *   VFR_Terminal   — readable at z≥10
 *   IFR_AreaLow    — readable at z≥5
 *   IFR_High       — readable at z≥5 (caps ~z10)
 *
 * Helicopter Route Charts are NOT published as
 * tiles by the FAA; skipped until a reliable
 * alternative tile source is found.
 */
import {
  Viewer,
  ImageryLayer,
  ArcGisMapServerImageryProvider,
} from 'cesium';

export type ChartId =
  | 'sectional'
  | 'tac'
  | 'ifr-low'
  | 'ifr-high';

interface ChartSpec {
  id: ChartId;
  label: string;
  mapServerUrl: string;
}

const _BASE = 'https://tiles.arcgis.com/tiles/'
  + 'ssFJjBXIUyZDrSYZ/arcgis/rest/services';

const CHART_SPECS: Record<ChartId, ChartSpec> = {
  sectional: {
    id: 'sectional',
    label: 'VFR Sectional',
    mapServerUrl: `${_BASE}/VFR_Sectional/MapServer`,
  },
  tac: {
    id: 'tac',
    label: 'Terminal Area Chart',
    mapServerUrl: `${_BASE}/VFR_Terminal/MapServer`,
  },
  'ifr-low': {
    id: 'ifr-low',
    label: 'IFR Low Enroute',
    mapServerUrl: `${_BASE}/IFR_AreaLow/MapServer`,
  },
  'ifr-high': {
    id: 'ifr-high',
    label: 'IFR High Enroute',
    mapServerUrl: `${_BASE}/IFR_High/MapServer`,
  },
};


export class ChartOverlayManager {
  private layers: Map<ChartId, ImageryLayer> = new Map();
  private opacities: Map<ChartId, number> = new Map();

  constructor(private viewer: Viewer) {}

  static specs(): ChartSpec[] {
    return Object.values(CHART_SPECS);
  }

  isOn(id: ChartId): boolean {
    return this.layers.has(id);
  }

  async setVisible(id: ChartId, on: boolean): Promise<void> {
    if (on && !this.layers.has(id)) {
      await this._add(id);
    } else if (!on && this.layers.has(id)) {
      this._remove(id);
    }
  }

  setOpacity(id: ChartId, alpha: number): void {
    const a = Math.max(0, Math.min(1, alpha));
    this.opacities.set(id, a);
    const layer = this.layers.get(id);
    if (layer) layer.alpha = a;
  }

  removeAll(): void {
    for (const id of [...this.layers.keys()]) {
      this._remove(id);
    }
  }

  private async _add(id: ChartId): Promise<void> {
    const spec = CHART_SPECS[id];
    try {
      const provider =
        await ArcGisMapServerImageryProvider.fromUrl(
          spec.mapServerUrl,
        );
      const layer =
        this.viewer.imageryLayers.addImageryProvider(
          provider,
        );
      layer.alpha = this.opacities.get(id) ?? 0.7;
      this.layers.set(id, layer);
    } catch (err) {
      console.warn(
        `Chart overlay ${id} failed to load:`, err,
      );
    }
  }

  private _remove(id: ChartId): void {
    const layer = this.layers.get(id);
    if (!layer) return;
    this.viewer.imageryLayers.remove(layer, true);
    this.layers.delete(id);
  }
}
