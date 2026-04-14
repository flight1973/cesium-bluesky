/**
 * Camera pan / tilt / zoom control widget.
 *
 * Overlays the bottom-left of the Cesium viewer.
 * Provides arrow buttons for pan, +/- for zoom,
 * tilt up/down with the current pitch angle shown
 * between the buttons, and a top-down preset.
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import type { Viewer } from 'cesium';
import {
  Cartesian3,
  Math as CesiumMath,
} from 'cesium';

@customElement('camera-controls')
export class CameraControls extends LitElement {
  @state() private pitchDeg = -90;
  @state() private heightM = 500000;
  private viewer: Viewer | null = null;
  private _moveEndListener: (() => void) | null = null;
  private _changeListener: (() => void) | null = null;

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
      align-items: center;
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

    .tilt-label, .zoom-label {
      font-size: 10px;
      color: #00ff00;
      text-align: center;
      min-width: 42px;
      padding: 2px 0;
      font-family: inherit;
    }
    .zoom-label {
      min-width: 32px;
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

      <!-- Zoom column with altitude readout -->
      <div class="col">
        <button @click=${this._zoomIn}
          title="Zoom in">+</button>
        <span class="zoom-label"
          title="Camera altitude above surface"
        >${this._formatHeight()}</span>
        <button @click=${this._zoomOut}
          title="Zoom out">\u2212</button>
      </div>

      <!-- Tilt column with angle readout -->
      <div class="col">
        <button class="wide" @click=${this._tiltUp}
          title="Tilt up">TILT\u25B2</button>
        <span class="tilt-label"
          title="Current camera pitch (0=level, -90=down)"
        >${this._formatPitch()}</span>
        <button class="wide" @click=${this._tiltDown}
          title="Tilt down">TILT\u25BC</button>
      </div>
    `;
  }

  /** Attach to a Cesium viewer instance. */
  setViewer(v: Viewer): void {
    this.viewer = v;
    this._startTracking();
    this._updatePitch();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._stopTracking();
  }

  private _startTracking(): void {
    if (!this.viewer) return;
    this._stopTracking();
    // Update on camera moveEnd (user stopped dragging).
    this._moveEndListener = () => this._updatePitch();
    this.viewer.camera.moveEnd.addEventListener(
      this._moveEndListener,
    );
    // Also update continuously while tilting with buttons.
    this._changeListener = () => this._updatePitch();
    this.viewer.camera.changed.addEventListener(
      this._changeListener,
    );
  }

  private _stopTracking(): void {
    if (!this.viewer) return;
    if (this._moveEndListener) {
      this.viewer.camera.moveEnd.removeEventListener(
        this._moveEndListener,
      );
      this._moveEndListener = null;
    }
    if (this._changeListener) {
      this.viewer.camera.changed.removeEventListener(
        this._changeListener,
      );
      this._changeListener = null;
    }
  }

  private _updatePitch(): void {
    if (!this.viewer) return;
    this.pitchDeg = CesiumMath.toDegrees(
      this.viewer.camera.pitch,
    );
    this.heightM =
      this.viewer.camera.positionCartographic.height;
  }

  private _formatPitch(): string {
    return `${Math.round(this.pitchDeg)}\u00B0`;
  }

  /**
   * Format camera height in user-friendly units.
   *  < 1 km : meters
   *  < 1000 km : kilometers
   *  >= 1000 km : thousands of km
   */
  private _formatHeight(): string {
    const h = this.heightM;
    if (h < 1000) {
      return `${Math.round(h)}m`;
    }
    if (h < 10_000) {
      return `${(h / 1000).toFixed(1)}km`;
    }
    if (h < 1_000_000) {
      return `${Math.round(h / 1000)}km`;
    }
    return `${(h / 1_000_000).toFixed(1)}Mm`;
  }

  // ── Pan ───────────────────────────────────────────

  private _panAmount(): number {
    if (!this.viewer) return 0;
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
    this._updatePitch();
  }
  private _zoomOut(): void {
    this.viewer?.camera.zoomOut(
      this.viewer.camera.positionCartographic.height * 0.3,
    );
    this._updatePitch();
  }

  // ── Tilt ──────────────────────────────────────────

  private _tiltUp(): void {
    if (!this.viewer) return;
    this.viewer.camera.lookUp(CesiumMath.toRadians(10));
    this._updatePitch();
  }
  private _tiltDown(): void {
    if (!this.viewer) return;
    this.viewer.camera.lookDown(CesiumMath.toRadians(10));
    this._updatePitch();
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
    this._updatePitch();
  }
}
