/**
 * Aircraft detail/edit panel.
 *
 * Shows when an aircraft is selected (click on map or traffic
 * list).  Displays origin, destination, route, heading, speed,
 * altitude, vertical rate — and allows editing them inline.
 *
 * Layout:
 * ┌─────────────────────────────┐
 * │ KL204  B738         [close] │
 * │ EHAM → LEMD                 │
 * ├─────────────────────────────┤
 * │ HDG   180°   [___] [SET]    │
 * │ ALT   FL350  [___] [SET]    │
 * │ SPD   280kts [___] [SET]    │
 * │ VS    0fpm   [___] [SET]    │
 * ├─────────────────────────────┤
 * │ LNAV [ON ] VNAV [OFF]      │
 * ├─────────────────────────────┤
 * │ Route: 5 waypoints          │
 * │ > EHAM                      │
 * │   SPY   FL350/280           │
 * │   ...                       │
 * └─────────────────────────────┘
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { FT, KTS } from '../types';

interface AircraftDetail {
  acid: string;
  actype: string;
  lat: number;
  lon: number;
  alt: number;
  tas: number;
  cas: number;
  gs: number;
  trk: number;
  vs: number;
  orig: string;
  dest: string;
  sel_hdg: number;
  sel_alt: number;
  sel_spd: number;
  sel_vs: number;
  lnav: boolean;
  vnav: boolean;
  route: {
    iactwp: number;
    wpname: string[];
    wplat: number[];
    wplon: number[];
    wpalt: number[];
    wpspd: number[];
  };
}

@customElement('aircraft-panel')
export class AircraftPanel extends LitElement {
  @state() private detail: AircraftDetail | null = null;
  @state() private loading = false;

  private onCommand: ((cmd: string) => void) | null = null;
  private refreshTimer: number | null = null;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
      overflow-y: auto;
      width: 280px;
      height: 100%;
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
    .route-info {
      padding: 4px 8px;
      color: #888;
      border-bottom: 1px solid #222;
    }
    .route-info .airports {
      color: #00ff00;
      font-size: 13px;
    }
    .section {
      padding: 6px 8px;
      border-bottom: 1px solid #222;
    }
    .field-row {
      display: flex;
      align-items: center;
      gap: 4px;
      margin: 3px 0;
    }
    .field-label {
      width: 36px;
      color: #888;
      font-size: 11px;
    }
    .field-value {
      flex: 1;
      color: #00ff00;
    }
    input {
      width: 60px;
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      font-family: inherit;
      font-size: 12px;
      padding: 1px 4px;
      border-radius: 2px;
    }
    input:focus {
      border-color: #00ff00;
      outline: none;
    }
    .set-btn {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 1px 6px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    .set-btn:hover {
      background: #00ff00;
      color: #000;
    }
    .toggle-row {
      display: flex;
      gap: 12px;
      padding: 4px 0;
    }
    .toggle-btn {
      background: #222;
      color: #888;
      border: 1px solid #444;
      padding: 2px 8px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    .toggle-btn.on {
      color: #00ff00;
      border-color: #00ff00;
    }
    .wp-list {
      padding: 4px 8px;
      max-height: 200px;
      overflow-y: auto;
    }
    .wp-row {
      padding: 1px 0;
      color: #888;
    }
    .wp-row.active {
      color: #ffff00;
    }
    .wp-row.active::before {
      content: '\\25B6 ';
    }
  `;

  render() {
    if (!this.detail) return nothing;
    const d = this.detail;
    const fl = Math.round(d.alt / FT / 100);
    const cas = Math.round(d.cas / KTS);
    const selFl = Math.round(d.sel_alt / FT / 100);
    const selSpd = Math.round(d.sel_spd / KTS);
    const vs = Math.round(d.vs / FT * 60);
    const r = d.route;

    return html`
      <div class="header">
        <span>${d.acid} ${d.actype}</span>
        <button class="close" @click=${this._close}>
          \u2715
        </button>
      </div>
      <div class="route-info">
        <div class="airports">
          ${d.orig || '----'} \u2192 ${d.dest || '----'}
        </div>
      </div>

      <div class="section">
        ${this._fieldRow(
          'HDG', `${Math.round(d.trk)}\u00B0`,
          'hdg-input', `${Math.round(d.sel_hdg)}`,
          (v) => this._send(`HDG ${d.acid} ${v}`),
        )}
        ${this._fieldRow(
          'ALT', `FL${fl}`,
          'alt-input', `FL${selFl}`,
          (v) => this._send(`ALT ${d.acid} ${v}`),
        )}
        ${this._fieldRow(
          'SPD', `${cas}kts`,
          'spd-input', `${selSpd}`,
          (v) => this._send(`SPD ${d.acid} ${v}`),
        )}
        ${this._fieldRow(
          'VS', `${vs}fpm`,
          'vs-input', `${Math.round(d.sel_vs / FT * 60)}`,
          (v) => this._send(`VS ${d.acid} ${v}`),
        )}
      </div>

      <div class="section">
        <div class="toggle-row">
          <button
            class="toggle-btn ${d.lnav ? 'on' : ''}"
            @click=${() => this._send(
              `LNAV ${d.acid} ${d.lnav ? 'OFF' : 'ON'}`,
            )}
          >LNAV ${d.lnav ? 'ON' : 'OFF'}</button>
          <button
            class="toggle-btn ${d.vnav ? 'on' : ''}"
            @click=${() => this._send(
              `VNAV ${d.acid} ${d.vnav ? 'OFF' : 'ON'}`,
            )}
          >VNAV ${d.vnav ? 'ON' : 'OFF'}</button>
          <button
            class="toggle-btn on"
            @click=${() => this._openFms()}
          >FMS</button>
        </div>
      </div>

      ${r.wpname.length > 0 ? html`
        <div class="section" style="color:#888">
          Route: ${r.wpname.length} waypoints
        </div>
        <div class="wp-list">
          ${r.wpname.map((name, i) => {
            const wpFl = r.wpalt[i] > 0
              ? `FL${Math.round(r.wpalt[i] / FT / 100)}`
              : '-----';
            const wpSpd = r.wpspd[i] > 0
              ? `${Math.round(r.wpspd[i] / KTS)}`
              : '---';
            return html`
              <div class="wp-row ${i === r.iactwp ? 'active' : ''}">
                ${name} ${wpFl}/${wpSpd}
              </div>
            `;
          })}
        </div>
      ` : nothing}
    `;
  }

  /** Set command handler for sending BlueSky commands. */
  setCommandHandler(
    handler: (cmd: string) => void,
  ): void {
    this.onCommand = handler;
  }

  /** Load and show detail for an aircraft. */
  async showAircraft(acid: string): Promise<void> {
    this.loading = true;
    this.hidden = false;
    try {
      const res = await fetch(
        `/api/aircraft/${acid}/detail`,
      );
      if (!res.ok) {
        this.detail = null;
        return;
      }
      this.detail = await res.json();
    } catch {
      this.detail = null;
    }
    this.loading = false;

    // Auto-refresh every 2s while open.
    this._stopRefresh();
    this.refreshTimer = window.setInterval(
      () => this._refresh(), 2000,
    );
  }

  private _openFms(): void {
    if (!this.detail) return;
    this.dispatchEvent(
      new CustomEvent('open-fms', {
        detail: { acid: this.detail.acid },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Hide the panel. */
  hide(): void {
    this.hidden = true;
    this.detail = null;
    this._stopRefresh();
    this.dispatchEvent(
      new CustomEvent('panel-close', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _close(): void {
    this.hide();
  }

  private _send(cmd: string): void {
    this.onCommand?.(cmd);
    // Refresh detail after command takes effect.
    setTimeout(() => this._refresh(), 500);
  }

  private async _refresh(): Promise<void> {
    if (!this.detail) return;
    try {
      const res = await fetch(
        `/api/aircraft/${this.detail.acid}/detail`,
      );
      if (res.ok) {
        this.detail = await res.json();
      }
    } catch {
      // Ignore refresh failures.
    }
  }

  private _stopRefresh(): void {
    if (this.refreshTimer !== null) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  private _fieldRow(
    label: string,
    current: string,
    inputId: string,
    defaultVal: string,
    onSet: (value: string) => void,
  ) {
    return html`
      <div class="field-row">
        <span class="field-label">${label}</span>
        <span class="field-value">${current}</span>
        <input
          id=${inputId}
          value=${defaultVal}
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              const input = e.target as HTMLInputElement;
              onSet(input.value);
            }
          }}
        />
        <button
          class="set-btn"
          @click=${() => {
            const el = this.renderRoot.querySelector(
              `#${inputId}`,
            ) as HTMLInputElement;
            if (el) onSet(el.value);
          }}
        >SET</button>
      </div>
    `;
  }
}
