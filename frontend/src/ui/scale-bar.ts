/**
 * Scale bar for the Cesium viewer.
 *
 * Shows the horizontal distance represented by a
 * ~100 px bar at the center of the current view.
 * Displays both kilometers and nautical miles — nm is
 * the standard aviation unit.
 *
 * Updates as the camera moves.  Rounds to "nice"
 * numbers (1, 2, 5, 10, 20, 50, ...) for readability.
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import type { Viewer } from 'cesium';
import {
  Cartographic,
  Cartesian2,
  EllipsoidGeodesic,
  Ellipsoid,
} from 'cesium';

const TARGET_PIXELS = 120;  // desired bar length
const NM_PER_M = 1 / 1852;

// Nice values to round to (in meters).
const NICE_VALUES_M = [
  1, 2, 5, 10, 20, 50,
  100, 200, 500,
  1_000, 2_000, 5_000,
  10_000, 20_000, 50_000,
  100_000, 200_000, 500_000,
  1_000_000, 2_000_000, 5_000_000,
];

@customElement('scale-bar')
export class ScaleBar extends LitElement {
  @state() private pixelWidth = 100;
  @state() private meters = 0;

  private viewer: Viewer | null = null;
  private _listener: (() => void) | null = null;

  static styles = css`
    :host {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 8px;
      background: rgba(0, 0, 0, 0.75);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 11px;
      border-radius: 3px;
      border: 1px solid #2a2a2a;
      user-select: none;
    }
    .bar {
      position: relative;
      height: 10px;
      border-left: 1px solid #00ff00;
      border-right: 1px solid #00ff00;
      border-bottom: 1px solid #00ff00;
    }
    .labels {
      display: flex;
      flex-direction: column;
      line-height: 1.1;
    }
    .nm { color: #ffff00; }
    .km { color: #00ff00; }
  `;

  render() {
    const nm = this.meters * NM_PER_M;
    return html`
      <div class="bar" style=${
        `width: ${this.pixelWidth}px`
      }></div>
      <div class="labels">
        <span class="nm">${this._fmt(nm)} nm</span>
        <span class="km">
          ${this._fmtMeters(this.meters)}
        </span>
      </div>
    `;
  }

  setViewer(v: Viewer): void {
    this.viewer = v;
    this._listener = () => this._update();
    v.camera.changed.addEventListener(this._listener);
    v.camera.moveEnd.addEventListener(this._listener);
    this._update();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this.viewer && this._listener) {
      this.viewer.camera.changed.removeEventListener(
        this._listener,
      );
      this.viewer.camera.moveEnd.removeEventListener(
        this._listener,
      );
    }
  }

  private _update(): void {
    if (!this.viewer) return;
    const scene = this.viewer.scene;
    const canvas = scene.canvas;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (width === 0 || height === 0) return;

    // Pick the ground distance between two points
    // spanning TARGET_PIXELS horizontally at mid-height.
    const y = height / 2;
    const x1 = width / 2 - TARGET_PIXELS / 2;
    const x2 = width / 2 + TARGET_PIXELS / 2;

    const ray1 = this.viewer.camera.getPickRay(
      new Cartesian2(x1, y),
    );
    const ray2 = this.viewer.camera.getPickRay(
      new Cartesian2(x2, y),
    );
    if (!ray1 || !ray2) return;

    const p1 = scene.globe.pick(ray1, scene);
    const p2 = scene.globe.pick(ray2, scene);
    if (!p1 || !p2) return;

    const c1 = Cartographic.fromCartesian(p1);
    const c2 = Cartographic.fromCartesian(p2);
    const geodesic = new EllipsoidGeodesic(
      c1, c2, Ellipsoid.WGS84,
    );
    const dist = geodesic.surfaceDistance;
    if (!isFinite(dist) || dist <= 0) return;

    // Find the nearest "nice" distance ≤ dist.
    let nice = NICE_VALUES_M[0];
    for (const v of NICE_VALUES_M) {
      if (v <= dist) nice = v;
    }

    // Scale the bar width proportionally.
    const scale = nice / dist;
    this.pixelWidth = Math.round(TARGET_PIXELS * scale);
    this.meters = nice;
  }

  private _fmt(val: number): string {
    if (val < 1) return val.toFixed(2);
    if (val < 10) return val.toFixed(1);
    return String(Math.round(val));
  }

  private _fmtMeters(m: number): string {
    if (m < 1000) return `${Math.round(m)} m`;
    return `${this._fmt(m / 1000)} km`;
  }
}
