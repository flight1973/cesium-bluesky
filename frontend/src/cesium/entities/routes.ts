/**
 * Route entity manager — draws the active flight plan as
 * magenta polylines with waypoint markers when an aircraft
 * is selected.
 */
import {
  Viewer,
  Cartesian3,
  Cartesian2,
  Color,
  CustomDataSource,
  VerticalOrigin,
  LabelStyle,
} from 'cesium';
import { FT, KTS } from '../../types';

const ROUTE_COLOR = Color.MAGENTA;
const ACTIVE_WP_COLOR = Color.YELLOW;

interface RouteResponse {
  acid: string;
  route: {
    iactwp: number;
    wpname: string[];
    wplat: number[];
    wplon: number[];
    wpalt: number[];
    wpspd: number[];
  };
  lat: number;
  lon: number;
  alt: number;
}

export class RouteManager {
  private source: CustomDataSource;
  private _visible = true;
  private currentAcid: string | null = null;
  private _altScale = 1.0;

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('routes');
    viewer.dataSources.add(this.source);
  }

  /** Fetch and display route for an aircraft. */
  async showRoute(acid: string): Promise<void> {
    this.clear();
    if (!acid || !this._visible) {
      this.currentAcid = null;
      return;
    }

    this.currentAcid = acid;

    try {
      const res = await fetch(
        `/api/aircraft/${acid}/detail`,
      );
      if (!res.ok) return;
      const data: RouteResponse = await res.json();
      this._drawRoute(data);
    } catch {
      // Network error — silently ignore.
    }
  }

  /** Set altitude exaggeration to match aircraft. */
  setAltScale(scale: number): void {
    this._altScale = scale;
  }

  /** Toggle route visibility. */
  setVisible(visible: boolean): void {
    this._visible = visible;
    this.source.show = visible;
  }

  get visible(): boolean {
    return this._visible;
  }

  /** Clear current route display. */
  clear(): void {
    this.source.entities.removeAll();
  }

  private _drawRoute(data: RouteResponse): void {
    const r = data.route;
    if (!r.wpname.length) return;

    // Build position array: aircraft → waypoints.
    const s = this._altScale;
    const positions: Cartesian3[] = [
      Cartesian3.fromDegrees(
        data.lon, data.lat, data.alt * s,
      ),
    ];
    for (let i = 0; i < r.wplat.length; i++) {
      const wpAlt = r.wpalt[i] > 0 ? r.wpalt[i] : data.alt;
      positions.push(
        Cartesian3.fromDegrees(
          r.wplon[i], r.wplat[i], wpAlt * s,
        ),
      );
    }

    // Route polyline.
    this.source.entities.add({
      polyline: {
        positions,
        width: 2,
        material: ROUTE_COLOR,
        clampToGround: false,
      },
    });

    // Waypoint markers.
    for (let i = 0; i < r.wpname.length; i++) {
      const isActive = i === r.iactwp;
      const wpAlt = r.wpalt[i] > 0 ? r.wpalt[i] : 0;
      const fl = Math.round(wpAlt / FT / 100);
      const spdRaw = r.wpspd[i];
      let spdLabel = '---';
      if (spdRaw > 0) {
        spdLabel = spdRaw < 1
          ? `M${spdRaw.toFixed(2)}`
          : `${Math.round(spdRaw / KTS)}`;
      }
      const altLabel = wpAlt > 0
        ? `FL${fl}`
        : '-----';

      const markerAlt = (wpAlt > 0 ? wpAlt : data.alt) * s;
      this.source.entities.add({
        position: Cartesian3.fromDegrees(
          r.wplon[i], r.wplat[i], markerAlt,
        ),
        point: {
          pixelSize: isActive ? 8 : 5,
          color: isActive
            ? ACTIVE_WP_COLOR
            : ROUTE_COLOR,
        },
        label: {
          text: `${r.wpname[i]}\n${altLabel}/${spdLabel}`,
          font: '11px monospace',
          fillColor: ROUTE_COLOR,
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(10, -5),
          verticalOrigin: VerticalOrigin.CENTER,
          showBackground: true,
          backgroundColor: new Color(0, 0, 0, 0.5),
        },
      });
    }
  }
}
