/**
 * Status bar -- replicates the Qt siminfoLabel exactly.
 *
 * Format:
 *   t: 00:15:30, Δt: 0.05, Speed: 1.0x, UTC: 2026-04-13 00:15:30,
 *   Mode: OP, Aircraft: 405, Conflicts: 0/0, LoS: 0/0
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import type { SimInfo } from '../types';

@customElement('bluesky-statusbar')
export class BlueSkyStatusBar extends LitElement {
  @state() private simt = 0;
  @state() private simdt = 0.05;
  @state() private speed = 1.0;
  @state() private utc = '';
  @state() private mode = 'INIT';
  @state() private ntraf = 0;
  @state() private nconfCur = 0;
  @state() private nconfTot = 0;
  @state() private nlosCur = 0;
  @state() private nlosTot = 0;
  @state() private wallUtc = '';
  private _clockTimer: number | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this._updateWallClock();
    this._clockTimer = window.setInterval(
      () => this._updateWallClock(), 1000,
    );
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._clockTimer !== null) {
      clearInterval(this._clockTimer);
    }
  }

  static styles = css`
    :host {
      display: block;
      padding: 2px 8px;
      background: #1a1a1a;
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-top: 1px solid #333;
      white-space: nowrap;
      overflow: hidden;
    }
    b { color: #00cc00; }
    .conflict { color: #ffa000; }
    .los { color: #ff4444; }
  `;

  render() {
    const t = this._fmtTime(this.simt);
    /* eslint-disable max-len */
    return html`
      <b>Sim:</b> ${t},
      <b>Sim UTC:</b> ${this.utc},
      <b>Wall UTC:</b> ${this.wallUtc},
      <b>\u0394t:</b> ${this.simdt.toFixed(2)},
      <b>Speed:</b> ${this.speed.toFixed(1)}x,
      <b>Mode:</b> ${this.mode},
      <b>Aircraft:</b> ${this.ntraf},
      <span class="conflict"><b>Conflicts:</b> ${this.nconfCur}/${this.nconfTot}</span>,
      <span class="los"><b>LoS:</b> ${this.nlosCur}/${this.nlosTot}</span>
    `;
    /* eslint-enable max-len */
  }

  /** Update from SIMINFO topic. */
  updateFromSimInfo(info: SimInfo): void {
    this.simt = info.simt;
    this.simdt = info.simdt;
    this.speed = info.dtmult;
    this.utc = info.utc;
    this.mode = info.state_name;
    this.ntraf = info.ntraf;
  }

  /** Update conflict counts from ACDATA. */
  updateConflicts(
    nconfCur: number,
    nconfTot: number,
    nlosCur: number,
    nlosTot: number,
  ): void {
    this.nconfCur = nconfCur;
    this.nconfTot = nconfTot;
    this.nlosCur = nlosCur;
    this.nlosTot = nlosTot;
  }

  private _updateWallClock(): void {
    const now = new Date();
    this.wallUtc =
      now.getUTCFullYear() + '-' +
      String(now.getUTCMonth() + 1).padStart(2, '0') +
      '-' +
      String(now.getUTCDate()).padStart(2, '0') +
      ' ' +
      String(now.getUTCHours()).padStart(2, '0') + ':' +
      String(now.getUTCMinutes()).padStart(2, '0') +
      ':' +
      String(now.getUTCSeconds()).padStart(2, '0');
  }

  private _fmtTime(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return (
      String(h).padStart(2, '0') + ':' +
      String(m).padStart(2, '0') + ':' +
      String(s).padStart(2, '0')
    );
  }
}
