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
import {
  getUnits, speedUnitLabel, onUnitsChange,
} from '../services/units';
import type { UnitSystem } from '../types';

type TabName =
  | 'sim'
  | 'layers'
  | 'view'
  | 'areas'
  | 'wind'
  | 'cameras'
  | 'wx'
  | 'notam';

type CamMode = 'chase' | 'pilot' | 'starboard' | 'port';

const CAM_MODE_LABELS: Record<CamMode, string> = {
  chase: 'CHASE',
  pilot: 'PILOT',
  starboard: 'STARBOARD',
  port: 'PORT',
};

const CAM_MODE_DESCRIPTIONS: Record<CamMode, string> = {
  chase: '3rd person — behind and above',
  pilot: '1st person — cockpit forward',
  starboard: 'Window view — right side',
  port: 'Window view — left side',
};

export interface ImageryChoice {
  id: string;
  label: string;
  disabled: boolean;
}

export interface TerrainChoice {
  id: string;
  label: string;
  disabled: boolean;
}

@customElement('bluesky-toolbar')
export class BlueSkyToolbar extends LitElement {
  @state() simState = 'INIT';
  @state() dtmult = 1.0;
  @state() currentScenario = '';
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
  @state() showWind = true;
  @state() showWindField = false;
  @state() showMetars = false;
  @state() showPireps = false;
  @state() showSigmets = false;
  @state() showGairmets = false;
  @state() showRadar = false;
  @state() showSatellite = false;
  @state() showMrms = false;
  @state() showGoesVis = false;
  @state() showSpcOutlook = false;
  @state() showWwa = false;
  @state() showNdfdTemp = false;
  @state() showSmoke = false;
  @state() showTfrs = false;
  @state() showSuaP = false;   // Prohibited
  @state() showSuaR = false;   // Restricted
  @state() showSuaW = false;   // Warning
  @state() showSuaA = false;   // Alert
  @state() showSuaM = false;   // MOA
  @state() showClassB = false;
  @state() showClassC = false;
  @state() showClassD = false;
  // Class E split by ARINC LOCAL_TYPE so users can
  // toggle the CONUS-blanket E5 separately from
  // the tighter E2/E3/E4 terminal-area types.
  @state() showClassE2 = false;
  @state() showClassE3 = false;
  @state() showClassE4 = false;
  @state() showClassE5 = false;
  @state() showClassE6 = false;
  @state() showClassEOther = false;
  // FAA aeronautical chart overlays (ChartBundle).
  @state() showLiveTraffic = false;
  @state() showInterpolation = true;
  @state() showChartSectional = false;
  @state() showChartTac = false;
  @state() showChartHelo = false;
  @state() showChartIfrLow = false;
  @state() showChartIfrHigh = false;
  @state() windFieldAltFt = 35000;
  @state() windFieldSpacingDeg = 1.0;
  @state() is3D = true;
  @state() altScale = 2;
  @state() activeTab: TabName = 'sim';
  @state() imageryOptions: ImageryChoice[] = [];
  @state() terrainOptions: TerrainChoice[] = [];
  @state() currentImagery = '';
  @state() currentTerrain = 'flat';
  @state() ionTokenSet = false;
  @state() showTokenInput = false;
  @state() windPoints: any[] = [];
  @state() windPickMode = false;
  @state() autoImportMetars = false;
  @state() asasMethod = 'OFF';
  @state() asasMethods: string[] = ['OFF'];
  @state() resoMethod = 'OFF';
  @state() resoMethods: string[] = ['OFF'];
  @state() resoPluginsAvailable: string[] = [];
  @state() aircraftIds: string[] = [];
  @state() camTrackAcid: string | null = null;
  @state() camTrackMode: CamMode = 'chase';
  @state() camSelectAcid: string = '';
  @state() private unitSystem: UnitSystem = getUnits();
  private unitsUnsub: (() => void) | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this.unitsUnsub = onUnitsChange((u) => {
      this.unitSystem = u;
      this.refreshWindInfo();
    });
  }

  disconnectedCallback(): void {
    this.unitsUnsub?.();
    super.disconnectedCallback();
  }

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
    .mode-select {
      background: #1a0a2a;
      color: #cc88ff;
      border: 1px solid #442266;
      border-radius: 3px;
      font-family: inherit;
      font-size: 11px;
      font-weight: bold;
      padding: 2px 6px;
      cursor: pointer;
      margin-right: 4px;
    }
    .mode-select:hover {
      border-color: #8844cc;
      color: #ee99ff;
    }
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
    .wx-group-label {
      color: #888;
      font-size: 11px;
      margin-right: 2px;
    }
    .wx-chip {
      position: relative;
      padding: 3px 8px 3px 14px;
      border-radius: 3px;
      font-size: 11px;
      cursor: pointer;
      font-family: inherit;
    }
    /* Left color bar — always visible, indicates
       which on-map color corresponds to this toggle. */
    .wx-chip::before {
      content: '';
      position: absolute;
      left: 3px;
      top: 50%;
      transform: translateY(-50%);
      width: 6px;
      height: 14px;
      border-radius: 2px;
      background: var(--swatch);
      border: 1px solid #444;
    }
    .wx-chip.on {
      background: #00ff00;
      color: #000;
      border: 1px solid #00ff00;
    }
    .wx-chip.off {
      background: #222;
      color: #aaa;
      border: 1px solid #444;
    }
    .wx-chip.off:hover {
      color: #fff;
      border-color: #888;
    }
  `;

  /** Current UI mode (Controller / Cockpit / Ops / Observer). */
  @state() currentMode: string = 'controller';

  render() {
    return html`
      <div class="tabs">
        <select class="mode-select"
                title="UI mode — changes which panels + layers are on by default"
                .value=${this.currentMode}
                @change=${this._onModeChange}>
          <option value="controller">Controller</option>
          <option value="cockpit">Cockpit</option>
          <option value="ops">Ops</option>
          <option value="observer">Observer</option>
        </select>
        ${this._tab('sim', 'SIM')}
        ${this._tab('areas', 'AREAS')}
        ${this._tab('wind', 'WIND')}
        ${this._tab('cameras', 'CAMERAS')}
      </div>
      <div class="controls">
        ${this._renderActiveTab()}
      </div>
    `;
  }

  private _onModeChange(e: Event): void {
    const id = (e.target as HTMLSelectElement).value;
    this.currentMode = id;
    this.dispatchEvent(new CustomEvent('mode-change', {
      detail: { mode: id },
      bubbles: true, composed: true,
    }));
  }

  /** Called externally when SIMINFO arrives. */
  updateState(
    stateName: string,
    dtmult: number,
    scenname: string = '',
  ): void {
    this.simState = stateName;
    this.dtmult = dtmult;
    this.currentScenario = scenname;
  }

  /** Sync button state with actual backend flags. */
  syncBackendState(flags: {
    trails: boolean;
    area: boolean;
    asasMethod?: string;
    asasMethods?: string[];
    resoMethod?: string;
    resoMethods?: string[];
    resoPluginsAvailable?: string[];
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
    if (flags.asasMethod !== undefined) {
      this.asasMethod = flags.asasMethod;
    }
    if (flags.asasMethods !== undefined) {
      this.asasMethods = flags.asasMethods;
    }
    if (flags.resoMethod !== undefined) {
      this.resoMethod = flags.resoMethod;
    }
    if (flags.resoMethods !== undefined) {
      this.resoMethods = flags.resoMethods;
    }
    if (flags.resoPluginsAvailable !== undefined) {
      this.resoPluginsAvailable = flags.resoPluginsAvailable;
    }
  }

  /** Populate imagery/terrain options from the viewer. */
  setImageryOptions(
    options: ImageryChoice[],
    current: string,
  ): void {
    this.imageryOptions = options;
    this.currentImagery = current;
  }

  setTerrainOptions(
    options: TerrainChoice[],
    current: string,
  ): void {
    this.terrainOptions = options;
    this.currentTerrain = current;
  }

  setIonTokenStatus(tokenSet: boolean): void {
    this.ionTokenSet = tokenSet;
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
    if (id === 'wind') {
      this.refreshWindInfo();
    }
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
      case 'sim':     return this._renderSim();
      case 'areas':   return this._renderAreasHint();
      case 'wind':    return this._renderWind();
      case 'cameras': return this._renderCameras();
    }
  }

  /** Refresh the list of defined wind points. */
  async refreshWindInfo(): Promise<void> {
    try {
      const res = await fetch('/api/wind/points').then(
        (r) => r.json(),
      );
      this.windPoints = res.points || [];
      // Notify listeners (main.ts) so the barbs update.
      this.dispatchEvent(
        new CustomEvent('wind-points-updated', {
          detail: { points: this.windPoints },
          bubbles: true,
          composed: true,
        }),
      );
    } catch {
      this.windPoints = [];
    }
  }

  private _renderWind() {
    const pickLabel = this.windPickMode
      ? '[click on map]'
      : '+ Add on map';
    const nPts = this.windPoints.length;
    return html`
      <button
        class=${this.windPickMode ? 'active' : ''}
        @click=${this._toggleWindPick}
        title="Click, then pick a spot on the globe to
          add a new wind point"
      >${pickLabel}</button>
      <label>Points:</label>
      <select
        @change=${this._onWindPointSelect}
        style="min-width: 180px"
        title="Open an existing point in the detail panel"
      >
        <option value="" selected>
          ${nPts === 0
            ? '— none defined —'
            : `${nPts} defined`}
        </option>
        ${this.windPoints.map((p, i) => html`
          <option value=${i}>
            ${p.lat.toFixed(2)}, ${p.lon.toFixed(2)}
            ${p.altitude_ft === null
              ? '(all alts)'
              : ` @FL${Math.round(p.altitude_ft / 100)}`}
            — ${Math.round(p.direction_deg)}°/${
              Math.round(p.speed)} ${p.unit_label}
          </option>
        `)}
      </select>
      <button @click=${this._clearWind}
        ?disabled=${nPts === 0}
      >CLEAR ALL</button>
      <div class="sep"></div>
      <label title="Show interpolated wind field as a
        grid of barbs at the selected altitude">
        <input type="checkbox"
          .checked=${this.showWindField}
          @change=${this._onWindFieldCheckbox}
          style="vertical-align: middle;"
        /> Field
      </label>
      <label>Alt:</label>
      <select
        @change=${this._onWindFieldAlt}
        ?disabled=${!this.showWindField}
        style="min-width: 70px"
      >
        ${[0, 5000, 10000, 15000, 20000, 25000,
          30000, 35000, 40000, 45000].map((ft) => html`
          <option
            value=${ft}
            ?selected=${this.windFieldAltFt === ft}
          >${ft === 0 ? 'SFC'
            : `FL${String(ft / 100).padStart(3, '0')}`
          }</option>
        `)}
      </select>
      <label>Grid:</label>
      <select
        @change=${this._onWindFieldSpacing}
        ?disabled=${!this.showWindField}
        style="min-width: 60px"
      >
        ${[0.25, 0.5, 1.0, 2.0, 5.0].map((v) => html`
          <option
            value=${v}
            ?selected=${this.windFieldSpacingDeg === v}
          >${v}°</option>
        `)}
      </select>
      <div class="sep"></div>
      <label
        title="When on, surface winds from every
          currently-loaded METAR station feed the
          wind field automatically.  Imported points
          refresh with METARs (every ~3 min) and do
          not appear as individual barbs — they only
          influence the interpolated Field layer."
      >
        <input type="checkbox"
          .checked=${this.autoImportMetars}
          @change=${this._toggleAutoImportMetars}
          style="vertical-align: middle;"
        />
        Auto-import METAR winds
      </label>
    `;
  }

  /** Update the aircraft id list shown in the CAMERAS tab. */
  setAircraftIds(ids: string[]): void {
    this.aircraftIds = ids;
    // If the currently-selected aircraft in the camera
    // picker disappeared, clear the picker.
    if (
      this.camSelectAcid
      && !ids.includes(this.camSelectAcid)
    ) {
      this.camSelectAcid = '';
    }
  }

  /** Sync the CAMERAS tab with the active tracking state. */
  setCameraState(acid: string | null, mode: CamMode): void {
    this.camTrackAcid = acid;
    this.camTrackMode = mode;
    // When tracking is active, surface the target in the
    // picker so the user can easily pick a different
    // mode against the same aircraft.
    if (acid) this.camSelectAcid = acid;
  }

  private _renderCameras() {
    const activeLabel = this.camTrackAcid
      ? `Tracking ${this.camTrackAcid} — ${
        CAM_MODE_LABELS[this.camTrackMode]
      }`
      : 'Free camera';
    const pickerAcid = this.camSelectAcid
      || this.camTrackAcid
      || '';
    return html`
      <label>Aircraft:</label>
      <select
        @change=${this._onCamAircraftChange}
        style="min-width: 90px"
      >
        <option value=""
          ?selected=${!pickerAcid}
        >— select —</option>
        ${this.aircraftIds.map(
          (id) => html`
            <option
              value=${id}
              ?selected=${pickerAcid === id}
            >${id}</option>
          `,
        )}
      </select>
      <div class="sep"></div>
      ${(Object.keys(CAM_MODE_LABELS) as CamMode[]).map(
        (m) => html`
          <button
            class=${
              this.camTrackAcid
              && this.camTrackMode === m
                ? 'active'
                : ''
            }
            title=${CAM_MODE_DESCRIPTIONS[m]}
            @click=${() => this._camSet(m)}
          >${CAM_MODE_LABELS[m]}</button>
        `,
      )}
      <div class="sep"></div>
      <button @click=${this._camFree}>FREE</button>
      <div class="sep"></div>
      <label style="color:#888; font-size:11px;">
        ${activeLabel}
      </label>
    `;
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
        <option value=""
          ?selected=${!this.currentScenario}
          disabled
        >${this.currentScenario
          ? '\u2014 select scenario \u2014'
          : 'Scenario...'}</option>
        ${Object.entries(this.scenarioCategories).map(
          ([cat, items]) => html`
            <optgroup label=${cat}>
              ${items.map(
                (s) => html`
                  <option
                    value=${s.filename}
                    ?selected=${
                      s.name === this.currentScenario
                    }
                  >${s.name}</option>
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
      <button @click=${this._openScenarioEditor}>
        EDIT SCENARIO
      </button>
      <div class="sep"></div>
      <button
        class=${this.asasMethod === 'OFF' ? 'off' : 'active'}
        title=${
          this.asasMethod === 'OFF'
            ? 'Conflict detection off'
            : `Conflict detection: ${this.asasMethod}`
        }
        @click=${this._toggleAsas}
      >ASAS ${this.asasMethod === 'OFF' ? 'OFF' : 'ON'}</button>
      <label>RESO:</label>
      <select @change=${this._onResoChange}>
        ${this.resoMethods.map(
          (m) => html`
            <option
              value=${m}
              ?selected=${this.resoMethod === m}
            >${m}</option>
          `,
        )}
      </select>
      ${this.resoPluginsAvailable.length > 0 ? html`
        <select
          @change=${this._onLoadResoPlugin}
          title="Load a RESO plugin"
        >
          <option value="" selected>+ Load plugin…</option>
          ${this.resoPluginsAvailable.map(
            (p) => html`<option value=${p}>${p}</option>`,
          )}
        </select>
      ` : ''}
    `;
  }

  private _openScenarioEditor(): void {
    this.dispatchEvent(
      new CustomEvent('open-scenario-editor', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _renderLayers() {
    return html`
      <button
        @click=${this._openOpacityPanel}
        title="Open layer-opacity sliders"
      >🌗 OPACITY</button>
      <span class="sep"></span>
      <button
        class=${this.showLiveTraffic ? '' : 'off'}
        @click=${this._toggleLiveTraffic}
        title="Live ADS-B traffic from OpenSky Network"
        style="${this.showLiveTraffic ? 'background:#ffa000;color:#000;font-weight:bold' : ''}"
      >LIVE</button>
      <button
        class=${this.showInterpolation ? '' : 'off'}
        @click=${this._toggleInterpolation}
        title="Dead-reckoning interpolation for live/replay traffic"
      >INTERP</button>
      <span class="sep"></span>
      <button
        class=${this.showChartSectional ? '' : 'off'}
        @click=${this._toggleChartSectional}
        title="VFR Sectional chart overlay"
      >SECT</button>
      <button
        class=${this.showChartTac ? '' : 'off'}
        @click=${this._toggleChartTac}
        title="Terminal Area Chart overlay"
      >TAC</button>
      <button
        class=${this.showChartIfrLow ? '' : 'off'}
        @click=${this._toggleChartIfrLow}
        title="IFR Low Enroute chart overlay"
      >IFR-L</button>
      <button
        class=${this.showChartIfrHigh ? '' : 'off'}
        @click=${this._toggleChartIfrHigh}
        title="IFR High Enroute chart overlay"
      >IFR-H</button>
      <span class="sep"></span>
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
        class=${this.showWind ? '' : 'off'}
        @click=${this._toggleWind}
        title="Toggle wind barbs for user-defined points
          (visibility only — does not change the wind's
          effect on aircraft)"
      >WIND BARBS</button>
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

  private _renderWx() {
    // Grouped button-style toggles.  Each button
    // shows:
    //   • A left color bar matching the layer's
    //     on-map color, so the user ties the button to
    //     what they'll see.
    //   • "On" state = filled background; "off" = dim.
    const chip = (
      on: boolean,
      label: string,
      color: string,
      title: string,
      onClick: () => void,
    ) => html`
      <button
        class="wx-chip ${on ? 'on' : 'off'}"
        title=${title}
        @click=${onClick}
        style="--swatch: ${color};"
      >${label}</button>
    `;
    return html`
      <label class="wx-group-label">Obs:</label>
      ${chip(
        this.showMetars,
        'METARs',
        'linear-gradient(90deg,\
          #3fbf3f 0%, #3fbf3f 25%,\
          #4080ff 25%, #4080ff 50%,\
          #ff4040 50%, #ff4040 75%,\
          #ff40c0 75%, #ff40c0 100%)',
        'METAR surface observations — colored dots per '
        + 'station (VFR/MVFR/IFR/LIFR)',
        () => this._toggleMetars(),
      )}
      ${chip(
        this.showPireps,
        'PIREPs',
        '#A06000',
        'Pilot reports — 3D-positioned points at the '
        + 'reported flight level, colored by hazard '
        + 'keyword (turb/icing/convective/wind-shear)',
        () => this._togglePireps(),
      )}
      <div class="sep"></div>
      <label class="wx-group-label">Advisories:</label>
      ${chip(
        this.showSigmets,
        'SIGMETs',
        '#800000',
        'SIGMETs — significant meteorological '
        + 'advisories (convective, turb, icing)',
        () => this._toggleSigmets(),
      )}
      ${chip(
        this.showGairmets,
        'G-AIRMETs',
        '#6666ff',
        'Graphical AIRMETs — the modern AWC AIRMET '
        + 'product.  Forecaster-drawn polygons, '
        + 'sliced into 3-hour forecast snapshots.',
        () => this._toggleGairmets(),
      )}
      <div class="sep"></div>
      <label class="wx-group-label">Imagery:</label>
      ${chip(
        this.showRadar,
        'Radar',
        '#00cc66',
        'NEXRAD base reflectivity mosaic '
        + '(IEM / Iowa State University).  Shows '
        + 'current precipitation across CONUS.',
        () => this._toggleRadar(),
      )}
      ${chip(
        this.showSatellite,
        'Satellite IR',
        '#cccccc',
        'GOES-East ABI Band 13 clean infrared '
        + '(NASA GIBS).  Shows cloud-top '
        + 'temperatures — white/bright = cold high '
        + 'clouds.',
        () => this._toggleSatellite(),
      )}
      ${chip(
        this.showMrms,
        'MRMS',
        '#00ff88',
        'NWS Multi-Radar Multi-Sensor — higher-res '
        + 'composite radar from all WSR-88D radars.',
        () => this._toggleWxTile('mrms'),
      )}
      ${chip(
        this.showGoesVis,
        'GOES Vis',
        '#eeeeaa',
        'GOES visible satellite — daytime only.  '
        + 'Shows cloud tops in visible light.',
        () => this._toggleWxTile('goes-vis'),
      )}
      ${chip(
        this.showSpcOutlook,
        'SPC Outlook',
        '#ff8800',
        'NWS Storm Prediction Center convective '
        + 'outlook — risk areas for severe weather.',
        () => this._toggleWxTile('spc-outlook'),
      )}
      ${chip(
        this.showWwa,
        'W/W/A',
        '#ff3030',
        'NWS Watches, Warnings, and Advisories — '
        + 'active severe weather alerts.',
        () => this._toggleWxTile('wwa'),
      )}
      ${chip(
        this.showNdfdTemp,
        'Temp Fcst',
        '#ff6600',
        'NWS NDFD temperature forecast grid.',
        () => this._toggleWxTile('ndfd-temp'),
      )}
      ${chip(
        this.showSmoke,
        'Smoke',
        '#996633',
        'NWS surface smoke analysis (1-hr avg).',
        () => this._toggleWxTile('smoke'),
      )}
      <div class="sep"></div>
      <button @click=${this._openWeatherPanel}
        title="Open the weather panel — full list of
          stations and advisories with decoded details"
      >OPEN PANEL</button>
      <div class="sep"></div>
      <label style="color:#888; font-size:11px;">
        Data: aviationweather.gov
      </label>
    `;
  }

  private _openWeatherPanel(): void {
    this.dispatchEvent(
      new CustomEvent('open-weather-panel', {
        bubbles: true, composed: true,
      }),
    );
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
      <div class="sep"></div>
      <label>Imagery:</label>
      <select
        .value=${this.currentImagery}
        @change=${this._onImageryChange}
      >
        ${this.imageryOptions.map(
          (o) => html`
            <option
              value=${o.id}
              ?disabled=${o.disabled}
              ?selected=${this.currentImagery === o.id}
            >${o.label}${o.disabled
              ? ' (Ion required)' : ''}</option>
          `,
        )}
      </select>
      <label>Terrain:</label>
      <select
        .value=${this.currentTerrain}
        @change=${this._onTerrainChange}
      >
        ${this.terrainOptions.map(
          (o) => html`
            <option
              value=${o.id}
              ?disabled=${o.disabled}
              ?selected=${this.currentTerrain === o.id}
            >${o.label}${o.disabled
              ? ' (Ion required)' : ''}</option>
          `,
        )}
      </select>
      <button @click=${this._toggleTokenInput}>
        ${this.ionTokenSet ? 'Ion \u2713' : 'Set Ion Token'}
      </button>
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
    // Don't reset selectedIndex — the dropdown will
    // sync to the loaded scenario via SIMINFO updates.
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

  private _toggleWind(): void {
    this.showWind = !this.showWind;
    this._dispatchLayer('wind-barbs', this.showWind);
  }

  private _toggleMetars(e?: Event): void {
    // Works for both direct button clicks (no event) and
    // checkbox change events (use the input's state).
    if (e && e.target instanceof HTMLInputElement) {
      this.showMetars = e.target.checked;
    } else {
      this.showMetars = !this.showMetars;
    }
    this._dispatchLayer('metars', this.showMetars);
  }

  private _togglePireps(): void {
    this.showPireps = !this.showPireps;
    this._dispatchLayer('pireps', this.showPireps);
  }

  private _toggleSigmets(e?: Event): void {
    if (e && e.target instanceof HTMLInputElement) {
      this.showSigmets = e.target.checked;
    } else {
      this.showSigmets = !this.showSigmets;
    }
    this._dispatchLayer('sigmets', this.showSigmets);
  }

  private _toggleGairmets(e?: Event): void {
    if (e && e.target instanceof HTMLInputElement) {
      this.showGairmets = e.target.checked;
    } else {
      this.showGairmets = !this.showGairmets;
    }
    this._dispatchLayer('gairmets', this.showGairmets);
  }

  private _toggleRadar(): void {
    this.showRadar = !this.showRadar;
    this._dispatchLayer('radar', this.showRadar);
  }

  private _toggleSatellite(): void {
    this.showSatellite = !this.showSatellite;
    this._dispatchLayer('satellite', this.showSatellite);
  }

  private _toggleWxTile(id: string): void {
    const key = `wx-${id}`;
    const stateMap: Record<string, keyof BlueSkyToolbar> = {
      'mrms': 'showMrms',
      'goes-vis': 'showGoesVis',
      'spc-outlook': 'showSpcOutlook',
      'wwa': 'showWwa',
      'ndfd-temp': 'showNdfdTemp',
      'smoke': 'showSmoke',
    };
    const prop = stateMap[id];
    if (prop) {
      (this as any)[prop] = !(this as any)[prop];
      this._dispatchLayer(key, (this as any)[prop]);
    }
  }

  private _renderNotam() {
    const chip = (
      on: boolean,
      label: string,
      color: string,
      title: string,
      onClick: () => void,
    ) => html`
      <button
        class="wx-chip ${on ? 'on' : 'off'}"
        title=${title}
        @click=${onClick}
        style="--swatch: ${color};"
      >${label}</button>
    `;
    return html`
      <label class="wx-group-label">TFR:</label>
      ${chip(
        this.showTfrs,
        'TFRs',
        '#ff3030',
        'Temporary Flight Restrictions from FAA '
        + '(tfr.faa.gov).  Volume rendered as a red '
        + 'cylinder — altitude band is not in the '
        + 'feed, so full column shown.',
        () => this._toggleTfrs(),
      )}
      <div class="sep"></div>
      <label class="wx-group-label">SUA:</label>
      ${chip(
        this.showSuaP,
        'Prohibited',
        '#ff2020',
        'Prohibited airspace (P-areas) — no entry '
        + 'without FAA approval.',
        () => this._toggleSuaP(),
      )}
      ${chip(
        this.showSuaR,
        'Restricted',
        '#cc0080',
        'Restricted areas (R-areas) — entry '
        + 'coordinated with controlling agency.',
        () => this._toggleSuaR(),
      )}
      ${chip(
        this.showSuaW,
        'Warning',
        '#ff8800',
        'Warning areas (W) — offshore hazards to '
        + 'non-participating aircraft.',
        () => this._toggleSuaW(),
      )}
      ${chip(
        this.showSuaA,
        'Alert',
        '#e0c800',
        'Alert areas (A) — high density of '
        + 'pilot training or unusual activity.',
        () => this._toggleSuaA(),
      )}
      ${chip(
        this.showSuaM,
        'MOA',
        '#a020d0',
        'Military Operations Areas (M) — '
        + 'scheduled military activity.',
        () => this._toggleSuaM(),
      )}
      <div class="sep"></div>
      <label class="wx-group-label">Class:</label>
      ${chip(
        this.showClassB,
        'Class B',
        '#0066ff',
        'Class B airspace — inverted wedding cake '
        + 'around major airports (ATL, JFK, LAX…).  '
        + 'Each shelf rendered as a separate volume '
        + 'with its published altitude band.',
        () => this._toggleClassB(),
      )}
      ${chip(
        this.showClassC,
        'Class C',
        '#ff0080',
        'Class C airspace — two-tier volumes around '
        + 'medium-size towered airports.',
        () => this._toggleClassC(),
      )}
      ${chip(
        this.showClassD,
        'Class D',
        '#66aaff',
        'Class D airspace — smaller cylinders '
        + 'around towered fields, surface to ~2500 '
        + 'ft AGL.',
        () => this._toggleClassD(),
      )}
      <div class="sep"></div>
      <label class="wx-group-label">Class E:</label>
      ${chip(
        this.showClassE2,
        'E2',
        '#ff60c0',
        'Class E2 — surface extension at non-towered '
        + 'airports with instrument approaches.',
        () => this._toggleClassE2(),
      )}
      ${chip(
        this.showClassE3,
        'E3',
        '#dc50dc',
        'Class E3 — airspace surrounding a navaid.',
        () => this._toggleClassE3(),
      )}
      ${chip(
        this.showClassE4,
        'E4',
        '#ff80dc',
        'Class E4 — transition area (700-ft AGL) '
        + 'around towered airports.',
        () => this._toggleClassE4(),
      )}
      ${chip(
        this.showClassE5,
        'E5',
        '#ff80c0',
        'Class E5 — 1200-ft AGL CONUS coverage. '
        + '~2800 shelves; default off because it '
        + 'paints the entire continental US.',
        () => this._toggleClassE5(),
      )}
      ${chip(
        this.showClassE6,
        'E6',
        '#c864c8',
        'Class E6 — federal airway corridor. '
        + 'Overlaps the airway-line layer; off by '
        + 'default.',
        () => this._toggleClassE6(),
      )}
      ${chip(
        this.showClassEOther,
        'E other',
        '#cc88cc',
        'Class E shelves with no specific LOCAL_TYPE.',
        () => this._toggleClassEOther(),
      )}
      <div class="sep"></div>
      <label style="color:#888; font-size:11px;">
        Data: FAA (tfr.faa.gov, sua.faa.gov, services6.arcgis.com)
      </label>
    `;
  }

  private _toggleTfrs(): void {
    this.showTfrs = !this.showTfrs;
    this._dispatchLayer('tfrs', this.showTfrs);
  }
  private _toggleSuaP(): void {
    this.showSuaP = !this.showSuaP;
    this._dispatchLayer('sua-p', this.showSuaP);
  }
  private _toggleSuaR(): void {
    this.showSuaR = !this.showSuaR;
    this._dispatchLayer('sua-r', this.showSuaR);
  }
  private _toggleSuaW(): void {
    this.showSuaW = !this.showSuaW;
    this._dispatchLayer('sua-w', this.showSuaW);
  }
  private _toggleSuaA(): void {
    this.showSuaA = !this.showSuaA;
    this._dispatchLayer('sua-a', this.showSuaA);
  }
  private _toggleSuaM(): void {
    this.showSuaM = !this.showSuaM;
    this._dispatchLayer('sua-m', this.showSuaM);
  }
  private _toggleClassB(): void {
    this.showClassB = !this.showClassB;
    this._dispatchLayer('class-b', this.showClassB);
  }
  private _toggleClassC(): void {
    this.showClassC = !this.showClassC;
    this._dispatchLayer('class-c', this.showClassC);
  }
  private _toggleClassD(): void {
    this.showClassD = !this.showClassD;
    this._dispatchLayer('class-d', this.showClassD);
  }
  private _toggleClassE2(): void {
    this.showClassE2 = !this.showClassE2;
    this._dispatchLayer('class-e2', this.showClassE2);
  }
  private _toggleClassE3(): void {
    this.showClassE3 = !this.showClassE3;
    this._dispatchLayer('class-e3', this.showClassE3);
  }
  private _toggleClassE4(): void {
    this.showClassE4 = !this.showClassE4;
    this._dispatchLayer('class-e4', this.showClassE4);
  }
  private _toggleClassE5(): void {
    this.showClassE5 = !this.showClassE5;
    this._dispatchLayer('class-e5', this.showClassE5);
  }
  private _toggleClassE6(): void {
    this.showClassE6 = !this.showClassE6;
    this._dispatchLayer('class-e6', this.showClassE6);
  }
  private _toggleClassEOther(): void {
    this.showClassEOther = !this.showClassEOther;
    this._dispatchLayer(
      'class-e-other', this.showClassEOther,
    );
  }


  private _toggleLeaders(): void {
    this.showLeaders = !this.showLeaders;
    this._dispatchLayer('leaders', this.showLeaders);
  }

  private _onImageryChange(e: Event): void {
    const id = (e.target as HTMLSelectElement).value;
    this.currentImagery = id;
    this.dispatchEvent(
      new CustomEvent('imagery-change', {
        detail: { id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onTerrainChange(e: Event): void {
    const id = (e.target as HTMLSelectElement).value;
    this.currentTerrain = id;
    this.dispatchEvent(
      new CustomEvent('terrain-change', {
        detail: { id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleTokenInput(): void {
    const current = this.ionTokenSet
      ? '(token is set)'
      : '';
    const val = prompt(
      'Cesium Ion access token:\n\n'
        + 'Get one free at https://ion.cesium.com/signup\n'
        + 'Leave empty to clear.',
      current,
    );
    if (val === null) return;  // cancelled
    const cleaned = val === '(token is set)'
      ? this.ionTokenSet ? '' : ''
      : val.trim();
    this.dispatchEvent(
      new CustomEvent('ion-token-set', {
        detail: { token: cleaned },
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

  private _toggleTrails(): void {
    this.showTrails = !this.showTrails;
    this._dispatchLayer('trails', this.showTrails);
  }

  private _toggleLiveTraffic(): void {
    this.showLiveTraffic = !this.showLiveTraffic;
    this._dispatchLayer('live-traffic', this.showLiveTraffic);
  }

  private _toggleInterpolation(): void {
    this.showInterpolation = !this.showInterpolation;
    this._dispatchLayer('interpolation', this.showInterpolation);
  }

  private _openOpacityPanel(): void {
    this.dispatchEvent(new CustomEvent(
      'open-opacity-panel',
      { bubbles: true, composed: true },
    ));
  }

  private _toggleChartSectional(): void {
    this.showChartSectional = !this.showChartSectional;
    this._dispatchLayer(
      'chart-sectional', this.showChartSectional,
    );
  }
  private _toggleChartTac(): void {
    this.showChartTac = !this.showChartTac;
    this._dispatchLayer('chart-tac', this.showChartTac);
  }
  private _toggleChartHelo(): void {
    this.showChartHelo = !this.showChartHelo;
    this._dispatchLayer('chart-helo', this.showChartHelo);
  }
  private _toggleChartIfrLow(): void {
    this.showChartIfrLow = !this.showChartIfrLow;
    this._dispatchLayer(
      'chart-ifr-low', this.showChartIfrLow,
    );
  }
  private _toggleChartIfrHigh(): void {
    this.showChartIfrHigh = !this.showChartIfrHigh;
    this._dispatchLayer(
      'chart-ifr-high', this.showChartIfrHigh,
    );
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

  private async _toggleAsas(): Promise<void> {
    const next = this.asasMethod === 'OFF' ? 'ON' : 'OFF';
    await api.executeCommand(`ASAS ${next}`);
    // State poll will catch up within ~2s; optimistic flip
    // so the button responds immediately.
    this.asasMethod = next === 'ON'
      ? (this.asasMethods.find((m) => m !== 'OFF') || 'ON')
      : 'OFF';
  }

  private async _onResoChange(e: Event): Promise<void> {
    const val = (e.target as HTMLSelectElement).value;
    if (!val) return;
    await api.executeCommand(`RESO ${val}`);
    this.resoMethod = val;
  }

  private async _onLoadResoPlugin(e: Event): Promise<void> {
    const sel = e.target as HTMLSelectElement;
    const name = sel.value;
    if (!name) return;
    await api.executeCommand(`PLUGIN LOAD ${name}`);
    // Reset selector; the state poll will drop the
    // loaded plugin from the available list.
    sel.value = '';
  }

  private _onCamAircraftChange(e: Event): void {
    this.camSelectAcid =
      (e.target as HTMLSelectElement).value;
  }

  private _camSet(mode: CamMode): void {
    const acid = this.camSelectAcid || this.camTrackAcid;
    if (!acid) {
      // No aircraft picked — briefly surface a hint in
      // the readout area by temporarily clearing.
      return;
    }
    this.dispatchEvent(
      new CustomEvent('cam-view', {
        detail: { acid, mode },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _camFree(): void {
    if (!this.camTrackAcid) return;
    this.dispatchEvent(
      new CustomEvent('cam-view', {
        detail: {
          acid: this.camTrackAcid,
          mode: this.camTrackMode,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleAutoImportMetars(e: Event): void {
    const on = (e.target as HTMLInputElement).checked;
    this.autoImportMetars = on;
    this.dispatchEvent(
      new CustomEvent('metar-wind-import-toggle', {
        detail: { active: on },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindFieldCheckbox(e: Event): void {
    const checked = (e.target as HTMLInputElement).checked;
    this.showWindField = checked;
    this._dispatchLayer('wind-field', checked);
  }

  private _onWindFieldAlt(e: Event): void {
    const val = parseInt(
      (e.target as HTMLSelectElement).value, 10,
    );
    this.windFieldAltFt = val;
    this.dispatchEvent(
      new CustomEvent('wind-field-config', {
        detail: {
          altitude_ft: val,
          spacing_deg: this.windFieldSpacingDeg,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindFieldSpacing(e: Event): void {
    const val = parseFloat(
      (e.target as HTMLSelectElement).value,
    );
    this.windFieldSpacingDeg = val;
    this.dispatchEvent(
      new CustomEvent('wind-field-config', {
        detail: {
          altitude_ft: this.windFieldAltFt,
          spacing_deg: val,
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _onWindPointSelect(e: Event): void {
    const sel = e.target as HTMLSelectElement;
    if (!sel.value) return;
    const idx = parseInt(sel.value, 10);
    const p = this.windPoints[idx];
    if (!p) return;
    // Reset the dropdown immediately so the user can
    // pick the same point again later.
    sel.value = '';
    // Ask main.ts to open the detail panel for this
    // point (in view mode).  Converting the API's
    // unit-system-aware fields into the kt-native
    // shape that the panel (and barb manager) use.
    this.dispatchEvent(
      new CustomEvent('wind-open-point', {
        detail: {
          lat: p.lat,
          lon: p.lon,
          altitude_ft: p.altitude_ft,
          direction_deg: p.direction_deg,
          speed_kt: (() => {
            switch (p.units) {
              case 'si': return p.speed / 0.514444;
              case 'imperial': return p.speed / 1.15078;
              default: return p.speed;
            }
          })(),
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _toggleWindPick(): void {
    this.windPickMode = !this.windPickMode;
    this.dispatchEvent(
      new CustomEvent('wind-pick-toggle', {
        detail: { active: this.windPickMode },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Called by main.ts after a pin-drop click lands. */
  clearPickMode(): void {
    this.windPickMode = false;
  }

  private async _clearWind(): Promise<void> {
    if (!confirm('Clear all defined wind points?')) {
      return;
    }
    try {
      await fetch('/api/wind', { method: 'DELETE' });
      setTimeout(() => this.refreshWindInfo(), 150);
    } catch (err) {
      alert(`Failed to clear wind: ${err}`);
    }
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
