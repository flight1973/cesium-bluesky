/**
 * Camera pan / tilt / zoom control widget.
 *
 * Overlays the bottom-left of the Cesium viewer.
 * Provides arrow buttons for pan, +/- for zoom,
 * tilt up/down, and preset view buttons.
 *
 * Layout:
 *       [TOP]
 *        [↑]
 *   [←]  [⊙]  [→]   [+]  [TILT↑]
 *        [↓]         [-]  [TILT↓]
 */
import { LitElement, html, css } from 'lit';
import { customElement } from 'lit/decorators.js';
import type { Viewer } from 'cesium';
import {
  Cartesian3,
  Math as CesiumMath,
} from 'cesium';

@customElement('camera-controls')
export class CameraControls extends LitElement {
  private viewer: Viewer | null = null;

  static styles = css`
    :host {
      display: flex;
      gap: 8px;
      padding: 6px;
      background: rgba(0, 0, 0, 0.8);
      border-radius: 6px;
      user-select: none;
    }

    .pad {
      display: grid;
      grid-template-columns: 28px 28px 28px;
      grid-template-rows: 28px 28px 28px;
      gap: 2px;
    }

    .col {
      display: flex;
      flex-direction: column;
      gap: 2px;
      justify-content: center;
    }

    button {
      width: 28px;
      height: 28px;
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 3px;
      cursor: pointer;
      font-size: 14px;
      font-family: inherit;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      line-height: 1;
    }
    button:hover {
      background: #00ff00;
      color: #000;
    }
    button:active {
      background: #00cc00;
    }
    button.wide {
      width: auto;
      padding: 0 6px;
      font-size: 10px;
    }

    .spacer { width: 28px; height: 28px; }
  `;

  render() {
    return html`
      <!-- Pan d-pad -->
      <div class="pad">
        <div class="spacer"></div>
        <button @click=${this._panUp}
          title="Pan north">\u25B2</button>
        <div class="spacer"></div>

        <button @click=${this._panLeft}
          title="Pan west">\u25C0</button>
        <button @click=${this._resetTop}
          title="Top-down view">\u25CE</button>
        <button @click=${this._panRight}
          title="Pan east">\u25B6</button>

        <div class="spacer"></div>
        <button @click=${this._panDown}
          title="Pan south">\u25BC</button>
        <div class="spacer"></div>
      </div>

      <!-- Zoom + Tilt -->
      <div class="col">
        <button @click=${this._zoomIn}
          title="Zoom in">+</button>
        <button @click=${this._zoomOut}
          title="Zoom out">\u2212</button>
      </div>
      <div class="col">
        <button class="wide" @click=${this._tiltUp}
          title="Tilt up">TILT\u25B2</button>
        <button class="wide" @click=${this._tiltDown}
          title="Tilt down">TILT\u25BC</button>
      </div>
    `;
  }

  /** Attach to a Cesium viewer instance. */
  setViewer(v: Viewer): void {
    this.viewer = v;
  }

  // ── Pan ───────────────────────────────────────────

  private _panAmount(): number {
    if (!this.viewer) return 0;
    // Scale pan distance by current camera height.
    const h = this.viewer.camera
      .positionCartographic.height;
    return h * 0.15;
  }

  private _panUp(): void {
    this.viewer?.camera.moveUp(this._panAmount());
  }
  private _panDown(): void {
    this.viewer?.camera.moveDown(this._panAmount());
  }
  private _panLeft(): void {
    this.viewer?.camera.moveLeft(this._panAmount());
  }
  private _panRight(): void {
    this.viewer?.camera.moveRight(this._panAmount());
  }

  // ── Zoom ──────────────────────────────────────────

  private _zoomIn(): void {
    this.viewer?.camera.zoomIn(
      this.viewer.camera.positionCartographic.height * 0.3,
    );
  }
  private _zoomOut(): void {
    this.viewer?.camera.zoomOut(
      this.viewer.camera.positionCartographic.height * 0.3,
    );
  }

  // ── Tilt ──────────────────────────────────────────

  private _tiltUp(): void {
    if (!this.viewer) return;
    const cam = this.viewer.camera;
    cam.lookUp(CesiumMath.toRadians(10));
  }
  private _tiltDown(): void {
    if (!this.viewer) return;
    const cam = this.viewer.camera;
    cam.lookDown(CesiumMath.toRadians(10));
  }

  // ── Presets ───────────────────────────────────────

  private _resetTop(): void {
    if (!this.viewer) return;
    const cam = this.viewer.camera;
    const carto = cam.positionCartographic;
    cam.setView({
      destination: Cartesian3.fromRadians(
        carto.longitude,
        carto.latitude,
        carto.height,
      ),
      orientation: {
        heading: 0,
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
    });
  }
}
