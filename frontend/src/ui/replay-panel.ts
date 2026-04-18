import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import {
  replayController,
  type ReplaySession,
  type ReplayState,
} from '../services/replay';

@customElement('replay-panel')
export class ReplayPanel extends LitElement {
  @state() private sessions: ReplaySession[] = [];
  @state() private rs: ReplayState = replayController.state;
  @state() private loading = false;
  @state() private _exportOpen = false;
  @state() private _exportName = '';
  @state() private _exporting = false;
  @state() private _exportResult = '';

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.85);
      border-radius: 6px;
      border: 1px solid #333;
      padding: 8px 12px;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 11px;
      color: #00ff00;
      min-width: 360px;
    }

    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }
    .title { font-size: 12px; font-weight: bold; }

    .row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 4px;
    }

    select {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 3px;
      font-family: inherit;
      font-size: 11px;
      padding: 2px 4px;
      cursor: pointer;
      flex: 1;
    }

    button {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 3px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
      padding: 2px 8px;
      min-width: 28px;
    }
    button:hover { background: #00ff00; color: #000; }
    button.active { background: #00ff00; color: #000; }
    button:disabled {
      opacity: 0.4;
      cursor: default;
      background: #222;
      color: #00ff00;
    }
    button.stop {
      border-color: #ff4444;
      color: #ff4444;
    }
    button.stop:hover {
      background: #ff4444;
      color: #000;
    }

    .timeline {
      margin-top: 6px;
    }

    input[type="range"] {
      -webkit-appearance: none;
      width: 100%;
      height: 6px;
      background: #333;
      border-radius: 3px;
      outline: none;
      cursor: pointer;
    }
    input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      background: #00ff00;
      border-radius: 50%;
      cursor: grab;
    }

    .time-row {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #888;
      margin-top: 2px;
    }

    .current-time {
      color: #00ff00;
      font-size: 12px;
      text-align: center;
      margin: 2px 0;
    }

    .speed-row {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 4px;
    }
    .speed-row span { color: #888; font-size: 10px; }
    .speed-btn {
      padding: 1px 6px;
      font-size: 10px;
      min-width: 32px;
    }

    .info {
      color: #666;
      font-size: 10px;
      margin-top: 4px;
    }

    .export-form {
      margin-top: 4px;
      padding: 6px;
      background: #0a0a0a;
      border: 1px solid #222;
      border-radius: 3px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .export-form label {
      color: #888;
      font-size: 10px;
    }
  `;

  connectedCallback(): void {
    super.connectedCallback();
    replayController.onChange(s => {
      const wasActive = this.rs.active;
      this.rs = s;
      if (wasActive && !s.active) this._loadSessions();
    });
    this._loadSessions();
  }

  private async _loadSessions(): Promise<void> {
    this.sessions = await replayController.loadSessions();
    if (this.sessions.length === 0) {
      setTimeout(() => this._retryLoad(), 2000);
    }
  }

  private async _retryLoad(): Promise<void> {
    if (this.sessions.length > 0) return;
    this.sessions = await replayController.loadSessions();
  }

  render() {
    if (!this.rs.active) return this._renderPicker();
    return this._renderPlayer();
  }

  private _renderPicker() {
    return html`
      <div class="header">
        <span class="title">REPLAY</span>
      </div>
      <div class="row">
        <select id="session-select">
          <option value="" disabled selected>
            Select session...
          </option>
          ${this.sessions.map(s => html`
            <option value=${s.label}>
              ${s.label} (${s.date}, ${s.row_count} pts)
            </option>
          `)}
        </select>
        <button @click=${this._start}
          ?disabled=${this.loading}>
          ${this.loading ? '...' : 'LOAD'}
        </button>
      </div>
      ${this.sessions.length === 0 ? html`
        <div class="info">
          No replay sessions found.
          <button @click=${this._loadSessions}>REFRESH</button>
        </div>
      ` : ''}
    `;
  }

  private _renderPlayer() {
    const s = this.rs;
    const pct = s.maxEpoch > s.minEpoch
      ? ((s.currentEpoch - s.minEpoch)
         / (s.maxEpoch - s.minEpoch)) * 100
      : 0;

    const cur = this._fmtTime(s.currentEpoch);
    const start = this._fmtTime(s.minEpoch);
    const end = this._fmtTime(s.maxEpoch);
    const label = s.session?.label || '';
    const date = s.session?.date || '';

    return html`
      <div class="header">
        <span class="title">REPLAY: ${label}</span>
        <button class="stop" @click=${this._stop}>
          \u2716
        </button>
      </div>

      <div class="current-time">${date} ${cur} UTC</div>

      <div class="timeline">
        <input type="range"
          min=${s.minEpoch} max=${s.maxEpoch}
          .value=${String(Math.round(s.currentEpoch))}
          @input=${this._onSeek} />
        <div class="time-row">
          <span>${start}</span>
          <span>${end}</span>
        </div>
      </div>

      <div class="row" style="margin-top:6px">
        ${s.playing
          ? html`<button @click=${this._pause}>
              \u23F8 PAUSE
            </button>`
          : html`<button @click=${this._play}>
              \u25B6 PLAY
            </button>`
        }
        <button @click=${this._stepBack}
          ?disabled=${s.playing}>-15s</button>
        <button @click=${this._stepFwd}
          ?disabled=${s.playing}>+15s</button>
      </div>

      <div class="speed-row">
        <span>Speed:</span>
        ${[1, 5, 15, 30, 60].map(x => html`
          <button class="speed-btn
            ${s.speed === x ? ' active' : ''}"
            @click=${() => replayController.setSpeed(x)}>
            ${x}x
          </button>
        `)}
      </div>

      <div class="row" style="margin-top:6px; gap:4px">
        <button @click=${this._toggleExport}
          title="Compile visible window into a BlueSky .scn file"
        >${this._exportOpen ? '\u25BC' : '\u25B6'} EXPORT .SCN</button>
      </div>

      ${this._exportOpen ? this._renderExportForm() : nothing}
    `;
  }

  private _renderExportForm() {
    const s = this.rs;
    return html`
      <div class="export-form">
        <div class="row" style="gap:4px">
          <label>Name:</label>
          <input id="scn-name" type="text"
            .value=${this._exportName}
            @input=${(e: Event) => {
              this._exportName = (e.target as HTMLInputElement).value;
            }}
            placeholder="dfw-replay"
            style="flex:1; background:#111; color:#0f0;
                   border:1px solid #333; padding:2px 4px;
                   font-family:inherit; font-size:11px"
          />
        </div>
        <div class="row" style="gap:4px; font-size:10px; color:#888">
          <span>From: ${this._fmtTime(s.minEpoch)}</span>
          <span>To: ${this._fmtTime(s.currentEpoch)}</span>
        </div>
        <div class="row" style="gap:4px">
          <button @click=${this._doExport}
            ?disabled=${this._exporting || !this._exportName}>
            ${this._exporting ? 'Writing...' : 'Write .SCN'}
          </button>
          <button @click=${this._exportFullRange}
            ?disabled=${this._exporting || !this._exportName}>
            Full range
          </button>
        </div>
        ${this._exportResult ? html`
          <div style="color:${this._exportResult.startsWith('Error')
                                 ? '#f66' : '#0f0'};
                      font-size:10px; margin-top:2px">
            ${this._exportResult}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _toggleExport(): void {
    this._exportOpen = !this._exportOpen;
    if (this._exportOpen && !this._exportName) {
      const label = this.rs.session?.label || 'replay';
      const ts = this._fmtTime(this.rs.currentEpoch).replace(/:/g, '');
      this._exportName = `${label}-${ts}`;
    }
  }

  private async _doExport(
    startEpoch?: number,
    stopEpoch?: number,
  ): Promise<void> {
    if (!this.rs.session || this._exporting) return;
    this._exporting = true;
    this._exportResult = '';
    const label = this.rs.session.label;

    // Default window: session start to current scrubber position
    const start = startEpoch ?? this.rs.minEpoch;
    const stop = stopEpoch ?? Math.round(this.rs.currentEpoch);

    const params = new URLSearchParams({
      name: this._exportName,
      start_epoch: String(start),
      stop_epoch: String(stop),
    });
    try {
      const res = await fetch(
        `/api/surveillance/replay/${label}/to-scenario?${params}`,
        { method: 'POST' },
      );
      if (!res.ok) {
        const txt = await res.text();
        this._exportResult = `Error: ${txt.slice(0, 100)}`;
      } else {
        const data = await res.json();
        this._exportResult =
          `Wrote ${data.filename} — ${data.aircraft} aircraft, ${data.commands} commands`;
      }
    } catch (e: any) {
      this._exportResult = `Error: ${e.message}`;
    }
    this._exporting = false;
  }

  private _exportFullRange(): void {
    this._doExport(this.rs.minEpoch, this.rs.maxEpoch);
  }

  private _fmtTime(epoch: number): string {
    const d = new Date(epoch * 1000);
    return d.toISOString().slice(11, 19);
  }

  private async _start(): Promise<void> {
    const sel = this.renderRoot.querySelector(
      '#session-select',
    ) as HTMLSelectElement;
    if (!sel?.value) return;
    this.loading = true;
    await replayController.start(sel.value);
    this.loading = false;
  }

  private _stop(): void { replayController.stop(); }
  private _play(): void { replayController.play(); }
  private _pause(): void { replayController.pause(); }

  private _stepBack(): void {
    replayController.seek(this.rs.currentEpoch - 15);
  }
  private _stepFwd(): void {
    replayController.seek(this.rs.currentEpoch + 15);
  }

  private _onSeek(e: Event): void {
    const val = Number((e.target as HTMLInputElement).value);
    replayController.seek(val);
  }
}
