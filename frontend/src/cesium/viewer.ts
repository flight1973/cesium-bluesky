/**
 * CesiumJS viewer initialization and layer management.
 *
 * Provides a set of selectable imagery providers and terrain
 * options. Without a Cesium Ion token only open basemaps are
 * shown; with a token, Ion imagery (Bing Aerial, Sentinel-2)
 * and Ion World Terrain become available.
 */
import {
  Viewer,
  Ion,
  Cartesian3,
  Color,
  UrlTemplateImageryProvider,
  IonImageryProvider,
  ImageryLayer,
  CesiumTerrainProvider,
  EllipsoidTerrainProvider,
  Math as CesiumMath,
  ImageryProvider,
  TerrainProvider,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

export interface ImageryOption {
  id: string;
  label: string;
  needsIon: boolean;
  create(): Promise<ImageryProvider>;
}

export interface TerrainOption {
  id: string;
  label: string;
  needsIon: boolean;
  create(): Promise<TerrainProvider>;
}

/** Free imagery providers — always available. */
const FREE_IMAGERY: ImageryOption[] = [
  {
    id: 'cartodb-dark',
    label: 'CartoDB Dark (radar-style)',
    needsIon: false,
    async create() {
      return new UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/'
          + 'dark_all/{z}/{x}/{y}.png',
        subdomains: ['a', 'b', 'c', 'd'],
        credit: 'CartoDB',
      });
    },
  },
  {
    id: 'cartodb-light',
    label: 'CartoDB Light',
    needsIon: false,
    async create() {
      return new UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/'
          + 'light_all/{z}/{x}/{y}.png',
        subdomains: ['a', 'b', 'c', 'd'],
        credit: 'CartoDB',
      });
    },
  },
  {
    id: 'osm',
    label: 'OpenStreetMap',
    needsIon: false,
    async create() {
      return new UrlTemplateImageryProvider({
        url: 'https://tile.openstreetmap.org/'
          + '{z}/{x}/{y}.png',
        credit: 'OpenStreetMap',
      });
    },
  },
  {
    id: 'opentopo',
    label: 'OpenTopoMap',
    needsIon: false,
    async create() {
      return new UrlTemplateImageryProvider({
        url: 'https://{s}.tile.opentopomap.org/'
          + '{z}/{x}/{y}.png',
        subdomains: ['a', 'b', 'c'],
        credit: 'OpenTopoMap',
      });
    },
  },
];

/** Ion-based imagery (requires token). */
const ION_IMAGERY: ImageryOption[] = [
  {
    id: 'bing-aerial',
    label: 'Bing Maps Aerial',
    needsIon: true,
    async create() {
      return IonImageryProvider.fromAssetId(2);
    },
  },
  {
    id: 'bing-aerial-labels',
    label: 'Bing Aerial with Labels',
    needsIon: true,
    async create() {
      return IonImageryProvider.fromAssetId(3);
    },
  },
  {
    id: 'bing-road',
    label: 'Bing Maps Road',
    needsIon: true,
    async create() {
      return IonImageryProvider.fromAssetId(4);
    },
  },
  {
    id: 'sentinel2',
    label: 'Sentinel-2',
    needsIon: true,
    async create() {
      return IonImageryProvider.fromAssetId(3954);
    },
  },
];

/** Terrain options. */
const TERRAIN_OPTIONS: TerrainOption[] = [
  {
    id: 'flat',
    label: 'Flat (no terrain)',
    needsIon: false,
    async create() {
      return new EllipsoidTerrainProvider();
    },
  },
  {
    id: 'world-terrain',
    label: 'Cesium World Terrain',
    needsIon: true,
    async create() {
      return CesiumTerrainProvider.fromIonAssetId(1);
    },
  },
];

/** All imagery options (free + Ion). */
export const ALL_IMAGERY: ImageryOption[] = [
  ...FREE_IMAGERY,
  ...ION_IMAGERY,
];
export const ALL_TERRAIN = TERRAIN_OPTIONS;

/** Current Ion token availability. */
let _ionTokenSet = false;

export function isIonEnabled(): boolean {
  return _ionTokenSet;
}

export function createViewer(
  container: string | HTMLElement,
): Viewer {
  const viewer = new Viewer(container, {
    animation: false,
    timeline: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    selectionIndicator: true,
    infoBox: false,
    baseLayerPicker: false,
    terrain: undefined,
  });

  // Start with CartoDB dark.
  viewer.imageryLayers.removeAll();
  FREE_IMAGERY[0].create().then((p) => {
    viewer.imageryLayers.addImageryProvider(p);
  });

  // Default camera over KDFW (Dallas/Fort Worth).
  viewer.camera.setView({
    destination: Cartesian3.fromDegrees(
      -97.0403, 32.8998, 500000,
    ),
    orientation: {
      heading: CesiumMath.toRadians(0),
      pitch: CesiumMath.toRadians(-90),
      roll: 0,
    },
  });

  viewer.scene.globe.depthTestAgainstTerrain = false;
  return viewer;
}

/**
 * Swap the current imagery layer.  Keeps a single base
 * layer (removes existing before adding the new one).
 */
export async function setImagery(
  viewer: Viewer,
  option: ImageryOption,
): Promise<void> {
  if (option.needsIon && !_ionTokenSet) {
    throw new Error(
      `${option.label} requires a Cesium Ion token`,
    );
  }
  const provider = await option.create();
  viewer.imageryLayers.removeAll();
  viewer.imageryLayers.addImageryProvider(provider);
}

/** Apply a terrain provider to the viewer. */
export async function setTerrain(
  viewer: Viewer,
  option: TerrainOption,
): Promise<void> {
  if (option.needsIon && !_ionTokenSet) {
    throw new Error(
      `${option.label} requires a Cesium Ion token`,
    );
  }
  const provider = await option.create();
  viewer.terrainProvider = provider;
  viewer.scene.globe.depthTestAgainstTerrain =
    option.id !== 'flat';
}

/**
 * Apply a Cesium Ion token.  Can be called any time —
 * from backend config on startup or from the UI later.
 */
export function setIonToken(token: string): void {
  if (!token) {
    _ionTokenSet = false;
    Ion.defaultAccessToken = '';
    return;
  }
  Ion.defaultAccessToken = token;
  _ionTokenSet = true;
  try {
    window.localStorage.setItem(
      'cesium_ion_token', token,
    );
  } catch {
    // Non-fatal (private mode / disabled).
  }
}

/**
 * Check backend for a token and apply it if present.
 * Falls back to localStorage if backend has none.
 */
export async function applyIonConfig(
  viewer: Viewer,
): Promise<void> {
  let token = '';
  try {
    const res = await fetch('/api/config/cesium');
    if (res.ok) {
      const cfg = await res.json();
      token = cfg.ion_token || '';
    }
  } catch {
    // Backend unreachable.
  }

  if (!token) {
    try {
      token =
        window.localStorage.getItem(
          'cesium_ion_token',
        ) || '';
    } catch {
      // Ignore.
    }
  }

  if (!token) {
    console.log(
      '[Cesium] No Ion token — using open basemaps',
    );
    return;
  }

  setIonToken(token);
  console.log('[Cesium] Ion token set — Ion enabled');
}
