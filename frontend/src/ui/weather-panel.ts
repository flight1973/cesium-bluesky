/**
 * Weather panel — list + detail for METARs (and
 * eventually SIGMETs, PIREPs, etc.).
 *
 * Two modes:
 *
 * - **List mode** (default) — scrollable table of every
 *   METAR currently loaded into the map, sorted with
 *   worst weather first so problems are immediately
 *   visible.  Clicking a row drills into detail.
 * - **Detail mode** — full decoded METAR for one
 *   station, with a [back] link returning to the list.
 *
 * The panel reads from an externally-supplied list of
 * observations (main.ts owns the MetarManager and
 * calls `setMetars()` whenever it refreshes).
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import {
  msToUser, speedUnitLabel, onUnitsChange,
} from '../services/units';
import type { MetarObs } from '../cesium/entities/metars';
import type { SigmetAdvisory } from '../cesium/entities/sigmets';

// Exact AWC GFA tool palette — reverse-engineered
// from the tool's minified class `Ve` getColor()
// + getFeatureColor() functions.  Match pixel-for-
// pixel so our panel legend matches the map.
const HAZ_COLOR: Record<string, string> = {
  CONVECTIVE: '#800000',  // AWC SIGMET default (maroon)
  TS: '#800000',
  TC: '#800000',
  TURB: '#A06000',        // dark orange-brown
  ICE: '#000080',         // navy
  IFR: '#990099',         // purple
  MT_OBSC: '#FF00FF',     // G-AIRMET magenta
  MTN_OBSCN: '#FF00FF',
  VA: '#FF5F15',
  ASH: '#FF5F15',
};

const CAT_ORDER: Record<string, number> = {
  LIFR: 0, IFR: 1, MVFR: 2, VFR: 3,
};
const CAT_COLOR: Record<string, string> = {
  VFR: '#3fbf3f',
  MVFR: '#4080ff',
  IFR: '#ff4040',
  LIFR: '#ff40c0',
};
const CAT_LABEL: Record<string, string> = {
  VFR: 'VFR', MVFR: 'MVFR', IFR: 'IFR', LIFR: 'LIFR',
};

@customElement('weather-panel')
export class WeatherPanel extends LitElement {
  @state() private metars: MetarObs[] = [];
  @state() private advisories: SigmetAdvisory[] = [];
  @state() private selected: MetarObs | null = null;
  @state() private selectedAdv: SigmetAdvisory | null = null;
  @state() private filter = '';
  @state() private enabled = false;
  @state() private advEnabled = false;
  @state() private _metarsOn = false;
  @state() private _sigmetsOn = false;
  @state() private _airmetsOn = false;
  @state() private _gairmetsOn = false;
  private unitsUnsub: (() => void) | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this.unitsUnsub = onUnitsChange(
      () => this.requestUpdate(),
    );
  }

  disconnectedCallback(): void {
    this.unitsUnsub?.();
    this.unitsUnsub = null;
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
      overflow: hidden;
      width: 340px;
      height: 100%;
      display: flex;
      flex-direction: column;
    }
    :host([hidden]) { display: none; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 8px;
      border-bottom: 1px solid #333;
      font-size: 14px;
      font-weight: bold;
      flex-shrink: 0;
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
    .back {
      cursor: pointer;
      color: #888;
      font-size: 12px;
      padding: 4px 8px;
      background: #111;
      border-bottom: 1px solid #222;
    }
    .back:hover { color: #00ff00; }
    .subheader {
      padding: 4px 8px;
      border-bottom: 1px solid #222;
      color: #aaa;
      font-size: 11px;
      flex-shrink: 0;
    }
    .toggles {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 6px 8px;
      border-bottom: 1px solid #222;
      background: #0a0a0a;
      flex-shrink: 0;
      font-size: 11px;
    }
    .toggles label {
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 3px;
      color: #ccc;
    }
    .toggles label:hover { color: #fff; }
    .toggles input[type=checkbox] {
      vertical-align: middle;
    }
    .toggles .swatch {
      display: inline-block;
      width: 12px;
      height: 12px;
      border: 1px solid #555;
      border-radius: 2px;
    }
    .filter {
      padding: 4px 8px;
      border-bottom: 1px solid #222;
      flex-shrink: 0;
    }
    .filter input {
      width: 100%;
      background: #111;
      border: 1px solid #333;
      color: #00ff00;
      padding: 3px 6px;
      font-family: inherit;
      font-size: 12px;
      box-sizing: border-box;
    }
    .filter input:focus {
      border-color: #00ff00;
      outline: none;
    }
    .list {
      overflow-y: auto;
      flex: 1;
      min-height: 0;
    }
    .empty {
      padding: 20px;
      text-align: center;
      color: #666;
      font-size: 11px;
    }
    .row {
      display: grid;
      grid-template-columns: 50px 60px 1fr;
      align-items: center;
      gap: 8px;
      padding: 5px 8px;
      border-bottom: 1px solid #181818;
      cursor: pointer;
      font-size: 11px;
    }
    .row:hover { background: #111; }
    .cat-badge {
      padding: 1px 4px;
      border-radius: 2px;
      text-align: center;
      font-weight: bold;
      font-size: 10px;
      border: 1px solid;
    }
    .icao {
      color: #eee;
      font-weight: bold;
    }
    .row-meta { color: #888; }

    /* Detail section, same styles as before. */
    .section {
      padding: 6px 8px;
      border-bottom: 1px solid #222;
    }
    .field-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 3px 0;
    }
    .field-label {
      width: 72px;
      color: #888;
      font-size: 11px;
    }
    .field-value { flex: 1; color: #00ff00; }
    .cat-detail {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 2px;
      font-weight: bold;
      font-size: 11px;
      margin: 6px 8px;
      border: 1px solid;
    }
    .station-name {
      color: #aaa;
      font-size: 11px;
      padding: 2px 8px 6px;
      border-bottom: 1px solid #222;
    }
    .obs-time {
      color: #888;
      font-size: 10px;
      padding: 0 8px 6px;
    }
    .decoded {
      padding: 8px;
      font-size: 11px;
      color: #00ff00;
      line-height: 1.6;
      white-space: pre-wrap;
      border-bottom: 1px solid #222;
    }
    .raw {
      padding: 8px;
      font-size: 10px;
      color: #666;
      background: #0a0a0a;
      border-top: 1px solid #222;
      word-break: break-word;
      white-space: pre-wrap;
    }
  `;

  /** Set the current list of METARs (from main.ts). */
  setMetars(metars: MetarObs[]): void {
    this.metars = metars;
    // If a detail is open and its station is no longer
    // in the list, fall back to list view.
    if (
      this.selected
      && !metars.find((m) => m.icao === this.selected!.icao)
    ) {
      this.selected = null;
    }
  }

  /** Called when the METAR layer toggles (for state). */
  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  /** Set advisories list (called by main.ts). */
  setAdvisories(items: SigmetAdvisory[]): void {
    this.advisories = items;
    if (
      this.selectedAdv
      && !items.find((a) => a.id === this.selectedAdv!.id)
    ) {
      this.selectedAdv = null;
    }
  }

  setAdvisoriesEnabled(enabled: boolean): void {
    this.advEnabled = enabled;
  }

  /** Mirror the current SIGMET/AIRMET toggle states so
   * the in-panel toggles reflect what's enabled on the
   * map.  Called by main.ts on toggle-layer events. */
  setToggleStates(
    metars: boolean,
    sigmets: boolean,
    airmets: boolean,
    gairmets: boolean = false,
  ): void {
    this._metarsOn = metars;
    this._sigmetsOn = sigmets;
    this._airmetsOn = airmets;
    this._gairmetsOn = gairmets;
  }

  /** Open in list mode. */
  showList(): void {
    this.selected = null;
    this.selectedAdv = null;
    this.hidden = false;
  }

  /** Open in detail mode for a specific station. */
  showStation(obs: MetarObs): void {
    this.selected = obs;
    this.selectedAdv = null;
    this.hidden = false;
  }

  /** Open in detail mode for an AIRMET/SIGMET. */
  showAdvisory(adv: SigmetAdvisory): void {
    this.selectedAdv = adv;
    this.selected = null;
    this.hidden = false;
  }

  hide(): void {
    this.hidden = true;
    this.dispatchEvent(
      new CustomEvent('weather-panel-close', {
        bubbles: true, composed: true,
      }),
    );
  }

  render() {
    if (this.selectedAdv) return this._renderAdvDetail();
    if (this.selected) return this._renderDetail();
    return this._renderList();
  }

  // ── List mode ────────────────────────────────────

  private _renderList() {
    const sorted = [...this.metars].sort((a, b) => {
      const oa = CAT_ORDER[a.flt_cat ?? ''] ?? 9;
      const ob = CAT_ORDER[b.flt_cat ?? ''] ?? 9;
      if (oa !== ob) return oa - ob;
      return (a.icao || '').localeCompare(b.icao || '');
    });
    const q = this.filter.trim().toUpperCase();
    const filtered = q
      ? sorted.filter((m) =>
        (m.icao || '').includes(q)
        || (m.name || '').toUpperCase().includes(q))
      : sorted;
    const unitLabel = speedUnitLabel();

    return html`
      <div class="header">
        <span>WEATHER</span>
        <button class="close"
          @click=${this._close}
        >\u2715</button>
      </div>
      <div class="toggles">
        <label title="Toggle METAR stations">
          <input type="checkbox"
            .checked=${this._metarsOn}
            @change=${(e: Event) => this._dispatchToggle(
              'metars',
              (e.target as HTMLInputElement).checked,
            )}
          />
          <span class="swatch"
            style="background: linear-gradient(90deg,
              #3fbf3f 0%, #3fbf3f 25%,
              #4080ff 25%, #4080ff 50%,
              #ff4040 50%, #ff4040 75%,
              #ff40c0 75%, #ff40c0 100%);"
          ></span>
          METARs
        </label>
        <label title="Toggle SIGMET polygons">
          <input type="checkbox"
            .checked=${this._sigmetsOn}
            @change=${(e: Event) => this._dispatchToggle(
              'sigmets',
              (e.target as HTMLInputElement).checked,
            )}
          />
          <span class="swatch"
            style="background:#800000;"
          ></span>
          SIGMETs
        </label>
        <label title="Toggle G-AIRMET polygons — the
          modern AWC AIRMET product">
          <input type="checkbox"
            .checked=${this._gairmetsOn}
            @change=${(e: Event) => this._dispatchToggle(
              'gairmets',
              (e.target as HTMLInputElement).checked,
            )}
          />
          <span class="swatch"
            style="background:#6666ff;"
          ></span>
          G-AIRMETs
        </label>
      </div>
      <div class="subheader">
        METAR stations:
        ${this.metars.length} loaded
        ${filtered.length !== this.metars.length
          ? html`(${filtered.length} shown)`
          : nothing}
      </div>
      <div class="filter">
        <input type="text"
          placeholder="Filter by ICAO or name…"
          .value=${this.filter}
          @input=${(e: Event) =>
            this.filter =
              (e.target as HTMLInputElement).value}
        />
      </div>
      <div class="list">
        ${this._renderAdvisoriesSection()}
        <div class="subheader"
          style="border-top: 1px solid #333"
        >STATIONS</div>
        ${!this.enabled && this.metars.length === 0
          ? html`<div class="empty">
              METAR stations are not loaded.<br/>
              Enable above or in the <b>WX</b> tab.
            </div>`
          : filtered.length === 0
            ? html`<div class="empty">
                No matches.
              </div>`
            : filtered.map((m) => this._renderRow(
              m, unitLabel,
            ))}
      </div>
    `;
  }

  private _dispatchToggle(layer: string, on: boolean): void {
    this.dispatchEvent(
      new CustomEvent('toggle-layer', {
        detail: { layer, visible: on },
        bubbles: true, composed: true,
      }),
    );
  }

  private _renderAdvisoriesSection() {
    const sorted = [...this.advisories].sort(
      (a, b) => (b.severity ?? 0) - (a.severity ?? 0),
    );
    return html`
      <div class="subheader">
        ADVISORIES (SIGMET / AIRMET):
        ${this.advisories.length} active
      </div>
      ${!this.advEnabled && this.advisories.length === 0
        ? html`<div class="empty"
            style="padding: 12px 20px"
          >
            No advisories loaded.  Enable SIGMETs or
            AIRMETs in the <b>WX</b> tab.
          </div>`
        : sorted.length === 0
          ? html`<div class="empty"
              style="padding: 12px 20px"
            >No active advisories.</div>`
          : sorted.map((a) => this._renderAdvRow(a))}
    `;
  }

  private _renderAdvRow(a: SigmetAdvisory) {
    const haz = (a.hazard || 'UNK').toUpperCase();
    const color = HAZ_COLOR[haz] || '#ffe040';
    const altStr = (() => {
      if (a.bottom_ft === 0 && a.top_ft >= 60000) {
        return 'All alts';
      }
      const lo = a.bottom_ft === 0
        ? 'SFC' : `FL${Math.round(a.bottom_ft / 100)}`;
      const hi = a.top_ft >= 60000
        ? 'UNL' : `FL${Math.round(a.top_ft / 100)}`;
      return `${lo}–${hi}`;
    })();
    return html`
      <div class="row"
        style="grid-template-columns: 72px 80px 1fr;"
        @click=${() => this.selectedAdv = a}
      >
        <span class="cat-badge"
          style="background:${color}22;
                 color:${color};
                 border-color:${color};"
        >${a.type} ${haz}</span>
        <span class="row-meta">${altStr}</span>
        <span class="row-meta">${
          a.severity != null ? `sev ${a.severity}` : ''
        } ${
          a.movement_spd
            ? `· ${a.movement_dir}°/${a.movement_spd}kt`
            : ''
        }</span>
      </div>
    `;
  }

  private _renderAdvDetail() {
    const a = this.selectedAdv!;
    const haz = (a.hazard || 'UNK').toUpperCase();
    const color = HAZ_COLOR[haz] || '#ffe040';
    const validFrom = a.valid_from
      ? new Date(a.valid_from * 1000).toISOString()
        .replace('T', ' ').replace('.000Z', ' Z')
      : '—';
    const validTo = a.valid_to
      ? new Date(a.valid_to * 1000).toISOString()
        .replace('T', ' ').replace('.000Z', ' Z')
      : '—';
    const altBand = a.bottom_ft === 0
      ? (a.top_ft >= 60000 ? 'All altitudes'
          : `Surface to FL${Math.round(a.top_ft / 100)}`)
      : `FL${Math.round(a.bottom_ft / 100)} to FL${
        Math.round(a.top_ft / 100)}`;

    return html`
      <div class="header">
        <span>${a.type} · ${haz}</span>
        <button class="close"
          @click=${this._close}
        >\u2715</button>
      </div>
      <div class="back"
        @click=${() => this.selectedAdv = null}
      >\u2190 Back to list</div>
      <span class="cat-detail"
        style="background:${color}22;
               color:${color};
               border-color:${color};"
      >${a.type} · ${haz}${
        a.severity != null ? ` · sev ${a.severity}` : ''
      }</span>

      <div class="section">
        <div class="field-row">
          <span class="field-label">ALT BAND</span>
          <span class="field-value">${altBand}</span>
        </div>
        <div class="field-row">
          <span class="field-label">VALID</span>
          <span class="field-value"
            style="font-size: 10px"
          >${validFrom} → ${validTo}</span>
        </div>
        ${a.movement_spd ? html`
          <div class="field-row">
            <span class="field-label">MOVING</span>
            <span class="field-value">${
              a.movement_dir
            }° at ${a.movement_spd} kt</span>
          </div>
        ` : nothing}
        <div class="field-row">
          <span class="field-label">ISSUED BY</span>
          <span class="field-value">${a.icao ?? '—'}</span>
        </div>
      </div>

      ${a.raw ? html`<div class="raw">${a.raw}</div>` : nothing}
    `;
  }

  private _renderRow(m: MetarObs, unitLabel: string) {
    const cat = m.flt_cat ?? '';
    const color = CAT_COLOR[cat] ?? '#888';
    const spd = m.wspd_kt != null
      ? Math.round(msToUser(m.wspd_kt * 0.514444))
      : null;
    const wind = (m.wdir_deg != null && spd !== null)
      ? `${String(Math.round(m.wdir_deg))
        .padStart(3, '0')}°/${spd}${unitLabel}`
      : (spd !== null ? `${spd}${unitLabel}` : '—');
    return html`
      <div class="row"
        @click=${() => this._selectStation(m)}
      >
        <span class="cat-badge"
          style="background:${color}22;
                 color:${color};
                 border-color:${color};"
        >${CAT_LABEL[cat] ?? '?'}</span>
        <span class="icao">${m.icao}</span>
        <span class="row-meta">${wind}
          ${m.visib ? html`· ${m.visib}` : nothing}</span>
      </div>
    `;
  }

  // ── Detail mode ──────────────────────────────────

  private _renderDetail() {
    const m = this.selected!;
    const cat = m.flt_cat ?? null;
    const catColor = cat && CAT_COLOR[cat]
      ? CAT_COLOR[cat] : '#888';

    return html`
      <div class="header">
        <span>${m.icao} METAR</span>
        <button class="close"
          @click=${this._close}
        >\u2715</button>
      </div>
      <div class="back"
        @click=${() => this.selected = null}
      >\u2190 Back to list</div>

      ${cat ? html`
        <span class="cat-detail"
          style="background:${catColor}22;
                 color:${catColor};
                 border-color:${catColor};"
        >${CAT_LABEL[cat] ?? cat}</span>
      ` : nothing}

      ${m.decoded ? html`
        <div class="decoded">${m.decoded}</div>
      ` : nothing}

      ${m.raw ? html`<div class="raw">${m.raw}</div>` : nothing}
    `;
  }

  private _close(): void { this.hide(); }

  private _selectStation(m: MetarObs): void {
    this.selected = m;
    this.dispatchEvent(
      new CustomEvent('weather-select-station', {
        detail: { icao: m.icao, lat: m.lat, lon: m.lon },
        bubbles: true, composed: true,
      }),
    );
  }
}
