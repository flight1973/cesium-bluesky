/**
 * Conflicts panel — live list of traffic conflicts
 * (loss-of-separation events and predicted conflicts).
 *
 * Each row shows the aircraft pair, TCPA, DCPA, and
 * severity.  Clicking a row flies the camera to the
 * midpoint between the two aircraft.  Rows pulse
 * amber for predicted conflicts and red for active
 * loss-of-separation.
 *
 * Data comes from the ACDATA WebSocket topic which
 * already carries ``confpairs``, ``lospairs``,
 * ``conf_tcpa``, ``conf_dcpa`` arrays.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

interface ConflictEntry {
  ac1: string;
  ac2: string;
  tcpa: number;   // seconds
  dcpa: number;   // meters
  isLos: boolean; // true = active LOS, false = predicted
}

@customElement('conflicts-panel')
export class ConflictsPanel extends LitElement {
  @state() private conflicts: ConflictEntry[] = [];
  @state() private expanded = false;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 11px;
      border: 1px solid #333;
      border-radius: 4px;
      overflow: hidden;
      max-height: 300px;
      width: 320px;
    }
    :host([hidden]) { display: none; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 8px;
      background: #1a0000;
      border-bottom: 1px solid #333;
      cursor: pointer;
      user-select: none;
    }
    .header:hover { background: #2a0000; }
    .title {
      font-weight: bold;
      font-size: 12px;
    }
    .count {
      background: #ff3030;
      color: #fff;
      padding: 1px 6px;
      border-radius: 8px;
      font-size: 10px;
      font-weight: bold;
    }
    .count.zero {
      background: #333;
      color: #888;
    }
    .list {
      overflow-y: auto;
      max-height: 260px;
    }
    .row {
      display: grid;
      grid-template-columns: 70px 70px 55px 55px 30px;
      align-items: center;
      gap: 4px;
      padding: 4px 8px;
      border-bottom: 1px solid #181818;
      cursor: pointer;
      font-size: 10px;
    }
    .row:hover { background: #111; }
    .row.los {
      background: rgba(255, 0, 0, 0.08);
      border-left: 3px solid #ff3030;
    }
    .row.conf {
      background: rgba(255, 160, 0, 0.06);
      border-left: 3px solid #ffa000;
    }
    .ac { color: #eee; font-weight: bold; }
    .tcpa { color: #ffa000; }
    .dcpa { color: #ff6060; }
    .sev {
      text-align: center;
      font-weight: bold;
      font-size: 9px;
      padding: 1px 3px;
      border-radius: 2px;
    }
    .sev.los { background: #ff3030; color: #fff; }
    .sev.conf { background: #ffa000; color: #000; }
    .empty {
      padding: 12px;
      text-align: center;
      color: #555;
    }
    .col-hdr {
      display: grid;
      grid-template-columns: 70px 70px 55px 55px 30px;
      gap: 4px;
      padding: 2px 8px;
      color: #666;
      font-size: 9px;
      border-bottom: 1px solid #222;
    }
  `;

  /**
   * Called by main.ts on each ACDATA frame with
   * the conflict arrays.
   */
  update_conflicts(
    confpairs: [string, string][],
    lospairs: [string, string][],
    tcpa: number[],
    dcpa: number[],
  ): void {
    const losSet = new Set(
      lospairs.map((p) => `${p[0]}|${p[1]}`),
    );
    const entries: ConflictEntry[] = [];
    for (let i = 0; i < confpairs.length; i++) {
      const [ac1, ac2] = confpairs[i];
      const key = `${ac1}|${ac2}`;
      entries.push({
        ac1, ac2,
        tcpa: tcpa[i] ?? 0,
        dcpa: dcpa[i] ?? 0,
        isLos: losSet.has(key),
      });
    }
    // Sort: LOS first, then by TCPA ascending.
    entries.sort((a, b) => {
      if (a.isLos !== b.isLos) return a.isLos ? -1 : 1;
      return a.tcpa - b.tcpa;
    });
    this.conflicts = entries;
  }

  render() {
    const n = this.conflicts.length;
    return html`
      <div class="header"
           @click=${() => this.expanded = !this.expanded}>
        <span class="title">CONFLICTS</span>
        <span class="count ${n === 0 ? 'zero' : ''}">${n}</span>
      </div>
      ${this.expanded ? this._renderList() : nothing}
    `;
  }

  private _renderList() {
    if (!this.conflicts.length) {
      return html`<div class="empty">
        No active conflicts
      </div>`;
    }
    return html`
      <div class="col-hdr">
        <span>AC 1</span>
        <span>AC 2</span>
        <span>TCPA</span>
        <span>DCPA</span>
        <span></span>
      </div>
      <div class="list">
        ${this.conflicts.map((c) => this._renderRow(c))}
      </div>
    `;
  }

  private _renderRow(c: ConflictEntry) {
    const tcpaStr = c.tcpa > 0
      ? `${Math.round(c.tcpa)}s`
      : 'NOW';
    const dcpaNm = c.dcpa / 1852.0;
    const dcpaStr = dcpaNm < 10
      ? `${dcpaNm.toFixed(1)} NM`
      : `${Math.round(dcpaNm)} NM`;
    const cls = c.isLos ? 'row los' : 'row conf';
    const sevCls = c.isLos ? 'sev los' : 'sev conf';
    const sevLabel = c.isLos ? 'LOS' : 'CONF';
    return html`
      <div class=${cls}
           @click=${() => this._selectPair(c)}>
        <span class="ac">${c.ac1}</span>
        <span class="ac">${c.ac2}</span>
        <span class="tcpa">${tcpaStr}</span>
        <span class="dcpa">${dcpaStr}</span>
        <span class=${sevCls}>${sevLabel}</span>
      </div>
    `;
  }

  private _selectPair(c: ConflictEntry): void {
    this.dispatchEvent(new CustomEvent(
      'conflict-select',
      {
        detail: { ac1: c.ac1, ac2: c.ac2 },
        bubbles: true, composed: true,
      },
    ));
  }
}
