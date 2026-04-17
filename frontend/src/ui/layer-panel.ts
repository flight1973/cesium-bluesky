import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

interface LayerItem {
  id: string;
  label: string;
  defaultOn: boolean;
}

interface LayerGroup {
  id: string;
  label: string;
  expanded: boolean;
  items: LayerItem[];
}

const LAYER_TREE: LayerGroup[] = [
  {
    id: 'traffic', label: 'Traffic', expanded: true, items: [
      { id: 'live-traffic', label: 'Live / Replay', defaultOn: false },
      { id: 'interpolation', label: 'Interpolation', defaultOn: true },
      { id: 'trails', label: 'Trails', defaultOn: false },
      { id: 'leaders', label: 'Velocity Vectors', defaultOn: true },
      { id: 'pz', label: 'Protected Zones', defaultOn: false },
      { id: 'labels', label: 'Labels', defaultOn: true },
      { id: 'routes', label: 'Routes', defaultOn: true },
    ],
  },
  {
    id: 'airspace', label: 'Airspace', expanded: false, items: [
      { id: 'class-b', label: 'Class B', defaultOn: false },
      { id: 'class-c', label: 'Class C', defaultOn: false },
      { id: 'class-d', label: 'Class D', defaultOn: false },
      { id: 'class-e2', label: 'Class E2 (Surface)', defaultOn: false },
      { id: 'class-e3', label: 'Class E3 (Navaid)', defaultOn: false },
      { id: 'class-e4', label: 'Class E4 (Transition)', defaultOn: false },
      { id: 'class-e5', label: 'Class E5 (1200 AGL)', defaultOn: false },
      { id: 'class-e6', label: 'Class E6 (Airway)', defaultOn: false },
      { id: 'class-e-other', label: 'Class E (Other)', defaultOn: false },
      { id: 'sua-p', label: 'SUA Prohibited', defaultOn: false },
      { id: 'sua-r', label: 'SUA Restricted', defaultOn: false },
      { id: 'sua-w', label: 'SUA Warning', defaultOn: false },
      { id: 'sua-a', label: 'SUA Alert', defaultOn: false },
      { id: 'sua-m', label: 'SUA MOA', defaultOn: false },
      { id: 'tfrs', label: 'TFRs', defaultOn: false },
    ],
  },
  {
    id: 'navigation', label: 'Navigation', expanded: false, items: [
      { id: 'airports', label: 'Airports', defaultOn: true },
      { id: 'waypoints', label: 'Waypoints', defaultOn: false },
    ],
  },
  {
    id: 'weather', label: 'Weather', expanded: false, items: [
      { id: 'metars', label: 'METARs', defaultOn: false },
      { id: 'sigmets', label: 'SIGMETs', defaultOn: false },
      { id: 'gairmets', label: 'G-AIRMETs', defaultOn: false },
      { id: 'pireps', label: 'PIREPs', defaultOn: false },
      { id: 'wind-barbs', label: 'Wind Barbs', defaultOn: false },
      { id: 'wind-field', label: 'Wind Field', defaultOn: false },
      { id: 'radar', label: 'Radar (NEXRAD)', defaultOn: false },
      { id: 'satellite', label: 'Satellite', defaultOn: false },
      { id: 'wx-mrms', label: 'MRMS Precip', defaultOn: false },
      { id: 'wx-goes-vis', label: 'GOES Visible', defaultOn: false },
      { id: 'wx-spc-outlook', label: 'SPC Outlook', defaultOn: false },
      { id: 'wx-wwa', label: 'Winter Wx Advisory', defaultOn: false },
      { id: 'wx-ndfd-temp', label: 'NDFD Temperature', defaultOn: false },
      { id: 'wx-smoke', label: 'Smoke Forecast', defaultOn: false },
    ],
  },
  {
    id: 'charts', label: 'Charts', expanded: false, items: [
      { id: 'chart-sectional', label: 'VFR Sectional', defaultOn: false },
      { id: 'chart-tac', label: 'Terminal Area', defaultOn: false },
      { id: 'chart-ifr-low', label: 'IFR Low', defaultOn: false },
      { id: 'chart-ifr-high', label: 'IFR High', defaultOn: false },
    ],
  },
  {
    id: 'overlays', label: 'Overlays', expanded: false, items: [
      { id: 'graticule', label: 'Lat/Lon Grid', defaultOn: false },
      { id: 'conflicts', label: 'Conflicts Panel', defaultOn: false },
    ],
  },
];

export interface ImageryOption { id: string; label: string; disabled: boolean; }
export interface TerrainOption { id: string; label: string; disabled: boolean; }

@customElement('layer-panel')
export class LayerPanel extends LitElement {
  @state() private _on = new Set<string>();
  @state() private _expanded = new Set<string>();
  @state() private _opacity = new Map<string, number>();
  @state() is3D = false;
  @state() altScale = 2;
  @state() imageryOptions: ImageryOption[] = [];
  @state() terrainOptions: TerrainOption[] = [];
  @state() currentImagery = '';
  @state() currentTerrain = '';
  @state() ionTokenSet = false;

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      background: #111;
      color: #ccc;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 11px;
      border-right: 1px solid #333;
      overflow-y: auto;
      user-select: none;
    }

    .panel-header {
      padding: 6px 10px;
      font-size: 12px;
      font-weight: bold;
      color: #00ff00;
      border-bottom: 1px solid #333;
      background: #0a0a0a;
    }

    .group {
      border-bottom: 1px solid #222;
    }

    .group-header {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 5px 8px;
      cursor: pointer;
      background: #151515;
      font-weight: bold;
      font-size: 11px;
      color: #aaa;
    }
    .group-header:hover { background: #1a1a1a; color: #ddd; }

    .arrow {
      display: inline-block;
      width: 12px;
      font-size: 9px;
      color: #666;
      text-align: center;
      flex-shrink: 0;
    }

    .group-label { flex: 1; }

    .group-count {
      font-size: 9px;
      color: #555;
      font-weight: normal;
    }

    .group-check {
      width: 14px;
      height: 14px;
      accent-color: #00ff00;
      cursor: pointer;
      flex-shrink: 0;
    }

    .items {
      background: #0d0d0d;
    }

    .item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 3px 8px 3px 28px;
      cursor: pointer;
      flex-wrap: wrap;
    }
    .item:hover { background: #181818; }

    .opacity-slider {
      display: none;
      width: 100%;
      padding: 2px 0 2px 19px;
    }
    .item:hover .opacity-slider,
    .item.on .opacity-slider { display: flex; }

    .opacity-slider input {
      flex: 1;
      height: 3px;
      accent-color: #00ff00;
      cursor: pointer;
    }
    .opacity-slider span {
      font-size: 9px;
      color: #555;
      min-width: 28px;
      text-align: right;
    }

    .item-check {
      width: 13px;
      height: 13px;
      accent-color: #00ff00;
      cursor: pointer;
      flex-shrink: 0;
    }

    .item-label {
      flex: 1;
      color: #aaa;
    }
    .item.on .item-label { color: #00ff00; }

    /* ── View controls section ──────── */
    .view-section {
      padding: 6px 10px;
      border-bottom: 1px solid #333;
      background: #0e0e0e;
      display: flex;
      flex-direction: column;
      gap: 5px;
    }

    .view-row {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .view-section label {
      color: #888;
      font-size: 10px;
      min-width: 42px;
    }

    .view-section select {
      flex: 1;
      background: #222;
      color: #00ff00;
      border: 1px solid #444;
      border-radius: 3px;
      font-family: inherit;
      font-size: 10px;
      padding: 2px 3px;
    }

    .view-btn {
      background: #222;
      color: #888;
      border: 1px solid #444;
      border-radius: 3px;
      cursor: pointer;
      font-family: inherit;
      font-size: 10px;
      padding: 2px 8px;
    }
    .view-btn:hover { color: #ccc; border-color: #888; }
    .view-btn.active {
      background: #00ff00;
      color: #000;
      border-color: #00ff00;
      font-weight: bold;
    }

    .alt-slider {
      flex: 1;
      height: 4px;
      accent-color: #00ff00;
    }

    .alt-val {
      color: #00ff00;
      font-size: 10px;
      min-width: 28px;
      text-align: right;
    }
  `;

  connectedCallback(): void {
    super.connectedCallback();
    for (const g of LAYER_TREE) {
      if (g.expanded) this._expanded.add(g.id);
      for (const item of g.items) {
        if (item.defaultOn) this._on.add(item.id);
      }
    }
  }

  setLayerState(layerId: string, on: boolean): void {
    if (on) {
      this._on.add(layerId);
    } else {
      this._on.delete(layerId);
    }
    this.requestUpdate();
  }

  render() {
    return html`
      <div class="panel-header">LAYERS</div>
      <div class="view-section">
        <div class="view-row">
          <button class="view-btn ${!this.is3D ? 'active' : ''}"
            @click=${() => this._setView(false)}>2D</button>
          <button class="view-btn ${this.is3D ? 'active' : ''}"
            @click=${() => this._setView(true)}>3D</button>
          <label>Alt:</label>
          <input type="range" class="alt-slider"
            min="1" max="50" step="1"
            .value=${String(this.altScale)}
            @input=${this._onAltScale} />
          <span class="alt-val">${this.altScale}x</span>
        </div>
        <div class="view-row">
          <label>Imagery:</label>
          <select @change=${this._onImagery}>
            ${this.imageryOptions.map(o => html`
              <option value=${o.id} ?disabled=${o.disabled}
                ?selected=${this.currentImagery === o.id}
              >${o.label}</option>
            `)}
          </select>
        </div>
        <div class="view-row">
          <label>Terrain:</label>
          <select @change=${this._onTerrain}>
            ${this.terrainOptions.map(o => html`
              <option value=${o.id} ?disabled=${o.disabled}
                ?selected=${this.currentTerrain === o.id}
              >${o.label}</option>
            `)}
          </select>
        </div>
      </div>
      ${LAYER_TREE.map(g => this._renderGroup(g))}
    `;
  }

  private _renderGroup(g: LayerGroup) {
    const expanded = this._expanded.has(g.id);
    const onCount = g.items.filter(i => this._on.has(i.id)).length;

    return html`
      <div class="group">
        <div class="group-header" @click=${() => this._toggleGroup(g.id)}>
          <span class="arrow">${expanded ? '\u25BC' : '\u25B6'}</span>
          <input type="checkbox" class="group-check"
            .checked=${onCount > 0}
            .indeterminate=${onCount > 0 && onCount < g.items.length}
            @click=${(e: Event) => { e.stopPropagation(); this._toggleAllInGroup(g, e); }}
          />
          <span class="group-label">${g.label}</span>
          ${onCount > 0 ? html`<span class="group-count">${onCount}</span>` : nothing}
        </div>
        ${expanded ? html`
          <div class="items">
            ${g.items.map(item => this._renderItem(item))}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _renderItem(item: LayerItem) {
    const on = this._on.has(item.id);
    const opac = this._opacity.get(item.id) ?? 100;
    return html`
      <div class="item ${on ? 'on' : ''}" @click=${() => this._toggleItem(item.id)}>
        <input type="checkbox" class="item-check"
          .checked=${on}
          @click=${(e: Event) => e.stopPropagation()}
          @change=${() => this._toggleItem(item.id)}
        />
        <span class="item-label">${item.label}</span>
        <div class="opacity-slider" @click=${(e: Event) => e.stopPropagation()}>
          <input type="range" min="0" max="100" step="5"
            .value=${String(opac)}
            @input=${(e: Event) => this._onOpacity(item.id, e)}
          />
          <span>${opac}%</span>
        </div>
      </div>
    `;
  }

  private _toggleGroup(id: string): void {
    if (this._expanded.has(id)) {
      this._expanded.delete(id);
    } else {
      this._expanded.add(id);
    }
    this.requestUpdate();
  }

  private _toggleAllInGroup(g: LayerGroup, e: Event): void {
    const target = e.target as HTMLInputElement;
    const turnOn = target.checked;
    for (const item of g.items) {
      const wasOn = this._on.has(item.id);
      if (turnOn && !wasOn) {
        this._on.add(item.id);
        this._dispatch(item.id, true);
      } else if (!turnOn && wasOn) {
        this._on.delete(item.id);
        this._dispatch(item.id, false);
      }
    }
    this.requestUpdate();
  }

  private _toggleItem(id: string): void {
    const on = !this._on.has(id);
    if (on) {
      this._on.add(id);
    } else {
      this._on.delete(id);
    }
    this._dispatch(id, on);
    this.requestUpdate();
  }

  private _onOpacity(layerId: string, e: Event): void {
    const val = Number((e.target as HTMLInputElement).value);
    this._opacity.set(layerId, val);
    this.requestUpdate();
    this.dispatchEvent(new CustomEvent('layer-opacity', {
      detail: { layer: layerId, opacity: val / 100 },
      bubbles: true, composed: true,
    }));
  }

  // ── View controls ──────────────────────────────────

  private _setView(is3D: boolean): void {
    this.is3D = is3D;
    this.dispatchEvent(new CustomEvent('toggle-view', {
      detail: { is3D }, bubbles: true, composed: true,
    }));
  }

  private _onAltScale(e: Event): void {
    this.altScale = Number((e.target as HTMLInputElement).value);
    this.dispatchEvent(new CustomEvent('alt-scale', {
      detail: { scale: this.altScale }, bubbles: true, composed: true,
    }));
  }

  private _onImagery(e: Event): void {
    const id = (e.target as HTMLSelectElement).value;
    this.currentImagery = id;
    this.dispatchEvent(new CustomEvent('imagery-change', {
      detail: { id }, bubbles: true, composed: true,
    }));
  }

  private _onTerrain(e: Event): void {
    const id = (e.target as HTMLSelectElement).value;
    this.currentTerrain = id;
    this.dispatchEvent(new CustomEvent('terrain-change', {
      detail: { id }, bubbles: true, composed: true,
    }));
  }

  private _dispatch(layer: string, visible: boolean): void {
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: { layer, visible },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
