import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import type { Viewer } from 'cesium';
import {
  Cartesian3,
  Cartographic,
  Color,
  Entity,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  EllipsoidGeodesic,
  Math as CesiumMath,
  PolylineGlowMaterialProperty,
  CustomDataSource,
  ConstantProperty,
  ConstantPositionProperty,
  HorizontalOrigin,
  VerticalOrigin,
  LabelStyle,
} from 'cesium';

type MeasureUnit = 'm' | 'km' | 'ft' | 'mi' | 'nm' | 'deg';

const UNIT_LABELS: Record<MeasureUnit, string> = {
  m: 'Meters', km: 'Kilometers', ft: 'Feet',
  mi: 'Miles', nm: 'Nautical Miles', deg: 'Degrees',
};

function convertDistance(meters: number, unit: MeasureUnit): number {
  switch (unit) {
    case 'm': return meters;
    case 'km': return meters / 1000;
    case 'ft': return meters * 3.28084;
    case 'mi': return meters / 1609.344;
    case 'nm': return meters / 1852;
    case 'deg': return meters / 111320;
  }
}

function formatDist(meters: number, unit: MeasureUnit): string {
  const v = convertDistance(meters, unit);
  if (v >= 1000) return `${v.toFixed(1)} ${unit}`;
  if (v >= 100) return `${v.toFixed(1)} ${unit}`;
  if (v >= 10) return `${v.toFixed(2)} ${unit}`;
  return `${v.toFixed(3)} ${unit}`;
}

function formatBearing(deg: number): string {
  const d = ((deg % 360) + 360) % 360;
  return `${d.toFixed(1)}°`;
}

interface MeasurePoint {
  lat: number;
  lon: number;
  cart: Cartesian3;
}

@customElement('measure-tool')
export class MeasureTool extends LitElement {
  @state() private active = false;
  @state() private unit: MeasureUnit = 'nm';
  @state() private points: MeasurePoint[] = [];
  @state() private segments: { dist: number; bearing: number }[] = [];
  @state() private totalDist = 0;
  @state() private mousePos: { lat: number; lon: number; dist: number; bearing: number } | null = null;

  private viewer: Viewer | null = null;
  private handler: ScreenSpaceEventHandler | null = null;
  private source: CustomDataSource | null = null;
  private _lineEntity: Entity | null = null;
  private _mouseLineEntity: Entity | null = null;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.88);
      border: 1px solid #333;
      border-radius: 4px;
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 11px;
      padding: 6px 10px;
      min-width: 240px;
    }
    :host([hidden]) { display: none; }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }
    .title { font-weight: bold; font-size: 12px; }

    .row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 3px 0;
    }

    button {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 3px;
      cursor: pointer;
      font-family: inherit;
      font-size: 10px;
      padding: 2px 8px;
    }
    button:hover { background: #00ff00; color: #000; }
    button.active { background: #00ff00; color: #000; }
    button.stop { border-color: #ff4444; color: #ff4444; }
    button.stop:hover { background: #ff4444; color: #000; }

    select {
      background: #222;
      color: #00ff00;
      border: 1px solid #444;
      border-radius: 3px;
      font-family: inherit;
      font-size: 10px;
      padding: 1px 4px;
    }

    .total {
      font-size: 14px;
      font-weight: bold;
      color: #00ff00;
      margin: 6px 0 2px;
    }

    .segment {
      color: #888;
      font-size: 10px;
      padding: 1px 0;
    }

    .hint { color: #555; font-size: 10px; margin-top: 4px; }

    .mouse-pos { color: #aaa; font-size: 10px; }

    .coord { color: #666; font-size: 9px; }
  `;

  render() {
    if (!this.active) {
      return html`
        <div class="row">
          <button @click=${this._start}>MEASURE</button>
        </div>
      `;
    }

    return html`
      <div class="header">
        <span class="title">MEASURE</span>
        <button class="stop" @click=${this._stop}>\u2716</button>
      </div>

      <div class="row">
        <select .value=${this.unit} @change=${this._onUnit}>
          ${(Object.keys(UNIT_LABELS) as MeasureUnit[]).map(u => html`
            <option value=${u} ?selected=${this.unit === u}>${UNIT_LABELS[u]}</option>
          `)}
        </select>
        <button @click=${this._clear}>CLEAR</button>
        <button @click=${this._undo}>UNDO</button>
      </div>

      ${this.points.length >= 2 ? html`
        <div class="total">
          Total: ${formatDist(this.totalDist, this.unit)}
        </div>
      ` : nothing}

      ${this.segments.map((s, i) => html`
        <div class="segment">
          ${i + 1}\u2192${i + 2}: ${formatDist(s.dist, this.unit)} @ ${formatBearing(s.bearing)}
        </div>
      `)}

      ${this.mousePos && this.points.length > 0 ? html`
        <div class="mouse-pos">
          \u2192 cursor: ${formatDist(this.mousePos.dist, this.unit)} @ ${formatBearing(this.mousePos.bearing)}
        </div>
      ` : nothing}

      ${this.points.length > 0 ? html`
        <div class="coord">
          Last: ${this.points[this.points.length - 1].lat.toFixed(5)}, ${this.points[this.points.length - 1].lon.toFixed(5)}
        </div>
      ` : nothing}

      <div class="hint">
        ${this.points.length === 0
          ? 'Click on map to start measuring'
          : 'Click to add point, double-click to finish'}
      </div>
    `;
  }

  setViewer(v: Viewer): void {
    this.viewer = v;
    this.source = new CustomDataSource('measure');
    v.dataSources.add(this.source);
  }

  private _start(): void {
    if (!this.viewer) return;
    this.active = true;
    this._setupHandler();
  }

  private _stop(): void {
    this.active = false;
    this._teardownHandler();
    this._clear();
  }

  private _clear(): void {
    this.points = [];
    this.segments = [];
    this.totalDist = 0;
    this.mousePos = null;
    this.source?.entities.removeAll();
    this._lineEntity = null;
    this._mouseLineEntity = null;
  }

  private _undo(): void {
    if (this.points.length === 0) return;
    this.points = this.points.slice(0, -1);
    if (this.segments.length > 0) {
      const removed = this.segments[this.segments.length - 1];
      this.segments = this.segments.slice(0, -1);
      this.totalDist -= removed.dist;
    }
    this._rebuildEntities();
  }

  private _onUnit(e: Event): void {
    this.unit = (e.target as HTMLSelectElement).value as MeasureUnit;
    this._updateLabels();
  }

  private _setupHandler(): void {
    if (!this.viewer || this.handler) return;
    this.handler = new ScreenSpaceEventHandler(this.viewer.scene.canvas);

    this.handler.setInputAction((click: any) => {
      const ll = this._pickGlobe(click.position);
      if (!ll) return;
      this._addPoint(ll.lat, ll.lon, ll.cart);
    }, ScreenSpaceEventType.LEFT_CLICK);

    this.handler.setInputAction(() => {
      this._teardownHandler();
    }, ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

    this.handler.setInputAction((move: any) => {
      if (this.points.length === 0) return;
      const ll = this._pickGlobe(move.endPosition);
      if (!ll) { this.mousePos = null; return; }
      const last = this.points[this.points.length - 1];
      const { dist, bearing } = this._geodesic(last.lat, last.lon, ll.lat, ll.lon);
      this.mousePos = { lat: ll.lat, lon: ll.lon, dist, bearing };
      this._updateMouseLine(last.cart, ll.cart);
    }, ScreenSpaceEventType.MOUSE_MOVE);
  }

  private _teardownHandler(): void {
    if (this.handler) {
      this.handler.destroy();
      this.handler = null;
    }
    if (this._mouseLineEntity && this.source) {
      this.source.entities.remove(this._mouseLineEntity);
      this._mouseLineEntity = null;
    }
  }

  private _pickGlobe(screenPos: any): { lat: number; lon: number; cart: Cartesian3 } | null {
    if (!this.viewer) return null;
    const ray = this.viewer.camera.getPickRay(screenPos);
    if (!ray) return null;
    const cart = this.viewer.scene.globe.pick(ray, this.viewer.scene);
    if (!cart) return null;
    const carto = Cartographic.fromCartesian(cart);
    return {
      lat: CesiumMath.toDegrees(carto.latitude),
      lon: CesiumMath.toDegrees(carto.longitude),
      cart: Cartesian3.clone(cart),
    };
  }

  private _geodesic(lat1: number, lon1: number, lat2: number, lon2: number): { dist: number; bearing: number } {
    const geo = new EllipsoidGeodesic(
      Cartographic.fromDegrees(lon1, lat1),
      Cartographic.fromDegrees(lon2, lat2),
    );
    return {
      dist: geo.surfaceDistance,
      bearing: CesiumMath.toDegrees(geo.startHeading),
    };
  }

  private _addPoint(lat: number, lon: number, cart: Cartesian3): void {
    const newPt: MeasurePoint = { lat, lon, cart };

    if (this.points.length > 0) {
      const prev = this.points[this.points.length - 1];
      const { dist, bearing } = this._geodesic(prev.lat, prev.lon, lat, lon);
      this.segments = [...this.segments, { dist, bearing }];
      this.totalDist += dist;
    }

    this.points = [...this.points, newPt];
    this._rebuildEntities();
  }

  private _rebuildEntities(): void {
    if (!this.source) return;
    this.source.entities.removeAll();
    this._lineEntity = null;
    this._mouseLineEntity = null;

    for (let i = 0; i < this.points.length; i++) {
      const p = this.points[i];
      this.source.entities.add({
        position: p.cart,
        point: {
          pixelSize: 8,
          color: Color.CYAN,
          outlineColor: Color.WHITE,
          outlineWidth: 1,
        },
        label: {
          text: `${i + 1}`,
          font: '11px Consolas',
          fillColor: Color.CYAN,
          style: LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          horizontalOrigin: HorizontalOrigin.LEFT,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian3(6, -6, 0) as any,
        },
      });
    }

    if (this.points.length >= 2) {
      const positions = this.points.map(p => p.cart);
      this._lineEntity = this.source.entities.add({
        polyline: {
          positions,
          width: 2,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.15,
            color: Color.CYAN,
          }),
          clampToGround: true,
        },
      });

      for (let i = 0; i < this.segments.length; i++) {
        const a = this.points[i];
        const b = this.points[i + 1];
        const mid = Cartesian3.midpoint(a.cart, b.cart, new Cartesian3());
        this.source.entities.add({
          position: mid,
          label: {
            text: formatDist(this.segments[i].dist, this.unit),
            font: '10px Consolas',
            fillColor: Color.YELLOW,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            horizontalOrigin: HorizontalOrigin.CENTER,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian3(0, -8, 0) as any,
          },
        });
      }
    }
  }

  private _updateLabels(): void {
    this._rebuildEntities();
  }

  private _updateMouseLine(from: Cartesian3, to: Cartesian3): void {
    if (!this.source) return;
    if (this._mouseLineEntity) {
      this._mouseLineEntity.polyline!.positions =
        new ConstantProperty([from, to]);
    } else {
      this._mouseLineEntity = this.source.entities.add({
        polyline: {
          positions: [from, to],
          width: 1.5,
          material: Color.CYAN.withAlpha(0.5),
          clampToGround: true,
        },
      });
    }
  }
}
