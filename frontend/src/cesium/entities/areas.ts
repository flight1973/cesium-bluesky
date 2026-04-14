/**
 * Area entity manager — syncs area boundaries from the
 * backend and renders them as 3D extruded volumes.
 *
 * Full vertical columns (no top/bottom set on the sim
 * side) extend from the surface up to the Kármán line
 * (100 km = internationally recognized edge of space).
 * Areas with altitude constraints are extruded between
 * their specified top and bottom.
 *
 * Altitude exaggeration is applied so volumes line up
 * with the visible aircraft altitude scale.
 */
import {
  Viewer,
  Cartesian3,
  Color,
  CustomDataSource,
  PolygonHierarchy,
} from 'cesium';

const COLOR_ACTIVE_FILL = new Color(0, 1, 0, 0.06);
const COLOR_ACTIVE_OUTLINE = new Color(0, 1, 0, 0.6);

// Kármán line — edge of space (100 km).
const KARMAN_LINE_M = 100_000;

// BlueSky uses 1e9 as "effective infinity" for top/bottom.
const INFINITY_THRESHOLD = 1e8;

interface ShapeInfo {
  name: string;
  type: string;
  coordinates: number[];
  top: number;
  bottom: number;
}

interface AreasResponse {
  shapes: Record<string, ShapeInfo>;
  active_area: string | null;
}

export class AreaManager {
  private source: CustomDataSource;
  private pollTimer: number | null = null;
  private lastJson = '';
  private _altScale = 1.0;

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('areas');
    viewer.dataSources.add(this.source);
  }

  /** Match aircraft altitude exaggeration. */
  setAltScale(scale: number): void {
    this._altScale = scale;
    // Force redraw so volumes update.
    this.lastJson = '';
    this._fetch();
  }

  /** Start polling the backend for areas. */
  startPolling(intervalMs = 2000): void {
    this.stopPolling();
    this._fetch();
    this.pollTimer = window.setInterval(
      () => this._fetch(), intervalMs,
    );
  }

  stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  refresh(): void {
    this.lastJson = '';
    this._fetch();
  }

  clear(): void {
    this.source.entities.removeAll();
    this.lastJson = '';
  }

  private async _fetch(): Promise<void> {
    try {
      const res = await fetch('/api/areas');
      if (!res.ok) return;
      const text = await res.text();
      if (text === this.lastJson) return;
      this.lastJson = text;
      const data: AreasResponse = JSON.parse(text);
      this._render(data);
    } catch {
      // Network error — skip.
    }
  }

  private _render(data: AreasResponse): void {
    this.source.entities.removeAll();

    if (!data.active_area) return;
    const shape = data.shapes?.[data.active_area];
    if (!shape) return;

    const coords = this._toDegreesArray(
      shape.type, shape.coordinates,
    );
    if (!coords || coords.length < 6) return;

    // Resolve top/bottom, defaulting to surface/Kármán.
    const { top, bottom } = this._resolveAltitudes(
      shape.top, shape.bottom,
    );

    const positions =
      Cartesian3.fromDegreesArray(coords);

    this.source.entities.add({
      polygon: {
        hierarchy: new PolygonHierarchy(positions),
        material: COLOR_ACTIVE_FILL,
        outline: true,
        outlineColor: COLOR_ACTIVE_OUTLINE,
        outlineWidth: 2,
        // Extrude into a 3D volume.
        height: bottom * this._altScale,
        extrudedHeight: top * this._altScale,
      },
    });
  }

  /**
   * Resolve sim-side top/bottom to display altitudes.
   *
   * BlueSky defaults to ±1e9 m for "no limit". We replace
   * those with surface (0) and Kármán line (100 km).
   */
  private _resolveAltitudes(
    top: number,
    bottom: number,
  ): { top: number; bottom: number } {
    const resolvedTop =
      top > INFINITY_THRESHOLD ? KARMAN_LINE_M : top;
    const resolvedBottom =
      bottom < -INFINITY_THRESHOLD || bottom < 0
        ? 0 : bottom;
    return {
      top: resolvedTop,
      bottom: resolvedBottom,
    };
  }

  /**
   * Convert BlueSky coords [lat,lon,...] to Cesium
   * [lon,lat,...] array.  For Box shapes, expands
   * two corners into four vertices.
   */
  private _toDegreesArray(
    shapeType: string,
    coordinates: number[],
  ): number[] | null {
    if (coordinates.length < 4) return null;

    if (shapeType === 'Box') {
      const lat1 = coordinates[0];
      const lon1 = coordinates[1];
      const lat2 = coordinates[2];
      const lon2 = coordinates[3];
      return [
        lon1, lat1,
        lon2, lat1,
        lon2, lat2,
        lon1, lat2,
      ];
    }

    // Poly — [lat,lon,lat,lon,...] → [lon,lat,...]
    const result: number[] = [];
    for (let i = 0; i < coordinates.length - 1; i += 2) {
      result.push(
        coordinates[i + 1], coordinates[i],
      );
    }
    return result;
  }
}
