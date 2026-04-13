/**
 * Area drawing tool for defining BlueSky deletion areas.
 *
 * Modes:
 *   BOX  — click two corners to define a rectangle
 *   POLY — click multiple points, double-click to finish
 *
 * After drawing, sends the shape command (BOX/POLY) and
 * then AREA <name> to activate it as the deletion area.
 * Aircraft leaving the area are removed from the sim.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

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

  private onCommand: ((cmd: string) => void) | null = null;
  private onStartDraw:
    ((cb: (lat: number, lon: number) => void,
      doneCb: () => void) => void) | null = null;
  private onStopDraw: (() => void) | null = null;

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
    button.drawing {
      color: #ffff00;
      border-color: #ffff00;
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
      return html`
        <span class="status">
          ${this.mode === 'box'
            ? `Click ${2 - this.points.length} corner${this.points.length === 1 ? '' : 's'}`
            : `Click points (dbl-click to finish) [${this.points.length}]`}
        </span>
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
      <button @click=${this._startBox}>DRAW BOX</button>
      <button @click=${this._startPoly}>DRAW POLY</button>
      <div class="sep"></div>
      <button
        class=${this.areaActive ? 'active' : ''}
        @click=${this._toggleArea}
      >${this.areaActive ? 'AREA ON' : 'AREA OFF'}</button>
    `;
  }

  /** Set command handler. */
  setCommandHandler(
    handler: (cmd: string) => void,
  ): void {
    this.onCommand = handler;
  }

  /**
   * Set callbacks for managing the globe click mode.
   *
   * startDraw: called with a point callback and a done
   *   callback when drawing begins. The host should
   *   install a click handler that calls pointCb(lat,lon)
   *   on each click, and doneCb() on double-click.
   * stopDraw: called when drawing ends or is cancelled.
   */
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
    this.onStopDraw?.();
  }

  private _addPoint(lat: number, lon: number): void {
    this.points = [...this.points, { lat, lon }];

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
      const cmd = `POLY ${name},${coords}`;
      this.onCommand?.(cmd);
    }

    // Activate as deletion area.
    setTimeout(() => {
      this.onCommand?.(`AREA ${name}`);
      this.areaActive = true;
    }, 300);

    this.mode = 'off';
    this.points = [];
    this.onStopDraw?.();
  }

  private _toggleArea(): void {
    if (this.areaActive) {
      this.onCommand?.('AREA OFF');
      this.areaActive = false;
    } else {
      const name = this.areaName || 'SIMAREA';
      this.onCommand?.(`AREA ${name}`);
      this.areaActive = true;
    }
  }
}
