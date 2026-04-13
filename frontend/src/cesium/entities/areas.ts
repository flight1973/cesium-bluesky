/**
 * Area entity manager — syncs area boundaries from the
 * backend and renders them on the globe.
 *
 * Polls GET /api/areas every few seconds and draws all
 * defined shapes.  The active deletion area is drawn in
 * green; inactive shapes are drawn in grey.  Works
 * regardless of which client created the area.
 */
import {
  Viewer,
  Entity,
  Cartesian3,
  Color,
  CustomDataSource,
  PolygonHierarchy,
} from 'cesium';

const COLOR_ACTIVE_FILL = new Color(0, 1, 0, 0.08);
const COLOR_ACTIVE_OUTLINE = new Color(0, 1, 0, 0.6);
const COLOR_INACTIVE_FILL = new Color(0.5, 0.5, 0.5, 0.05);
const COLOR_INACTIVE_OUTLINE = new Color(
  0.5, 0.5, 0.5, 0.4,
);

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

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('areas');
    viewer.dataSources.add(this.source);
  }

  /** Start polling the backend for areas. */
  startPolling(intervalMs = 2000): void {
    this.stopPolling();
    this._fetch();
    this.pollTimer = window.setInterval(
      () => this._fetch(), intervalMs,
    );
  }

  /** Stop polling. */
  stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /** Force an immediate refresh. */
  refresh(): void {
    this._fetch();
  }

  private async _fetch(): Promise<void> {
    try {
      const res = await fetch('/api/areas');
      if (!res.ok) return;
      const text = await res.text();
      // Skip re-render if nothing changed.
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

    for (const shape of Object.values(data.shapes)) {
      const isActive = shape.name === data.active_area;
      const coords = this._toDegreesArray(
        shape.type, shape.coordinates,
      );
      if (!coords || coords.length < 6) continue;

      const positions =
        Cartesian3.fromDegreesArray(coords);

      this.source.entities.add({
        polygon: {
          hierarchy: new PolygonHierarchy(positions),
          material: isActive
            ? COLOR_ACTIVE_FILL
            : COLOR_INACTIVE_FILL,
          outline: true,
          outlineColor: isActive
            ? COLOR_ACTIVE_OUTLINE
            : COLOR_INACTIVE_OUTLINE,
          outlineWidth: 2,
        },
      });
    }
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
