/**
 * Simulation control toolbar with layer toggle buttons.
 *
 * Top bar: OP/HOLD | RESET | Speed selector
 * Layer toggles: TRAIL | ROUTE | LABEL
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../services/api';

@customElement('bluesky-toolbar')
export class BlueSkyToolbar extends LitElement {
  @state() simState = 'INIT';
  @state() dtmult = 1.0;
  @state() scenarioCategories: Record<string, { filename: string; name: string }[]> = {};
  @state() showTrails = false;
  @state() showRoutes = true;
  @state() showLabels = true;
  @state() showAirports = true;
  @state() showWaypoints = false;
  @state() showLeaders = true;
  @state() showPz = false;
  @state() is3D = true;
  @state() altScale = 10;

  static styles = css`
    :host {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: rgba(0, 0, 0, 0.85);
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 13px;
      color: #00ff00;
    }
    button {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 3px 10px;
      border-radius: 3px;
      cursor: pointer;
      font-family: inherit;
      font-size: 12px;
    }
    button:hover { background: #00ff00; color: #000; }
    button.active { background: #00ff00; color: #000; }
    button.off {
      color: #555;
      border-color: #555;
    }
    select {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 3px 4px;
      border-radius: 3px;
      font-family: inherit;
      font-size: 12px;
    }
    .sep {
      width: 1px;
      height: 18px;
      background: #444;
    }
    label { color: #888; font-size: 11px; }
    .alt-group {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    input[type=range] {
      -webkit-appearance: none;
      width: 80px;
      height: 4px;
      background: #444;
      border-radius: 2px;
      outline: none;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 12px;
      height: 12px;
      background: #00ff00;
      border-radius: 50%;
      cursor: pointer;
    }
    .alt-val {
      min-width: 30px;
      text-align: right;
      font-size: 11px;
      color: #00ff00;
    }
  `;

  render() {
    const running = this.simState === 'OP';
    return html`
      <button
        class=${running ? 'active' : ''}
        @click=${this._op}
      >OP</button>
      <button
        class=${!running && this.simState !== 'INIT'
          ? 'active' : ''}
        @click=${this._hold}
      >HOLD</button>
      <button @click=${this._reset}>RESET</button>
      <div class="sep"></div>
      <select @change=${this._onScenario}>
        <option value="" selected disabled>
          Scenario...
        </option>
        ${Object.entries(this.scenarioCategories).map(
          ([cat, items]) => html`
            <optgroup label=${cat}>
              ${items.map(
                (s) => html`
                  <option value=${s.filename}>
                    ${s.name}
                  </option>
                `,
              )}
            </optgroup>
          `,
        )}
      </select>
      <div class="sep"></div>
      <label>Speed:</label>
      <select @change=${this._onSpeed}>
        ${[0.5, 1, 2, 5, 10, 20].map(
          (v) => html`
            <option
              value=${v}
              ?selected=${this.dtmult === v}
            >${v}x</option>
          `,
        )}
      </select>
      <div class="sep"></div>
      <button
        class=${this.showTrails ? '' : 'off'}
        @click=${this._toggleTrails}
      >TRAIL</button>
      <button
        class=${this.showRoutes ? '' : 'off'}
        @click=${this._toggleRoutes}
      >ROUTE</button>
      <button
        class=${this.showLabels ? '' : 'off'}
        @click=${this._toggleLabels}
      >LABEL</button>
      <button
        class=${this.showLeaders ? '' : 'off'}
        @click=${this._toggleLeaders}
      >VEL VECTOR</button>
      <button
        class=${this.showPz ? '' : 'off'}
        @click=${this._togglePz}
      >PZ</button>
      <button
        class=${this.showAirports ? '' : 'off'}
        @click=${this._toggleAirports}
      >APT</button>
      <button
        class=${this.showWaypoints ? '' : 'off'}
        @click=${this._toggleWaypoints}
      >WPT</button>
      <div class="sep"></div>
      <button @click=${this._toggleView}>
        ${this.is3D ? '2D' : '3D'}
      </button>
      <div class="alt-group">
        <label>Alt Exag:</label>
        <input
          type="range"
          min="1" max="50" step="1"
          .value=${String(this.altScale)}
          @input=${this._onAltScale}
        />
        <span class="alt-val">${this.altScale}x</span>
      </div>
    `;
  }

  /** Called externally when SIMINFO arrives. */
  updateState(stateName: string, dtmult: number): void {
    this.simState = stateName;
    this.dtmult = dtmult;
  }

  /** Fetch categorized scenario list from backend. */
  async loadScenarios(): Promise<void> {
    try {
      const res = await fetch('/api/scenarios');
      if (res.ok) {
        this.scenarioCategories = await res.json();
      }
    } catch {
      // Non-fatal — dropdown stays empty.
    }
  }

  private _onScenario(e: Event): void {
    const sel = e.target as HTMLSelectElement;
    const filename = sel.value;
    if (!filename) return;
    this.dispatchEvent(
      new CustomEvent('load-scenario', {
        detail: { filename },
        bubbles: true,
        composed: true,
      }),
    );
    // Reset dropdown to placeholder.
    sel.selectedIndex = 0;
  }

  private async _op(): Promise<void> {
    await api.simOp();
  }

  private async _hold(): Promise<void> {
    await api.simHold();
  }

  private async _reset(): Promise<void> {
    await api.simReset();
  }

  private async _onSpeed(e: Event): Promise<void> {
    const val = parseFloat(
      (e.target as HTMLSelectElement).value,
    );
    this.dtmult = val;
    await api.simDtmult(val);
  }

  private _toggleTrails(): void {
    this.showTrails = !this.showTrails;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'trails',
          visible: this.showTrails,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleRoutes(): void {
    this.showRoutes = !this.showRoutes;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'routes',
          visible: this.showRoutes,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleLabels(): void {
    this.showLabels = !this.showLabels;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'labels',
          visible: this.showLabels,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleView(): void {
    this.is3D = !this.is3D;
    this.dispatchEvent(
      new CustomEvent('toggle-view', {
        detail: { is3D: this.is3D },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _togglePz(): void {
    this.showPz = !this.showPz;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'pz',
          visible: this.showPz,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleLeaders(): void {
    this.showLeaders = !this.showLeaders;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'leaders',
          visible: this.showLeaders,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onAltScale(e: Event): void {
    const val = parseInt(
      (e.target as HTMLInputElement).value, 10,
    );
    this.altScale = val;
    this.dispatchEvent(
      new CustomEvent('alt-scale', {
        detail: { scale: val },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleAirports(): void {
    this.showAirports = !this.showAirports;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'airports',
          visible: this.showAirports,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleWaypoints(): void {
    this.showWaypoints = !this.showWaypoints;
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: {
          layer: 'waypoints',
          visible: this.showWaypoints,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
