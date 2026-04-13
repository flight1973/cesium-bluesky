/**
 * Initialize the CesiumJS viewer for ATM simulation.
 *
 * If a Cesium Ion token is available (via /api/config/cesium),
 * enables Ion imagery, terrain, and the base layer picker so
 * users can choose from Bing, Sentinel-2, OSM, etc.
 *
 * Without a token, falls back to free open basemaps (CartoDB
 * dark, OpenStreetMap) with no terrain — works for everyone.
 */
import {
  Viewer,
  Ion,
  Cartesian3,
  UrlTemplateImageryProvider,
  Math as CesiumMath,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

/**
 * Create the viewer.  Call this once on startup.
 *
 * The returned viewer starts with open basemaps.
 * Call ``applyIonConfig(viewer)`` afterward to upgrade
 * to Ion if a token is available.
 */
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
    terrain: undefined,

    // Start without Ion — base layer picker off.
    // applyIonConfig will re-enable it if a token exists.
    baseLayerPicker: false,
  });

  // Default: CartoDB dark basemap (free, no key).
  viewer.imageryLayers.removeAll();
  viewer.imageryLayers.addImageryProvider(
    new UrlTemplateImageryProvider({
      url: 'https://{s}.basemaps.cartocdn.com/'
        + 'dark_all/{z}/{x}/{y}.png',
      subdomains: ['a', 'b', 'c', 'd'],
      credit: 'CartoDB',
    }),
  );

  // Default camera: tilted 3D over Schiphol.
  viewer.camera.setView({
    destination: Cartesian3.fromDegrees(
      4.76, 50.5, 400000,
    ),
    orientation: {
      heading: CesiumMath.toRadians(0),
      pitch: CesiumMath.toRadians(-45),
      roll: 0,
    },
  });

  viewer.scene.globe.depthTestAgainstTerrain = false;
  return viewer;
}

/**
 * Check the backend for a Cesium Ion token and, if
 * present, upgrade the viewer with Ion imagery, terrain,
 * and the base layer picker.
 */
export async function applyIonConfig(
  viewer: Viewer,
): Promise<void> {
  try {
    const res = await fetch('/api/config/cesium');
    if (!res.ok) return;
    const cfg = await res.json();

    if (!cfg.ion_token) {
      console.log(
        '[Cesium] No Ion token — using open basemaps',
      );
      return;
    }

    // Set the Ion token globally.
    Ion.defaultAccessToken = cfg.ion_token;
    console.log('[Cesium] Ion token set — enabling Ion');

    // Re-create the viewer's base layer picker now
    // that Ion is available.  The simplest way is to
    // replace imagery with the Ion default (Bing).
    viewer.imageryLayers.removeAll();

    // Ion asset 2 = Bing Maps Aerial.
    const { IonImageryProvider } = await import('cesium');
    const bingProvider =
      await IonImageryProvider.fromAssetId(2);
    viewer.imageryLayers.addImageryProvider(bingProvider);

    // Enable Ion world terrain.
    try {
      const { Terrain } = await import('cesium');
      viewer.scene.setTerrain(
        Terrain.fromWorldTerrain(),
      );
      viewer.scene.globe.depthTestAgainstTerrain = true;
    } catch {
      // Terrain load failure is non-fatal.
      console.warn('[Cesium] Could not load Ion terrain');
    }

  } catch {
    // Backend unreachable — keep open basemaps.
    console.log(
      '[Cesium] Config fetch failed — using open basemaps',
    );
  }
}
