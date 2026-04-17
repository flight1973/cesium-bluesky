/**
 * Opacity panel — sliders for every dim-able layer.
 *
 * Opens via a "🌗" button in the toolbar.  Each
 * row is one layer (or layer-group) with a 0–100
 * slider that updates the OpacityService.  Managers
 * subscribe to the service and re-render at the
 * new alpha.
 *
 * Default alpha is 100 (native).  Reset button per
 * row + a "reset all" master.
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { opacity } from '../services/opacity';

interface LayerRow {
  key: string;
  label: string;
  group: string;
}

const LAYERS: LayerRow[] = [
  // Airspace fills — most-frequently-tweaked
  // because Class E in particular wants a low
  // default to avoid washing out the map.
  { key: 'TFR',        label: 'TFRs',          group: 'Airspace' },
  { key: 'SUA_P',      label: 'Prohibited',    group: 'Airspace' },
  { key: 'SUA_R',      label: 'Restricted',    group: 'Airspace' },
  { key: 'SUA_W',      label: 'Warning',       group: 'Airspace' },
  { key: 'SUA_A',      label: 'Alert',         group: 'Airspace' },
  { key: 'SUA_M',      label: 'MOA',           group: 'Airspace' },
  { key: 'CLASS_B',    label: 'Class B',       group: 'Airspace' },
  { key: 'CLASS_C',    label: 'Class C',       group: 'Airspace' },
  { key: 'CLASS_D',    label: 'Class D',       group: 'Airspace' },
  { key: 'CLASS_E2',   label: 'Class E2',      group: 'Airspace' },
  { key: 'CLASS_E3',   label: 'Class E3',      group: 'Airspace' },
  { key: 'CLASS_E4',   label: 'Class E4',      group: 'Airspace' },
  { key: 'CLASS_E5',   label: 'Class E5',      group: 'Airspace' },
  { key: 'CLASS_E6',   label: 'Class E6',      group: 'Airspace' },
  { key: 'CLASS_E_OTHER', label: 'Class E (other)', group: 'Airspace' },
  // Hazard advisories
  { key: 'SIGMET',     label: 'SIGMETs',       group: 'Advisories' },
  { key: 'AIRMET',     label: 'AIRMETs',       group: 'Advisories' },
  { key: 'G-AIRMET',   label: 'G-AIRMETs / CWA / ISIGMET', group: 'Advisories' },
  // Other layers (manager-level opacity)
  { key: 'PROCEDURE',  label: 'Procedures',    group: 'Routes' },
  { key: 'PIREP',      label: 'PIREPs',        group: 'Weather' },
  // FAA aeronautical chart overlays
  { key: 'CHART_SECTIONAL', label: 'VFR Sectional',  group: 'Charts' },
  { key: 'CHART_TAC',       label: 'Terminal Area',  group: 'Charts' },
  { key: 'CHART_HELO',      label: 'Helicopter',     group: 'Charts' },
  { key: 'CHART_IFR_LOW',   label: 'IFR Low',        group: 'Charts' },
  { key: 'CHART_IFR_HIGH',  label: 'IFR High',       group: 'Charts' },
];


@customElement('opacity-panel')
export class OpacityPanel extends LitElement {
  @state() private values: Record<string, number> = {};
  private _unsub: (() => void) | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    // Snapshot once; the service is canonical.
    this.values = opacity.all();
    this._unsub = opacity.onChange((k, a) => {
      this.values = { ...this.values, [k]: a };
    });
  }

  disconnectedCallback(): void {
    this._unsub?.();
    super.disconnectedCallback();
  }

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
      width: 320px;
      height: 100%;
      overflow-y: auto;
    }
    :host([hidden]) { display: none; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 8px;
      border-bottom: 1px solid #333;
      font-size: 13px;
      font-weight: bold;
    }
    .close {
      cursor: pointer;
      color: #888;
      font-size: 16px;
      border: none;
      background: none;
      font-family: inherit;
    }
    .close:hover { color: #ff4444; }
    .group {
      padding: 4px 8px 8px 8px;
      border-bottom: 1px solid #181818;
    }
    .group-label {
      color: #888;
      font-size: 11px;
      text-transform: uppercase;
      margin: 4px 0 4px 0;
    }
    .row {
      display: grid;
      grid-template-columns: 90px 1fr 36px 24px;
      align-items: center;
      gap: 6px;
      padding: 2px 0;
    }
    .row label { color: #ddd; font-size: 11px; }
    .row input[type=range] {
      width: 100%;
      accent-color: #00ff00;
    }
    .row .pct {
      color: #888;
      font-size: 10px;
      text-align: right;
    }
    .row button.reset {
      background: none;
      border: none;
      color: #555;
      cursor: pointer;
      font-size: 11px;
      padding: 0 2px;
    }
    .row button.reset:hover { color: #aaa; }
    .footer {
      padding: 8px;
      border-top: 1px solid #222;
    }
    .footer button {
      width: 100%;
      background: #111;
      border: 1px solid #333;
      color: #aaa;
      padding: 4px;
      font-family: inherit;
      cursor: pointer;
    }
    .footer button:hover {
      color: #fff;
      border-color: #555;
    }
  `;

  render() {
    const groups = new Map<string, LayerRow[]>();
    for (const l of LAYERS) {
      const g = groups.get(l.group) ?? [];
      g.push(l);
      groups.set(l.group, g);
    }
    return html`
      <div class="header">
        <span>Layer Opacity</span>
        <button class="close"
                @click=${() => this._close()}>×</button>
      </div>
      ${[...groups.entries()].map(
        ([g, rows]) => html`
          <div class="group">
            <div class="group-label">${g}</div>
            ${rows.map((r) => this._renderRow(r))}
          </div>
        `,
      )}
      <div class="footer">
        <button @click=${() => this._resetAll()}>
          Reset all to 100%
        </button>
      </div>
    `;
  }

  private _renderRow(r: LayerRow) {
    const v = this.values[r.key] ?? 1.0;
    const pct = Math.round(v * 100);
    return html`
      <div class="row">
        <label>${r.label}</label>
        <input type="range" min="0" max="100" .value=${String(pct)}
          @input=${(e: Event) => this._onSlide(r.key, e)} />
        <span class="pct">${pct}%</span>
        <button class="reset" title="Reset to 100%"
                @click=${() => opacity.set(r.key, 1.0)}>↺</button>
      </div>
    `;
  }

  private _onSlide(key: string, e: Event): void {
    const v = Number((e.target as HTMLInputElement).value) / 100;
    opacity.set(key, v);
  }

  private _resetAll(): void {
    for (const r of LAYERS) opacity.set(r.key, 1.0);
  }

  private _close(): void {
    this.hidden = true;
    this.dispatchEvent(new CustomEvent('panel-close', {
      detail: { panel: 'opacity' },
      bubbles: true, composed: true,
    }));
  }
}
