/**
 * Airport panel — opens when the user clicks an
 * airport dot on the globe.  Lists published CIFP
 * procedures (SIDs / STARs / IAPs) grouped by type;
 * each row has a checkbox that toggles the
 * procedure's polyline on the globe.
 *
 * State lives in this component (which proc ids are
 * on); geometry rendering is delegated via the
 * ``toggle-procedure`` CustomEvent that main.ts
 * listens for.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

interface ProcEntry {
  id: string;
  proc_type: 'SID' | 'STAR' | 'IAP';
  name: string;
  transition: string | null;
  n_legs: number;
  pbn_requirement?: string;
  pbn_rnp_nm?: number | null;
  pbn_flyable?: boolean;
}

interface TafBlock {
  id: string;
  icao: string;
  issue_time: string | null;
  valid_from: string | null;
  valid_to: string | null;
  time_group: number | null;
  fcst_type: string | null;
  wdir_deg: number | null;
  wspd_kt: number | null;
  wgst_kt: number | null;
  visib: number | string | null;
  ceil_ft: number | null;
  clouds: any[] | null;
  flt_cat: string | null;
  raw: string | null;
}

const TYPE_COLOR: Record<string, string> = {
  SID: '#30e030',
  STAR: '#30d0e0',
  IAP: '#e040e0',
};

@customElement('airport-panel')
export class AirportPanel extends LitElement {
  @state() private airport: string | null = null;
  @state() private aptPos: { lat: number; lon: number } | null = null;
  @state() private items: ProcEntry[] = [];
  @state() private loading = false;
  @state() private error: string | null = null;
  /** Ids currently checked (visible on globe). */
  @state() private active = new Set<string>();
  /** Which type tab is expanded. */
  @state() private openType: 'SID' | 'STAR' | 'IAP' | null = 'IAP';
  /** Top-level tab. */
  @state() private tab: 'procedures' | 'weather' = 'procedures';
  /** When set, the procedure list includes PBN
   * ``pbn_flyable`` gating per the aircraft's
   * PBN capability.  Set externally by main.ts
   * (e.g., from the selected aircraft's type). */
  @state() acType: string | null = null;
  /** TAF state — fetched on first weather-tab visit. */
  @state() private tafBlocks: TafBlock[] = [];
  @state() private tafLoading = false;
  @state() private tafError: string | null = null;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
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
    .meta {
      padding: 4px 8px;
      border-bottom: 1px solid #222;
      color: #aaa;
      font-size: 11px;
    }
    .empty, .loading, .error {
      padding: 20px;
      text-align: center;
      color: #666;
      font-size: 11px;
    }
    .error { color: #ff6060; }
    .list {
      overflow-y: auto;
      flex: 1;
      min-height: 0;
    }
    .group-header {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 8px;
      background: #111;
      border-bottom: 1px solid #222;
      cursor: pointer;
      font-weight: bold;
      user-select: none;
    }
    .group-header:hover { background: #1a1a1a; }
    .group-chev {
      color: #666;
      width: 10px;
      text-align: center;
    }
    .group-count {
      color: #666;
      font-weight: normal;
      font-size: 11px;
      margin-left: auto;
    }
    .group-swatch {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 2px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 8px 4px 22px;
      border-bottom: 1px solid #181818;
      font-size: 11px;
      cursor: pointer;
    }
    .row:hover { background: #0e0e0e; }
    .row input[type=checkbox] {
      margin: 0;
      accent-color: var(--swatch);
    }
    .row .name { color: #eee; flex: 1; }
    .row .transition { color: #888; font-size: 10px; }
    .row .legs { color: #555; font-size: 10px; }
    .pbn-badge {
      display: inline-block;
      padding: 0 3px;
      border-radius: 2px;
      font-size: 9px;
      font-weight: bold;
      margin-left: 4px;
    }
    .pbn-badge.ar { background: #3a1040; color: #e060ff; }
    .pbn-badge.rnp { background: #102040; color: #60a0ff; }
    .pbn-badge.rnav { background: #103010; color: #60c060; }
    .pbn-badge.nogo { background: #401010; color: #ff6060; opacity: 0.8; }
    .row.unflyable { opacity: 0.45; }

    .actions {
      padding: 4px 8px;
      border-top: 1px solid #222;
      display: flex;
      gap: 6px;
      flex-shrink: 0;
    }
    .actions button {
      flex: 1;
      background: #111;
      border: 1px solid #333;
      color: #aaa;
      font-family: inherit;
      font-size: 11px;
      padding: 3px 6px;
      cursor: pointer;
    }
    .actions button:hover {
      color: #fff;
      border-color: #555;
    }

    .tabs {
      display: flex;
      border-bottom: 1px solid #222;
      flex-shrink: 0;
    }
    .tab {
      flex: 1;
      padding: 6px 8px;
      background: #0a0a0a;
      color: #888;
      cursor: pointer;
      text-align: center;
      font-size: 11px;
      border: none;
      border-right: 1px solid #222;
      font-family: inherit;
    }
    .tab:last-child { border-right: none; }
    .tab.active {
      background: #1a1a1a;
      color: #00ff00;
      border-bottom: 1px solid #00ff00;
    }
    .tab:hover { color: #ddd; }

    .taf-block {
      padding: 6px 8px;
      border-bottom: 1px solid #181818;
      font-size: 11px;
    }
    .taf-block .head {
      display: flex;
      justify-content: space-between;
      color: #aaa;
      margin-bottom: 3px;
      font-size: 10px;
    }
    .taf-block .type-tag {
      display: inline-block;
      padding: 0 4px;
      background: #1a1a3a;
      color: #88aaff;
      border-radius: 2px;
      font-weight: bold;
      font-size: 10px;
    }
    .taf-block .row {
      display: flex;
      gap: 12px;
      color: #ddd;
      font-family: monospace;
    }
    .taf-block .label {
      color: #777;
      font-size: 10px;
    }
    .taf-cat {
      display: inline-block;
      padding: 1px 4px;
      border-radius: 2px;
      font-weight: bold;
      font-size: 10px;
    }
    .taf-cat.VFR  { background: #103010; color: #5fdf5f; }
    .taf-cat.MVFR { background: #102040; color: #80a0ff; }
    .taf-cat.IFR  { background: #401010; color: #ff7070; }
    .taf-cat.LIFR { background: #301030; color: #ff70d0; }
    .taf-raw {
      padding: 6px 8px;
      background: #0a0a0a;
      color: #aaa;
      font-family: monospace;
      font-size: 10px;
      white-space: pre-wrap;
      word-break: break-word;
      border-bottom: 1px solid #222;
    }
  `;

  /**
   * Open the panel for ``icao``.  Fetches the
   * procedure index immediately; TAF is fetched
   * lazily when the user switches to the weather
   * tab.  ``pos`` lets us request a tight bbox
   * around the airport for the TAF query.
   */
  async open(
    icao: string,
    pos?: { lat: number; lon: number },
  ): Promise<void> {
    this.airport = icao.toUpperCase();
    this.aptPos = pos ?? null;
    this.loading = true;
    this.error = null;
    this.items = [];
    this.tafBlocks = [];
    this.tafError = null;
    this.tab = 'procedures';
    this.hidden = false;
    try {
      let url = `/api/navdata/procedures?airport=${this.airport}`;
      if (this.acType) {
        url += `&ac_type=${encodeURIComponent(this.acType)}`;
      }
      const res = await fetch(url);
      if (!res.ok) {
        this.error = `HTTP ${res.status}`;
        return;
      }
      const data = await res.json();
      this.items = data.items || [];
    } catch (e) {
      this.error = String(e);
    } finally {
      this.loading = false;
    }
  }

  private async _fetchTafs(): Promise<void> {
    if (!this.aptPos || !this.airport) return;
    this.tafLoading = true;
    this.tafError = null;
    try {
      const { lat, lon } = this.aptPos;
      // ±0.5 deg around the airport — TAFs are
      // airport-specific, this catches a single
      // station reliably.
      const bounds =
        `${lat - 0.5},${lon - 0.5},${lat + 0.5},${lon + 0.5}`;
      const res = await fetch(
        `/api/weather/tafs?bounds=${bounds}`,
      );
      if (!res.ok) {
        this.tafError = `HTTP ${res.status}`;
        return;
      }
      const data = await res.json();
      // Filter to this airport (the bbox can pick
      // up neighboring airports' TAFs).
      this.tafBlocks = (data.items || [])
        .filter((b: TafBlock) => b.icao === this.airport);
    } catch (e) {
      this.tafError = String(e);
    } finally {
      this.tafLoading = false;
    }
  }

  hide(): void {
    this.hidden = true;
    // Leave ``active`` intact so the panel restores
    // checkbox state if the user re-opens the same
    // airport without toggling via the map.
  }

  /** Called by main.ts when it successfully shows a proc. */
  markActive(id: string): void {
    this.active = new Set([...this.active, id]);
    this.requestUpdate();
  }

  /** Called by main.ts when a proc gets hidden externally. */
  markInactive(id: string): void {
    this.active.delete(id);
    this.active = new Set(this.active);
    this.requestUpdate();
  }

  /** Remove all visible procedures for this airport. */
  clearActive(): void {
    const airportPrefix = `${this.airport}-`;
    const next = new Set<string>();
    for (const id of this.active) {
      if (id.startsWith(airportPrefix)) continue;
      next.add(id);
    }
    this.active = next;
    this.requestUpdate();
  }

  render() {
    if (!this.airport) return nothing;
    const byType: Record<string, ProcEntry[]> = {
      SID: [], STAR: [], IAP: [],
    };
    for (const it of this.items) {
      (byType[it.proc_type] ??= []).push(it);
    }
    for (const k of Object.keys(byType)) {
      byType[k].sort((a, b) =>
        a.name.localeCompare(b.name)
        || (a.transition || '').localeCompare(b.transition || ''),
      );
    }

    return html`
      <div class="header">
        <span>${this.airport}</span>
        <button class="close" @click=${this._close}>×</button>
      </div>
      <div class="tabs">
        <button
          class="tab ${this.tab === 'procedures' ? 'active' : ''}"
          @click=${() => this._setTab('procedures')}>
          Procedures (${this.items.length})
        </button>
        <button
          class="tab ${this.tab === 'weather' ? 'active' : ''}"
          @click=${() => this._setTab('weather')}>
          Weather
        </button>
      </div>
      ${this.tab === 'procedures'
        ? this._renderProcedures(byType)
        : this._renderWeather()}
      <div class="actions">
        ${this.tab === 'procedures'
          ? html`<button @click=${this._deselectAll}>
              Hide all
            </button>`
          : nothing}
        <button @click=${this._close}>Close</button>
      </div>
    `;
  }

  private _renderProcedures(
    byType: Record<string, ProcEntry[]>,
  ) {
    return html`
      <div class="meta">
        ${this.loading
          ? 'Loading…'
          : `${this.items.length} procedures`}
      </div>
      ${this.error
        ? html`<div class="error">${this.error}</div>`
        : this.items.length === 0 && !this.loading
          ? html`<div class="empty">
              No procedures found.
            </div>`
          : html`<div class="list">
              ${(['IAP', 'STAR', 'SID'] as const).map(
                (t) => this._renderGroup(t, byType[t]),
              )}
            </div>`}
    `;
  }

  private _renderWeather() {
    if (this.tafLoading) {
      return html`<div class="loading">Loading TAF…</div>`;
    }
    if (this.tafError) {
      return html`<div class="error">
        ${this.tafError}
      </div>`;
    }
    if (!this.tafBlocks.length) {
      return html`<div class="empty">
        No TAF available for ${this.airport}.
      </div>`;
    }
    // Group by issue_time so multiple amendments
    // surface as separate stacks; show the most-
    // recent issuance first.
    const blocks = [...this.tafBlocks].sort(
      (a, b) => (b.time_group ?? 0) - (a.time_group ?? 0),
    ).reverse();
    const issued = blocks[0]?.issue_time ?? '';
    const raw = blocks[0]?.raw ?? '';
    return html`
      <div class="meta">
        TAF issued ${issued
          ? new Date(issued).toUTCString()
          : '—'}
      </div>
      ${raw ? html`<div class="taf-raw">${raw}</div>` : nothing}
      <div class="list">
        ${blocks.map((b) => this._renderTafBlock(b))}
      </div>
    `;
  }

  private _renderTafBlock(b: TafBlock) {
    const validFrom = b.valid_from
      ? new Date(b.valid_from).toUTCString().slice(0, 22)
      : '—';
    const validTo = b.valid_to
      ? new Date(b.valid_to).toUTCString().slice(0, 22)
      : '—';
    const wind = b.wdir_deg != null && b.wspd_kt != null
      ? `${String(b.wdir_deg).padStart(3, '0')}@${b.wspd_kt}`
        + (b.wgst_kt ? `G${b.wgst_kt}` : '')
        + ' kt'
      : '—';
    const cat = b.flt_cat || '';
    return html`
      <div class="taf-block">
        <div class="head">
          <span>
            <span class="type-tag">${b.fcst_type ?? '—'}</span>
            ${cat
              ? html`<span class="taf-cat ${cat}">${cat}</span>`
              : nothing}
          </span>
          <span>${validFrom} → ${validTo}</span>
        </div>
        <div class="row">
          <span><span class="label">Wind</span> ${wind}</span>
          <span><span class="label">Vis</span> ${b.visib ?? '—'}</span>
          <span><span class="label">Ceil</span> ${
            b.ceil_ft != null ? `${b.ceil_ft} ft` : '—'
          }</span>
        </div>
      </div>
    `;
  }

  private _setTab(t: 'procedures' | 'weather'): void {
    this.tab = t;
    if (t === 'weather' && !this.tafBlocks.length
        && !this.tafLoading) {
      void this._fetchTafs();
    }
  }

  private _renderGroup(
    type: 'SID' | 'STAR' | 'IAP',
    rows: ProcEntry[],
  ) {
    if (!rows.length) return nothing;
    const open = this.openType === type;
    return html`
      <div class="group-header"
           @click=${() => this._toggleGroup(type)}>
        <span class="group-chev">${open ? '▾' : '▸'}</span>
        <span class="group-swatch"
              style="background:${TYPE_COLOR[type]}"></span>
        <span>${type}</span>
        <span class="group-count">${rows.length}</span>
      </div>
      ${open
        ? rows.map((r) => this._renderRow(r, type))
        : nothing}
    `;
  }

  private _renderRow(r: ProcEntry, type: string) {
    const on = this.active.has(r.id);
    // PBN badge: show the requirement level, and dim
    // the row if the aircraft can't fly it.
    const rnp = r.pbn_rnp_nm;
    const flyable = r.pbn_flyable;
    const pbnBadge = rnp != null
      ? html`<span class="pbn-badge ${
          rnp <= 0.1 ? 'ar' : rnp <= 1.0 ? 'rnp' : 'rnav'
        }" title="${r.pbn_requirement ?? ''}">${
          rnp <= 0.1 ? 'RNP AR'
          : rnp <= 0.3 ? `RNP ${rnp}`
          : rnp <= 1.0 ? 'RNP 1'
          : `RNAV ${rnp}`
        }</span>`
      : nothing;
    const noGoBadge = flyable === false
      ? html`<span class="pbn-badge nogo"
          title="Aircraft PBN capability insufficient">NO-GO</span>`
      : nothing;
    const rowCls = flyable === false
      ? 'row unflyable' : 'row';
    return html`
      <div class=${rowCls}
           style="--swatch:${TYPE_COLOR[type]}"
           @click=${() => this._toggleProc(r)}>
        <input type="checkbox" .checked=${on}
               @click=${(e: Event) => e.stopPropagation()}
               @change=${() => this._toggleProc(r)} />
        <span class="name">${r.name}${pbnBadge}${noGoBadge}</span>
        <span class="transition">${r.transition ?? ''}</span>
        <span class="legs">${r.n_legs}L</span>
      </div>
    `;
  }

  private _toggleGroup(
    t: 'SID' | 'STAR' | 'IAP',
  ): void {
    this.openType = this.openType === t ? null : t;
  }

  private _toggleProc(r: ProcEntry): void {
    const on = !this.active.has(r.id);
    this.dispatchEvent(
      new CustomEvent('toggle-procedure', {
        detail: { id: r.id, on },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _deselectAll(): void {
    for (const id of Array.from(this.active)) {
      this.dispatchEvent(
        new CustomEvent('toggle-procedure', {
          detail: { id, on: false },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private _close(): void {
    this.hide();
    this.dispatchEvent(
      new CustomEvent('panel-close', {
        detail: { panel: 'airport' },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
