/**
 * Area drawing tool for defining BlueSky deletion areas.
 *
 * Modes:
 *   BOX  — click two corners to define a rectangle
 *   POLY — click multiple points, double-click to finish
 *
 * Shows a live preview polygon on the globe while drawing.
 * After drawing, sends the shape command (BOX/POLY) and
 * then AREA <name> to activate it as the deletion area.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import {
  Viewer,
  Entity,
  Cartesian3,
  Color,
  PolygonHierarchy,
} from 'cesium';

type DrawMode = 'off' | 'box' | 'poly';

interface LatLon {
  lat: number;
  lon: number;
}

@customElement('area-tool')
export class AreaTool extends LitElement {
  @state() private mode: DrawMode = 'off';
  @state() private points: LatLon[] = [];
  @state() private areaName = 'SIMAREA';
  @state() private areaActive = false;

  private onCommand:
    ((cmd: string) => void) | null = null;
  private onStartDraw:
    ((cb: (lat: number, lon: number) => void,
      doneCb: () => void) => void) | null = null;
  private onStopDraw: (() => void) | null = null;
  private viewer: Viewer | null = null;
  private previewEntity: Entity | null = null;
  private activeEntity: Entity | null = null;
  private lastDrawnPoints: LatLon[] = [];
  private lastDrawnMode: DrawMode = 'off';

  static styles = css`
    :host {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: rgba(0, 0, 0, 0.85);
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      color: #00ff00;
      border-radius: 4px;
    }
    button {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 3px 8px;
      border-radius: 3px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    button:hover {
      background: #00ff00;
      color: #000;
    }
    button.active {
      background: #00ff00;
      color: #000;
    }
    button.danger {
      color: #ff4444;
      border-color: #ff4444;
    }
    button.danger:hover {
      background: #ff4444;
      color: #000;
    }
    input {
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      font-family: inherit;
      font-size: 12px;
      padding: 2px 4px;
      border-radius: 2px;
      width: 80px;
    }
    input:focus {
      border-color: #00ff00;
      outline: none;
    }
    .sep {
      width: 1px;
      height: 18px;
      background: #444;
    }
    .status {
      color: #ffff00;
      font-size: 11px;
    }
    label { color: #888; font-size: 11px; }
  `;

  render() {
    if (this.mode !== 'off') {
      const n = this.points.length;
      let hint: string;
      if (this.mode === 'box') {
        hint = n === 0
          ? 'Click first corner'
          : 'Click opposite corner';
      } else {
        hint = n < 3
          ? `Click points (${n} placed, need 3+)`
          : `${n} points \u2014 dbl-click to finish`;
      }
      return html`
        <span class="status">${hint}</span>
        <button class="danger"
          @click=${this._cancel}
        >CANCEL</button>
      `;
    }

    return html`
      <label>Area:</label>
      <input
        .value=${this.areaName}
        @input=${(e: Event) => {
          this.areaName =
            (e.target as HTMLInputElement).value;
        }}
      />
      <button @click=${this._startBox}>
        DRAW BOX
      </button>
      <button @click=${this._startPoly}>
        DRAW POLY
      </button>
      <div class="sep"></div>
      <button
        class=${this.areaActive ? 'active' : ''}
        @click=${this._toggleArea}
      >${this.areaActive
          ? 'AREA ON' : 'AREA OFF'}</button>
      <button @click=${this._checkArea}>
        CHECK
      </button>
    `;
  }

  setCommandHandler(
    handler: (cmd: string) => void,
  ): void {
    this.onCommand = handler;
  }

  setViewer(v: Viewer): void {
    this.viewer = v;
  }

  setDrawCallbacks(
    startDraw: (
      pointCb: (lat: number, lon: number) => void,
      doneCb: () => void,
    ) => void,
    stopDraw: () => void,
  ): void {
    this.onStartDraw = startDraw;
    this.onStopDraw = stopDraw;
  }

  // ── Drawing modes ─────────────────────────────────

  private _startBox(): void {
    this.mode = 'box';
    this.points = [];
    this.onStartDraw?.(
      (lat, lon) => this._addPoint(lat, lon),
      () => this._finishDraw(),
    );
  }

  private _startPoly(): void {
    this.mode = 'poly';
    this.points = [];
    this.onStartDraw?.(
      (lat, lon) => this._addPoint(lat, lon),
      () => this._finishDraw(),
    );
  }

  private _cancel(): void {
    this.mode = 'off';
    this.points = [];
    this._clearPreview();
    this.onStopDraw?.();
  }

  private _addPoint(lat: number, lon: number): void {
    this.points = [...this.points, { lat, lon }];
    this._updatePreview();

    if (this.mode === 'box' && this.points.length >= 2) {
      this._finishDraw();
    }
  }

  private _finishDraw(): void {
    const name = this.areaName || 'SIMAREA';

    if (this.mode === 'box' && this.points.length >= 2) {
      const p = this.points;
      const cmd =
        `BOX ${name},` +
        `${p[0].lat.toFixed(6)},` +
        `${p[0].lon.toFixed(6)},` +
        `${p[1].lat.toFixed(6)},` +
        `${p[1].lon.toFixed(6)}`;
      this.onCommand?.(cmd);
    } else if (
      this.mode === 'poly' && this.points.length >= 3
    ) {
      const coords = this.points
        .map(
          (p) =>
            `${p.lat.toFixed(6)},${p.lon.toFixed(6)}`,
        )
        .join(',');
      this.onCommand?.(`POLY ${name},${coords}`);
    }

    // Save the drawn shape for persistent display.
    this.lastDrawnPoints = [...this.points];
    this.lastDrawnMode = this.mode;

    // Activate and verify the area was created.
    setTimeout(async () => {
      this.onCommand?.(`AREA ${name}`);
      // Poll backend to confirm.
      await this._verifyArea(name);
    }, 300);

    this.mode = 'off';
    this.points = [];
    this._clearPreview();
    this.onStopDraw?.();
  }

  private async _checkArea(): Promise<void> {
    try {
      const res = await fetch('/api/areas');
      if (!res.ok) return;
      const data = await res.json();
      const names = Object.keys(data.shapes || {});
      const active = data.active_area;
      let msg = `Shapes: ${names.length > 0
          ? names.join(', ') : 'none'}`;
      msg += ` | Active: ${active || 'none'}`;
      this.dispatchEvent(
        new CustomEvent('echo', {
          detail: { text: msg },
          bubbles: true,
          composed: true,
        }),
      );
      // Sync button and display with backend.
      this.areaActive = !!active;
      this._clearActiveArea();
      if (this.areaActive && active) {
        const shape = data.shapes[active];
        if (shape) {
          this._showAreaFromCoords(
            shape.type, shape.coordinates,
          );
        }
      }
    } catch {
      // Non-fatal.
    }
  }

  private _toggleArea(): void {
    if (this.areaActive) {
      this.onCommand?.('AREA OFF');
      this.areaActive = false;
      this._clearActiveArea();
    } else {
      const name = this.areaName || 'SIMAREA';
      this.onCommand?.(`AREA ${name}`);
      this.areaActive = true;
      // Fetch coords from backend to display.
      setTimeout(() => this._checkArea(), 500);
    }
  }

  // ── Backend verification ───────────────────────────

  private async _verifyArea(name: string): Promise<void> {
    await new Promise((r) => setTimeout(r, 500));
    try {
      const res = await fetch('/api/areas');
      if (!res.ok) return;
      const data = await res.json();
      const shape = data.shapes?.[name];
      if (!shape) return;
      if (data.active_area !== name) {
        this.onCommand?.(`AREA ${name}`);
        await new Promise((r) => setTimeout(r, 500));
      }
      this.areaActive = true;
      this._clearActiveArea();
      this._showAreaFromCoords(
        shape.type, shape.coordinates,
      );
    } catch {
      // Non-fatal — fall back to local preview.
      this.areaActive = true;
      this._showActiveArea();
    }
  }

  // ── Live preview on the globe ─────────────────────

  private _updatePreview(): void {
    if (!this.viewer) return;
    this._clearPreview();

    if (this.points.length === 1) {
      // Single point — yellow dot.
      this.previewEntity = this.viewer.entities.add({
        position: Cartesian3.fromDegrees(
          this.points[0].lon, this.points[0].lat,
        ),
        point: {
          pixelSize: 8,
          color: Color.YELLOW,
        },
      });
      return;
    }

    // Build polygon positions.
    let coords: number[];
    if (this.mode === 'box' && this.points.length >= 2) {
      const a = this.points[0];
      const b = this.points[1];
      coords = [
        a.lon, a.lat,
        b.lon, a.lat,
        b.lon, b.lat,
        a.lon, b.lat,
      ];
    } else if (this.points.length >= 2) {
      coords = [];
      for (const p of this.points) {
        coords.push(p.lon, p.lat);
      }
    } else {
      return;
    }

    const positions =
      Cartesian3.fromDegreesArray(coords);

    this.previewEntity = this.viewer.entities.add({
      polygon: {
        hierarchy: new PolygonHierarchy(positions),
        material: new Color(1, 1, 0, 0.15),
        outline: true,
        outlineColor: Color.YELLOW,
        outlineWidth: 2,
      },
    });
  }

  private _clearPreview(): void {
    if (this.previewEntity && this.viewer) {
      this.viewer.entities.remove(this.previewEntity);
      this.previewEntity = null;
    }
  }

  // ── Persistent active area display ────────────────

  private _showActiveArea(): void {
    if (!this.viewer || this.lastDrawnPoints.length < 2) {
      return;
    }
    this._clearActiveArea();

    let coords: number[];
    if (
      this.lastDrawnMode === 'box'
      && this.lastDrawnPoints.length >= 2
    ) {
      const a = this.lastDrawnPoints[0];
      const b = this.lastDrawnPoints[1];
      coords = [
        a.lon, a.lat,
        b.lon, a.lat,
        b.lon, b.lat,
        a.lon, b.lat,
      ];
    } else {
      coords = [];
      for (const p of this.lastDrawnPoints) {
        coords.push(p.lon, p.lat);
      }
    }

    const positions =
      Cartesian3.fromDegreesArray(coords);

    this.activeEntity = this.viewer.entities.add({
      polygon: {
        hierarchy: new PolygonHierarchy(positions),
        material: new Color(0, 1, 0, 0.08),
        outline: true,
        outlineColor: new Color(0, 1, 0, 0.6),
        outlineWidth: 2,
      },
    });
  }

  /**
   * Draw area boundary from backend coordinates.
   *
   * Coordinates from BlueSky are [lat,lon,lat,lon,...].
   * For Box: [lat1,lon1,lat2,lon2] (two corners).
   * For Poly: [lat1,lon1,lat2,lon2,...] (vertices).
   */
  private _showAreaFromCoords(
    shapeType: string,
    coordinates: number[],
  ): void {
    if (!this.viewer || coordinates.length < 4) return;
    this._clearActiveArea();

    // Build [lon,lat,...] array for Cesium.
    let cesiumCoords: number[];
    if (shapeType === 'Box') {
      const lat1 = coordinates[0];
      const lon1 = coordinates[1];
      const lat2 = coordinates[2];
      const lon2 = coordinates[3];
      cesiumCoords = [
        lon1, lat1,
        lon2, lat1,
        lon2, lat2,
        lon1, lat2,
      ];
    } else {
      // Poly — coords are [lat,lon,lat,lon,...]
      cesiumCoords = [];
      for (let i = 0; i < coordinates.length - 1; i += 2) {
        cesiumCoords.push(
          coordinates[i + 1], coordinates[i],
        );
      }
    }

    const positions =
      Cartesian3.fromDegreesArray(cesiumCoords);

    this.activeEntity = this.viewer.entities.add({
      polygon: {
        hierarchy: new PolygonHierarchy(positions),
        material: new Color(0, 1, 0, 0.08),
        outline: true,
        outlineColor: new Color(0, 1, 0, 0.6),
        outlineWidth: 2,
      },
    });
  }

  private _clearActiveArea(): void {
    if (this.activeEntity && this.viewer) {
      this.viewer.entities.remove(this.activeEntity);
      this.activeEntity = null;
    }
  }
}
