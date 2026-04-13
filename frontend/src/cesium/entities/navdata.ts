/**
 * Navigation data entity manager — renders airports with
 * runway diagrams and waypoint markers on the Cesium globe.
 *
 * Fetches data from the backend on camera move (debounced),
 * filtered by the current view bounds.
 */
import {
  Viewer,
  Cartesian2,
  Cartesian3,
  Color,
  CustomDataSource,
  VerticalOrigin,
  HorizontalOrigin,
  LabelStyle,
  Math as CesiumMath,
  Rectangle,
} from 'cesium';

const APT_COLOR = new Color(0.6, 0.8, 1.0, 0.9);
const RWY_COLOR = new Color(0.5, 0.5, 0.5, 1.0);
const WPT_COLOR = new Color(0.6, 0.8, 1.0, 0.5);

// Runway width in meters for visual rendering.
const RWY_WIDTH_PX = 2;

export class NavdataManager {
  private aptSource: CustomDataSource;
  private wptSource: CustomDataSource;
  private _debounceTimer: number | null = null;
  private _lastBounds = '';
  private _aptVisible = true;
  private _wptVisible = true;

  constructor(private viewer: Viewer) {
    this.aptSource = new CustomDataSource('airports');
    this.wptSource = new CustomDataSource('waypoints');
    viewer.dataSources.add(this.aptSource);
    viewer.dataSources.add(this.wptSource);

    // Fetch navdata when camera stops moving.
    viewer.camera.moveEnd.addEventListener(() => {
      this._debouncedFetch();
    });

    // Initial fetch.
    this._debouncedFetch();
  }

  setAirportsVisible(visible: boolean): void {
    this._aptVisible = visible;
    this.aptSource.show = visible;
  }

  setWaypointsVisible(visible: boolean): void {
    this._wptVisible = visible;
    this.wptSource.show = visible;
  }

  get airportsVisible(): boolean {
    return this._aptVisible;
  }

  get waypointsVisible(): boolean {
    return this._wptVisible;
  }

  private _debouncedFetch(): void {
    if (this._debounceTimer !== null) {
      clearTimeout(this._debounceTimer);
    }
    this._debounceTimer = window.setTimeout(
      () => this._fetchForCurrentView(),
      400,
    );
  }

  private async _fetchForCurrentView(): Promise<void> {
    const rect = this.viewer.camera.computeViewRectangle();
    if (!rect) return;

    const lat1 = CesiumMath.toDegrees(rect.south);
    const lon1 = CesiumMath.toDegrees(rect.west);
    const lat2 = CesiumMath.toDegrees(rect.north);
    const lon2 = CesiumMath.toDegrees(rect.east);

    // Compute a rough zoom level from camera height.
    const camHeight =
      this.viewer.camera.positionCartographic.height;
    const zoom = this._heightToZoom(camHeight);

    const key = `${lat1.toFixed(1)},${lon1.toFixed(1)},` +
      `${lat2.toFixed(1)},${lon2.toFixed(1)},${zoom.toFixed(1)}`;
    if (key === this._lastBounds) return;
    this._lastBounds = key;

    await Promise.all([
      this._fetchAirports(lat1, lon1, lat2, lon2, zoom),
      zoom >= 2
        ? this._fetchWaypoints(lat1, lon1, lat2, lon2)
        : this._clearWaypoints(),
    ]);
  }

  private async _fetchAirports(
    lat1: number, lon1: number,
    lat2: number, lon2: number,
    zoom: number,
  ): Promise<void> {
    try {
      const params = new URLSearchParams({
        lat1: lat1.toString(),
        lon1: lon1.toString(),
        lat2: lat2.toString(),
        lon2: lon2.toString(),
        zoom: zoom.toString(),
      });
      const res = await fetch(
        `/api/navdata/airports?${params}`,
      );
      if (!res.ok) return;
      const airports: any[] = await res.json();
      this._renderAirports(airports, zoom);
    } catch {
      // Network error — skip.
    }
  }

  private async _fetchWaypoints(
    lat1: number, lon1: number,
    lat2: number, lon2: number,
  ): Promise<void> {
    try {
      const params = new URLSearchParams({
        lat1: lat1.toString(),
        lon1: lon1.toString(),
        lat2: lat2.toString(),
        lon2: lon2.toString(),
      });
      const res = await fetch(
        `/api/navdata/waypoints?${params}`,
      );
      if (!res.ok) return;
      const wpts: any[] = await res.json();
      this._renderWaypoints(wpts);
    } catch {
      // Network error — skip.
    }
  }

  private _renderAirports(
    airports: any[],
    zoom: number,
  ): void {
    this.aptSource.entities.removeAll();

    for (const apt of airports) {
      // Airport label.
      this.aptSource.entities.add({
        position: Cartesian3.fromDegrees(
          apt.lon, apt.lat, 0,
        ),
        point: {
          pixelSize: apt.type === 1 ? 6 : 4,
          color: APT_COLOR,
        },
        label: {
          text: apt.id,
          font: '11px monospace',
          fillColor: APT_COLOR,
          outlineColor: Color.BLACK,
          outlineWidth: 1,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(10, 0),
          verticalOrigin: VerticalOrigin.CENTER,
          horizontalOrigin: HorizontalOrigin.LEFT,
          showBackground: true,
          backgroundColor: new Color(0, 0, 0, 0.2),
        },
      });

      // Runway lines (visible when zoomed in).
      if (apt.runways && zoom >= 1.5) {
        for (const rwy of apt.runways) {
          this.aptSource.entities.add({
            polyline: {
              positions: Cartesian3.fromDegreesArray([
                rwy.end1.lon, rwy.end1.lat,
                rwy.end2.lon, rwy.end2.lat,
              ]),
              width: RWY_WIDTH_PX,
              material: RWY_COLOR,
              clampToGround: true,
            },
          });
        }
      }
    }
  }

  private _renderWaypoints(wpts: any[]): void {
    this.wptSource.entities.removeAll();
    for (const wp of wpts) {
      this.wptSource.entities.add({
        position: Cartesian3.fromDegrees(
          wp.lon, wp.lat, 0,
        ),
        point: {
          pixelSize: 3,
          color: WPT_COLOR,
        },
        label: {
          text: wp.id,
          font: '10px monospace',
          fillColor: WPT_COLOR,
          outlineColor: Color.BLACK,
          outlineWidth: 1,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(6, 0),
          verticalOrigin: VerticalOrigin.CENTER,
          horizontalOrigin: HorizontalOrigin.LEFT,
          showBackground: false,
        },
      });
    }
  }

  private _clearWaypoints(): Promise<void> {
    this.wptSource.entities.removeAll();
    return Promise.resolve();
  }

  /** Map camera height to a rough zoom level. */
  private _heightToZoom(height: number): number {
    if (height > 5_000_000) return 0.3;
    if (height > 2_000_000) return 0.7;
    if (height > 500_000) return 1.5;
    if (height > 100_000) return 3;
    if (height > 20_000) return 5;
    return 8;
  }
}
