/**
 * Traffic list panel -- replicates the Qt TrafficList tab.
 *
 * Shows a sortable table of all aircraft with columns:
 *   CALLSIGN | FL | TRK | CAS
 *
 * Clicking a row selects/deselects the aircraft.
 * Conflict aircraft are highlighted in orange.
 * Updates throttled to 1 Hz (from 5 Hz ACDATA stream).
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import type { AcData } from '../types';
import { FT, KTS } from '../types';

interface AircraftRow {
  acid: string;
  fl: number;
  trk: number;
  cas: number;
  inconf: boolean;
}

@customElement('bluesky-traffic-list')
export class BlueSkyTrafficList extends LitElement {
  @state() rows: AircraftRow[] = [];
  @state() selectedAcid: string | null = null;
  private _throttleTimer: number | null = null;

  static styles = css`
    :host {
      display: block;
      background: #1a1a1a;
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      overflow-y: auto;
      height: 100%;
    }
    .header {
      padding: 4px 8px;
      color: #888;
      font-size: 11px;
      border-bottom: 1px solid #333;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th {
      position: sticky;
      top: 0;
      background: #111;
      padding: 3px 6px;
      text-align: left;
      color: #888;
      font-weight: normal;
      font-size: 11px;
      border-bottom: 1px solid #333;
    }
    td { padding: 2px 6px; }
    tr:hover { background: #1a2a1a; cursor: pointer; }
    tr.selected { background: #003333; color: #00ffff; }
    tr.conflict td { color: #ffa000; }
  `;

  render() {
    return html`
      <div class="header">Aircraft</div>
      <table>
        <thead>
          <tr>
            <th>CALLSIGN</th>
            <th>FL</th>
            <th>TRK</th>
            <th>CAS</th>
          </tr>
        </thead>
        <tbody>
          ${this.rows.map(
            (r) => html`
              <tr
                class="${r.acid === this.selectedAcid ? 'selected' : ''} ${r.inconf ? 'conflict' : ''}"
                @click=${() => this._onSelect(r.acid)}
              >
                <td>${r.acid}</td>
                <td>${r.fl}</td>
                <td>${Math.round(r.trk)}</td>
                <td>${r.cas}</td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    `;
  }

  /** Update from ACDATA -- throttled to 1 Hz. */
  updateFromAcData(data: AcData): void {
    if (this._throttleTimer !== null) return;
    this._throttleTimer = window.setTimeout(() => {
      this._throttleTimer = null;
    }, 1000);

    this.rows = data.id.map((acid, i) => ({
      acid,
      fl: Math.round(data.alt[i] / FT / 100),
      trk: data.trk[i],
      cas: Math.round(data.cas[i] / KTS),
      inconf: data.inconf?.[i] ?? false,
    }));
  }

  private _onSelect(acid: string): void {
    this.selectedAcid =
      acid === this.selectedAcid ? null : acid;
    this.dispatchEvent(
      new CustomEvent('aircraft-select', {
        detail: { acid: this.selectedAcid },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
