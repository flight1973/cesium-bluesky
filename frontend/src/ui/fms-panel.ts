/**
 * FMS Route Editor panel.
 *
 * Provides an FMS-style interface for creating and editing
 * an aircraft's flight plan:
 *
 *  ┌──────────────────────────────────┐
 *  │ FMS  KL204              [close]  │
 *  ├──────────────────────────────────┤
 *  │ ORIG [EHAM    ] DEST [LEMD    ] │
 *  ├──────────────────────────────────┤
 *  │   WPT        ALT      SPD      │
 *  │ ▶ LEKKO      FL100    ---  [x] │
 *  │   WOODY      -----    ---  [x] │
 *  │   CIV        FL350    M.80 [x] │
 *  │   LEMD       -----    ---  [x] │
 *  ├──────────────────────────────────┤
 *  │ [wpt___] [alt__] [spd__] [ADD]  │
 *  ├──────────────────────────────────┤
 *  │ [DIRECT TO...]  [CLEAR ROUTE]   │
 *  └──────────────────────────────────┘
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, query } from 'lit/decorators.js';
import { FT, KTS } from '../types';

interface RouteWaypoint {
  name: string;
  alt: number;   // meters, negative = not set
  spd: number;   // m/s, negative = not set
  active: boolean;
}

interface AircraftRoute {
  acid: string;
  orig: string;
  dest: string;
  iactwp: number;
  waypoints: RouteWaypoint[];
}

@customElement('fms-panel')
export class FmsPanel extends LitElement {
  @state() private route: AircraftRoute | null = null;
  @state() private loading = false;
  @query('#wp-name') private wpNameEl!: HTMLInputElement;
  @query('#wp-alt') private wpAltEl!: HTMLInputElement;
  @query('#wp-spd') private wpSpdEl!: HTMLInputElement;

  private onCommand: ((cmd: string) => void) | null = null;
  private refreshTimer: number | null = null;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.95);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
      overflow-y: auto;
      width: 320px;
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

    .section {
      padding: 6px 8px;
      border-bottom: 1px solid #222;
    }

    .od-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .od-row label {
      color: #888;
      font-size: 11px;
      width: 35px;
    }
    .od-row input {
      width: 70px;
    }
    .od-row button { margin-left: 2px; }

    table {
      width: 100%;
      border-collapse: collapse;
    }
    th {
      text-align: left;
      color: #888;
      font-weight: normal;
      font-size: 11px;
      padding: 2px 4px;
      border-bottom: 1px solid #333;
    }
    td {
      padding: 2px 4px;
    }
    tr.active-wp td {
      color: #ffff00;
    }
    tr.active-wp td:first-child::before {
      content: '\\25B6 ';
    }
    tr:hover { background: #1a2a1a; }

    .del-btn {
      background: none;
      border: none;
      color: #ff4444;
      cursor: pointer;
      font-size: 11px;
      font-family: inherit;
      padding: 0 4px;
    }
    .del-btn:hover { color: #ff8888; }

    .add-row {
      display: flex;
      gap: 4px;
      padding: 6px 8px;
      border-bottom: 1px solid #222;
      align-items: center;
    }

    input {
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      font-family: inherit;
      font-size: 12px;
      padding: 2px 4px;
      border-radius: 2px;
    }
    input:focus {
      border-color: #00ff00;
      outline: none;
    }
    input::placeholder {
      color: #555;
    }

    .action-row {
      display: flex;
      gap: 6px;
      padding: 6px 8px;
    }

    button.cmd-btn {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 3px 8px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    button.cmd-btn:hover {
      background: #00ff00;
      color: #000;
    }
    button.cmd-btn.danger {
      color: #ff4444;
      border-color: #ff4444;
    }
    button.cmd-btn.danger:hover {
      background: #ff4444;
      color: #000;
    }
  `;

  render() {
    if (!this.route) return nothing;
    const r = this.route;

    return html`
      <div class="header">
        <span>FMS ${r.acid}</span>
        <button class="close" @click=${this._close}>
          \u2715
        </button>
      </div>

      <!-- Origin / Destination -->
      <div class="section">
        <div class="od-row">
          <label>ORIG</label>
          <input
            id="orig-input"
            value=${r.orig}
            placeholder="ICAO"
          />
          <button class="cmd-btn"
            @click=${this._setOrig}
          >SET</button>
          <label>DEST</label>
          <input
            id="dest-input"
            value=${r.dest}
            placeholder="ICAO"
          />
          <button class="cmd-btn"
            @click=${this._setDest}
          >SET</button>
        </div>
      </div>

      <!-- Waypoint list -->
      <div class="section">
        <table>
          <thead>
            <tr>
              <th>WPT</th>
              <th>ALT</th>
              <th>SPD</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${r.waypoints.map(
              (wp, i) => html`
                <tr class=${wp.active ? 'active-wp' : ''}>
                  <td>${wp.name}</td>
                  <td>${this._fmtAlt(wp.alt)}</td>
                  <td>${this._fmtSpd(wp.spd)}</td>
                  <td>
                    <button class="del-btn"
                      title="Delete waypoint"
                      @click=${() => this._delWpt(wp.name)}
                    >\u2715</button>
                  </td>
                </tr>
              `,
            )}
          </tbody>
        </table>
      </div>

      <!-- Add waypoint row -->
      <div class="add-row">
        <input id="wp-name"
          style="width:80px"
          placeholder="WPT"
          @keydown=${this._onAddKey}
        />
        <input id="wp-alt"
          style="width:60px"
          placeholder="ALT"
          @keydown=${this._onAddKey}
        />
        <input id="wp-spd"
          style="width:50px"
          placeholder="SPD"
          @keydown=${this._onAddKey}
        />
        <button class="cmd-btn"
          @click=${this._addWpt}
        >ADD</button>
      </div>

      <!-- Action buttons -->
      <div class="action-row">
        <button class="cmd-btn"
          @click=${this._directTo}
        >DIRECT TO...</button>
        <button class="cmd-btn"
          @click=${this._lnavOn}
        >LNAV ON</button>
        <button class="cmd-btn"
          @click=${this._vnavOn}
        >VNAV ON</button>
      </div>
      <div class="action-row">
        <button class="cmd-btn danger"
          @click=${this._clearRoute}
        >CLEAR ROUTE</button>
      </div>
    `;
  }

  /** Set command handler. */
  setCommandHandler(
    handler: (cmd: string) => void,
  ): void {
    this.onCommand = handler;
  }

  /** Open the FMS for an aircraft. */
  async open(acid: string): Promise<void> {
    this.hidden = false;
    this.loading = true;
    await this._fetchRoute(acid);
    this.loading = false;
    this._startRefresh();
  }

  /** Close the FMS panel. */
  close(): void {
    this.hidden = true;
    this.route = null;
    this._stopRefresh();
  }

  // ── Data fetching ─────────────────────────────────

  private async _fetchRoute(acid: string): Promise<void> {
    try {
      const res = await fetch(
        `/api/aircraft/${acid}/detail`,
      );
      if (!res.ok) return;
      const d = await res.json();
      const r = d.route;
      this.route = {
        acid: d.acid,
        orig: d.orig || '',
        dest: d.dest || '',
        iactwp: r.iactwp,
        waypoints: r.wpname.map(
          (name: string, i: number) => ({
            name,
            alt: r.wpalt[i],
            spd: r.wpspd[i],
            active: i === r.iactwp,
          }),
        ),
      };
    } catch {
      // Fetch failed — keep existing data.
    }
  }

  private _startRefresh(): void {
    this._stopRefresh();
    this.refreshTimer = window.setInterval(() => {
      if (this.route) {
        this._fetchRoute(this.route.acid);
      }
    }, 3000);
  }

  private _stopRefresh(): void {
    if (this.refreshTimer !== null) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  // ── Commands ──────────────────────────────────────

  private _send(cmd: string): void {
    this.onCommand?.(cmd);
    setTimeout(() => {
      if (this.route) this._fetchRoute(this.route.acid);
    }, 500);
  }

  private _setOrig(): void {
    const el = this.renderRoot.querySelector(
      '#orig-input',
    ) as HTMLInputElement;
    if (el?.value && this.route) {
      this._send(`ORIG ${this.route.acid} ${el.value}`);
    }
  }

  private _setDest(): void {
    const el = this.renderRoot.querySelector(
      '#dest-input',
    ) as HTMLInputElement;
    if (el?.value && this.route) {
      this._send(`DEST ${this.route.acid} ${el.value}`);
    }
  }

  private _addWpt(): void {
    if (!this.route) return;
    const name = this.wpNameEl?.value?.trim();
    if (!name) return;
    const alt = this.wpAltEl?.value?.trim();
    const spd = this.wpSpdEl?.value?.trim();

    let cmd = `ADDWPT ${this.route.acid} ${name}`;
    if (alt) cmd += ` ${alt}`;
    if (spd) cmd += ` ${spd}`;
    this._send(cmd);

    // Clear inputs.
    if (this.wpNameEl) this.wpNameEl.value = '';
    if (this.wpAltEl) this.wpAltEl.value = '';
    if (this.wpSpdEl) this.wpSpdEl.value = '';
    this.wpNameEl?.focus();
  }

  private _onAddKey(e: KeyboardEvent): void {
    if (e.key === 'Enter') this._addWpt();
  }

  private _delWpt(wpname: string): void {
    if (!this.route) return;
    this._send(`DELWPT ${this.route.acid} ${wpname}`);
  }

  private _directTo(): void {
    if (!this.route) return;
    const wp = prompt('Direct to waypoint:');
    if (wp) {
      this._send(`DIRECT ${this.route.acid} ${wp}`);
    }
  }

  private _lnavOn(): void {
    if (!this.route) return;
    this._send(`LNAV ${this.route.acid} ON`);
  }

  private _vnavOn(): void {
    if (!this.route) return;
    this._send(`VNAV ${this.route.acid} ON`);
  }

  private _clearRoute(): void {
    if (!this.route) return;
    this._send(`DELROUTE ${this.route.acid}`);
  }

  private _close(): void {
    this.close();
  }

  // ── Formatting ────────────────────────────────────

  private _fmtAlt(alt: number): string {
    if (alt < 0) return '-----';
    const ft = alt / 0.3048;
    if (ft >= 5000) {
      return `FL${Math.round(ft / 100)}`;
    }
    return `${Math.round(ft)}ft`;
  }

  private _fmtSpd(spd: number): string {
    if (spd < 0) return '---';
    if (spd < 1) return `M${spd.toFixed(2)}`;
    return `${Math.round(spd / 0.5144)}`;
  }
}
