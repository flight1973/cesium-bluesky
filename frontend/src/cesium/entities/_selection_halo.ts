/**
 * Shared selection-highlight helper for 3D airspace /
 * weather polygons.
 *
 * Draws a bright polyline along the top and bottom
 * rims of an extruded polygon, plus optional vertical
 * edges, so the selected volume is unmistakable from
 * any camera angle.
 *
 * Polygon ``outlineWidth > 1`` is ignored on most
 * WebGL implementations in Cesium, so we use a
 * separate polyline overlay (polyline width IS
 * respected in pixels).
 */
import {
  Cartesian3,
  Color,
  Entity,
  Viewer,
} from 'cesium';

/**
 * One logical "volume" to highlight:
 *   rings[i]       = ordered [lat, lon] ring (closed or not)
 *   bottomM/topM   = extrusion band in meters
 */
export interface HaloVolume {
  rings: [number, number][][];
  bottomM: number;
  topM: number;
}

const HALO_COLOR = Color.fromCssColorString('#ffffff');
const HALO_WIDTH = 4;

export class SelectionHalo {
  private entities: Entity[] = [];
  constructor(private viewer: Viewer) {}

  /** Remove any existing halo. Safe to call repeatedly. */
  clear(): void {
    for (const e of this.entities) {
      this.viewer.entities.remove(e);
    }
    this.entities = [];
  }

  /**
   * Replace the halo with one rendered around ``vol``.
   * Passing null just clears.
   */
  show(vol: HaloVolume | null): void {
    this.clear();
    if (!vol) return;
    for (const ring of vol.rings) {
      if (ring.length < 2) continue;
      // Close the ring if it isn't already.
      const closed = ring.length > 2
        && (ring[0][0] !== ring[ring.length - 1][0]
          || ring[0][1] !== ring[ring.length - 1][1])
        ? [...ring, ring[0]]
        : ring;
      this._rim(closed, vol.topM);
      this._rim(closed, vol.bottomM);
    }
  }

  private _rim(
    ring: [number, number][],
    heightM: number,
  ): void {
    const positions = ring.map(
      ([lat, lon]) =>
        Cartesian3.fromDegrees(lon, lat, heightM),
    );
    const ent = this.viewer.entities.add({
      polyline: {
        positions,
        width: HALO_WIDTH,
        material: HALO_COLOR,
        // Rim must stay visible even through the
        // polygon's own fill — disable depth test so
        // the outline doesn't get z-clipped when the
        // camera is inside or below the volume.
        depthFailMaterial: HALO_COLOR,
      },
    });
    this.entities.push(ent);
  }
}
