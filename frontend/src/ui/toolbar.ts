/**
 * Simulation toolbar with tabbed sections.
 *
 * Groups controls by purpose to reduce clutter:
 *   SIM    — OP / HOLD / RESET / Scenario / Speed
 *   LAYERS — TRAIL / ROUTE / LABEL / VEC / PZ / APT / WPT
 *   VIEW   — 2D/3D toggle, Alt Exag slider
 *
 * Tabs run along the top of the toolbar; the active tab's
 * controls are shown below.
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import * as api from '../services/api';

type TabName = 'sim' | 'layers' | 'view' | 'areas';

@customElement('bluesky-toolbar')
export class BlueSkyToolbar extends LitElement {
  @state() simState = 'INIT';
  @state() dtmult = 1.0;
  @state() scenarioCategories: Record<
    string,
    { filename: string; name: string }[]
  > = {};
  @state() showTrails = false;
  @state() showRoutes = true;
  @state() showLabels = true;
  @state() showAirports = true;
  @state() showWaypoints = false;
  @state() showLeaders = true;
  @state() showPz = false;
  @state() is3D = true;
  @state() altScale = 10;
  @state() activeTab: TabName = 'sim';

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.85);
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 13px;
      color: #00ff00;
      border-radius: 4px;
      overflow: hidden;
    }

    /* Tab strip */
    .tabs {
      display: flex;
      background: #0a0a0a;
      border-bottom: 1px solid #222;
    }
    .tab {
      padding: 3px 12px;
      font-size: 10px;
      color: #888;
      cursor: pointer;
      border-right: 1px solid #1a1a1a;
      user-select: none;
      letter-spacing: 0.5px;
    }
    .tab:hover {
      color: #00ff00;
      background: #111;
    }
    .tab.active {
      color: #00ff00;
      background: rgba(0, 0, 0, 0.85);
      border-bottom: 1px solid #00ff00;
      margin-bottom: -1px;
    }

    /* Control row */
    .controls {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      min-height: 28px;
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
      width: 120px;
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
    return html`
      <div class="tabs">
        ${this._tab('sim', 'SIM')}
        ${this._tab('layers', 'LAYERS')}
        ${this._tab('view', 'VIEW')}
        ${this._tab('areas', 'AREAS')}
      </div>
      <div class="controls">
        ${this._renderActiveTab()}
      </div>
    `;
  }

  /** Called externally when SIMINFO arrives. */
  updateState(stateName: string, dtmult: number): void {
    this.simState = stateName;
    this.dtmult = dtmult;
  }

  /** Sync button state with actual backend flags. */
  syncBackendState(flags: {
    trails: boolean;
    area: boolean;
  }): void {
    if (this.showTrails !== flags.trails) {
      this.showTrails = flags.trails;
      this.dispatchEvent(
        new CustomEvent('toggle-layer', {
          detail: {
            layer: 'trails-display',
            visible: flags.trails,
          },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  /** Fetch categorized scenario list. */
  async loadScenarios(): Promise<void> {
    try {
      const res = await fetch('/api/scenarios');
      if (res.ok) {
        this.scenarioCategories = await res.json();
      }
    } catch {
      // Non-fatal.
    }
  }

  // ── Tab rendering ─────────────────────────────────

  private _tab(id: TabName, label: string) {
    return html`
      <div
        class="tab ${this.activeTab === id
          ? 'active' : ''}"
        @click=${() => this._setTab(id)}
      >${label}</div>
    `;
  }

  private _setTab(id: TabName): void {
    this.activeTab = id;
    this.dispatchEvent(
      new CustomEvent('tab-changed', {
        detail: { tab: id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _renderActiveTab() {
    switch (this.activeTab) {
      case 'sim':    return this._renderSim();
      case 'layers': return this._renderLayers();
      case 'view':   return this._renderView();
      case 'areas':  return this._renderAreasHint();
    }
  }

  private _renderAreasHint() {
    // The actual area-tool component lives outside the
    // toolbar (so it can draw on the viewer).  When this
    // tab is active, main.ts shows the area-tool bar.
    return html`
      <label style="color:#888; font-size:11px;">
        Use the area tool bar below to draw and manage
        deletion areas.
      </label>
    `;
  }

  private _renderSim() {
    const running = this.simState === 'OP';
    const held = !running && this.simState !== 'INIT';
    return html`
      <button
        class=${running ? 'active' : ''}
        @click=${this._op}
      >OP</button>
      <button
        class=${held ? 'active' : ''}
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
    `;
  }

  private _renderLayers() {
    return html`
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
      <div class="sep"></div>
      <button
        class=${this.showAirports ? '' : 'off'}
        @click=${this._toggleAirports}
      >APT</button>
      <button
        class=${this.showWaypoints ? '' : 'off'}
        @click=${this._toggleWaypoints}
      >WPT</button>
    `;
  }

  private _renderView() {
    return html`
      <button @click=${this._toggleView}>
        ${this.is3D ? '2D' : '3D'}
      </button>
      <div class="sep"></div>
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

  // ── Event handlers ────────────────────────────────

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
    this.dispatchEvent(
      new CustomEvent('sim-reset', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private async _onSpeed(e: Event): Promise<void> {
    const val = parseFloat(
      (e.target as HTMLSelectElement).value,
    );
    this.dtmult = val;
    await api.simDtmult(val);
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
    this._dispatchLayer('pz', this.showPz);
  }

  private _toggleLeaders(): void {
    this.showLeaders = !this.showLeaders;
    this._dispatchLayer('leaders', this.showLeaders);
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

  private _toggleTrails(): void {
    this.showTrails = !this.showTrails;
    this._dispatchLayer('trails', this.showTrails);
  }

  private _toggleRoutes(): void {
    this.showRoutes = !this.showRoutes;
    this._dispatchLayer('routes', this.showRoutes);
  }

  private _toggleLabels(): void {
    this.showLabels = !this.showLabels;
    this._dispatchLayer('labels', this.showLabels);
  }

  private _toggleAirports(): void {
    this.showAirports = !this.showAirports;
    this._dispatchLayer('airports', this.showAirports);
  }

  private _toggleWaypoints(): void {
    this.showWaypoints = !this.showWaypoints;
    this._dispatchLayer('waypoints', this.showWaypoints);
  }

  private _dispatchLayer(
    layer: string,
    visible: boolean,
  ): void {
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: { layer, visible },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
