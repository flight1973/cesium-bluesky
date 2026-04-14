/**
 * Scenario editor — create and edit versioned .scn files.
 *
 * Layout:
 *   ┌──────────────────────────────────────┐
 *   │ Scenario Editor            [close]    │
 *   │ File: [my_scen.scn ▾] [NEW] [LOAD]   │
 *   │ Versions: [v1] [v2] [v3 (current)]   │
 *   ├──────────────────────────────────────┤
 *   │ Time      Command              [del] │
 *   │ 00:00:00  CRE KL204 B738 ...   [✕]  │
 *   │ 00:00:10  ADDWPT KL204 EHAM    [✕]  │
 *   │ 00:00:30  LNAV KL204 ON        [✕]  │
 *   │ ...                                   │
 *   ├──────────────────────────────────────┤
 *   │ [time] [command]            [+ ADD]  │
 *   ├──────────────────────────────────────┤
 *   │ [SAVE] [SAVE AS NEW VER] [LOAD SIM]  │
 *   └──────────────────────────────────────┘
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, query } from 'lit/decorators.js';

interface Entry {
  time: number;
  command: string;
}

interface VersionInfo {
  filename: string;
  size: number;
  mtime: number;
  writable: boolean;
}

@customElement('scenario-editor')
export class ScenarioEditor extends LitElement {
  @state() private currentFile = '';
  @state() private entries: Entry[] = [];
  @state() private writable = true;
  @state() private versions: VersionInfo[] = [];
  @state() private dirty = false;
  @state() private newTime = '00:00:00';
  @state() private newCmd = '';
  @query('#new-cmd') private newCmdInput!: HTMLInputElement;

  private onCommand:
    ((cmd: string) => void) | null = null;

  static styles = css`
    :host([hidden]) { display: none !important; }
    :host {
      display: flex;
      flex-direction: column;
      background: rgba(0, 0, 0, 0.95);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
      width: 500px;
      height: 100%;
      overflow: hidden;
    }

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

    .section {
      padding: 6px 8px;
      border-bottom: 1px solid #222;
      flex-shrink: 0;
    }

    .file-row {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .versions {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 4px;
    }
    .version-btn {
      background: #222;
      color: #888;
      border: 1px solid #444;
      padding: 1px 6px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 10px;
    }
    .version-btn:hover {
      background: #00ff00;
      color: #000;
    }
    .version-btn.current {
      color: #00ff00;
      border-color: #00ff00;
    }

    .entries {
      flex: 1;
      overflow-y: auto;
      padding: 4px 0;
    }
    .entry-row {
      display: flex;
      gap: 6px;
      padding: 2px 8px;
      align-items: center;
      border-bottom: 1px solid #111;
    }
    .entry-row:hover { background: #111; }
    .entry-time {
      color: #888;
      font-size: 11px;
      min-width: 75px;
      flex-shrink: 0;
    }
    .entry-cmd {
      flex: 1;
      color: #00ff00;
      font-size: 11px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
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
      border-top: 1px solid #222;
      flex-shrink: 0;
    }
    .add-row input {
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      padding: 2px 6px;
      font-family: inherit;
      font-size: 12px;
      border-radius: 2px;
    }
    .add-row input.time { width: 80px; }
    .add-row input.cmd { flex: 1; }

    .actions {
      display: flex;
      gap: 6px;
      padding: 6px 8px;
      border-top: 1px solid #333;
      flex-shrink: 0;
    }

    button.cmd-btn {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 3px 10px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    button.cmd-btn:hover {
      background: #00ff00;
      color: #000;
    }
    button.cmd-btn:disabled {
      color: #555;
      border-color: #444;
      cursor: not-allowed;
      background: #111;
    }
    button.cmd-btn.danger {
      color: #ff4444;
      border-color: #ff4444;
    }
    button.cmd-btn.danger:hover {
      background: #ff4444;
      color: #000;
    }

    label {
      color: #888;
      font-size: 11px;
    }
    .dirty-marker {
      color: #ffa000;
      margin-left: 4px;
    }
    .readonly {
      color: #ffa000;
      font-size: 10px;
      font-style: italic;
    }
  `;

  render() {
    return html`
      <div class="header">
        <span>
          Scenario Editor
          ${this.dirty
            ? html`<span class="dirty-marker">\u25CF</span>`
            : nothing}
        </span>
        <button class="close" @click=${this._close}>
          \u2715
        </button>
      </div>

      <div class="section">
        <div class="file-row">
          <label>File:</label>
          <input
            style="flex:1; background:#222; border:1px solid
              #444; color:#00ff00; padding:2px 6px;
              font-family:inherit; font-size:12px;"
            .value=${this.currentFile}
            placeholder="my_scenario.scn"
            @input=${(e: Event) => {
              this.currentFile =
                (e.target as HTMLInputElement).value;
              this._refreshVersions();
            }}
          />
          <button class="cmd-btn" @click=${this._new}>
            NEW
          </button>
          <button class="cmd-btn" @click=${this._load}>
            LOAD
          </button>
        </div>
        ${this.versions.length > 0 ? html`
          <div class="versions">
            <label>Versions:</label>
            ${this.versions.map((v) => html`
              <button
                class="version-btn
                  ${v.filename === this.currentFile
                    ? 'current' : ''}"
                @click=${() => this._loadVersion(v)}
                title="${new Date(v.mtime * 1000)
                  .toLocaleString()} — ${v.size} bytes"
              >${v.filename}</button>
            `)}
          </div>
        ` : nothing}
        ${!this.writable ? html`
          <div class="readonly">
            Read-only (built-in scenario) — use Save As
            New Version to modify
          </div>
        ` : nothing}
      </div>

      <div class="entries">
        ${this.entries.length === 0
          ? html`<div style="padding:12px; color:#666">
              No entries. Add commands below.
            </div>`
          : this.entries.map(
              (e, i) => html`
                <div class="entry-row">
                  <input
                    class="entry-time"
                    .value=${this._fmtTime(e.time)}
                    @change=${(ev: Event) =>
                      this._editTime(i, ev)}
                  />
                  <input
                    class="entry-cmd"
                    style="background:transparent;
                      border:none; color:#00ff00;
                      font-family:inherit; font-size:11px;"
                    .value=${e.command}
                    @change=${(ev: Event) =>
                      this._editCmd(i, ev)}
                  />
                  <button class="del-btn"
                    @click=${() => this._deleteEntry(i)}
                  >\u2715</button>
                </div>
              `,
            )}
      </div>

      <div class="add-row">
        <input class="time"
          .value=${this.newTime}
          placeholder="HH:MM:SS"
          @input=${(e: Event) => {
            this.newTime =
              (e.target as HTMLInputElement).value;
          }}
        />
        <input id="new-cmd" class="cmd"
          .value=${this.newCmd}
          placeholder="command (e.g. CRE ...)"
          @input=${(e: Event) => {
            this.newCmd =
              (e.target as HTMLInputElement).value;
          }}
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter') this._addEntry();
          }}
        />
        <button class="cmd-btn" @click=${this._addEntry}>
          + ADD
        </button>
      </div>

      <div class="actions">
        <button class="cmd-btn"
          @click=${this._save}
          ?disabled=${!this.currentFile}
        >SAVE</button>
        <button class="cmd-btn"
          @click=${this._saveAsVersion}
          ?disabled=${!this.currentFile}
        >SAVE AS NEW VERSION</button>
        <button class="cmd-btn"
          @click=${this._loadIntoSim}
          ?disabled=${!this.currentFile}
        >LOAD INTO SIM</button>
      </div>
    `;
  }

  setCommandHandler(
    handler: (cmd: string) => void,
  ): void {
    this.onCommand = handler;
  }

  open(): void {
    this.hidden = false;
  }

  close(): void {
    if (this.dirty && !confirm(
      'Unsaved changes. Close anyway?',
    )) return;
    this.hidden = true;
    this.dispatchEvent(
      new CustomEvent('panel-close', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Load a scenario by filename. */
  async loadFile(filename: string): Promise<void> {
    this.currentFile = filename;
    try {
      const res = await fetch(
        `/api/scenarios/content?filename=${
          encodeURIComponent(filename)
        }`,
      );
      if (!res.ok) {
        alert(`Failed to load ${filename}`);
        return;
      }
      const data = await res.json();
      this.entries = data.entries || [];
      this.writable = !!data.writable;
      this.dirty = false;
      await this._refreshVersions();
    } catch (e) {
      alert(`Error loading scenario: ${e}`);
    }
  }

  // ── Private ──────────────────────────────────────

  private _close(): void {
    this.close();
  }

  private _new(): void {
    if (this.dirty && !confirm(
      'Discard unsaved changes?',
    )) return;
    this.currentFile = 'untitled.scn';
    this.entries = [];
    this.writable = true;
    this.versions = [];
    this.dirty = false;
  }

  private async _load(): Promise<void> {
    const fname = this.currentFile;
    if (!fname) return;
    if (this.dirty && !confirm(
      'Discard unsaved changes?',
    )) return;
    await this.loadFile(fname);
  }

  private async _loadVersion(
    v: VersionInfo,
  ): Promise<void> {
    if (this.dirty && !confirm(
      'Discard unsaved changes?',
    )) return;
    await this.loadFile(v.filename);
  }

  private async _refreshVersions(): Promise<void> {
    const stem = (this.currentFile || '')
      .replace(/\.scn$/i, '')
      .replace(/_v\d+$/i, '');
    if (!stem) {
      this.versions = [];
      return;
    }
    try {
      const res = await fetch(
        `/api/scenarios/versions?stem=${
          encodeURIComponent(stem)
        }`,
      );
      if (res.ok) {
        this.versions = await res.json();
      }
    } catch {
      this.versions = [];
    }
  }

  private _parseTime(s: string): number {
    const m = s.match(
      /^(\d+):(\d+):(\d+)(?:\.(\d+))?$/,
    );
    if (!m) return 0;
    const [, h, mm, ss, frac] = m;
    let t = (
      parseInt(h) * 3600
      + parseInt(mm) * 60
      + parseInt(ss)
    );
    if (frac) t += parseFloat(`0.${frac}`);
    return t;
  }

  private _fmtTime(t: number): string {
    const h = Math.floor(t / 3600);
    const m = Math.floor((t % 3600) / 60);
    const s = t - h * 3600 - m * 60;
    return `${String(h).padStart(2, '0')}:`
      + `${String(m).padStart(2, '0')}:`
      + `${s.toFixed(2).padStart(5, '0')}`;
  }

  private _editTime(i: number, e: Event): void {
    const t = this._parseTime(
      (e.target as HTMLInputElement).value,
    );
    this.entries = this.entries.map(
      (entry, idx) => idx === i
        ? { ...entry, time: t } : entry,
    );
    this.dirty = true;
  }

  private _editCmd(i: number, e: Event): void {
    const cmd = (e.target as HTMLInputElement).value;
    this.entries = this.entries.map(
      (entry, idx) => idx === i
        ? { ...entry, command: cmd } : entry,
    );
    this.dirty = true;
  }

  private _deleteEntry(i: number): void {
    this.entries = this.entries.filter(
      (_, idx) => idx !== i,
    );
    this.dirty = true;
  }

  private _addEntry(): void {
    const cmd = this.newCmd.trim();
    if (!cmd) return;
    const t = this._parseTime(this.newTime);
    this.entries = [
      ...this.entries,
      { time: t, command: cmd },
    ].sort((a, b) => a.time - b.time);
    this.newCmd = '';
    this.dirty = true;
    this.newCmdInput?.focus();
  }

  private async _save(): Promise<void> {
    try {
      const res = await fetch(
        '/api/scenarios/save',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            filename: this.currentFile,
            entries: this.entries,
            overwrite: true,
          }),
        },
      );
      const data = await res.json();
      if (res.ok) {
        this.currentFile = data.filename;
        this.dirty = false;
        await this._refreshVersions();
      } else {
        alert(`Save failed: ${data.detail}`);
      }
    } catch (e) {
      alert(`Save error: ${e}`);
    }
  }

  private async _saveAsVersion(): Promise<void> {
    try {
      const res = await fetch(
        '/api/scenarios/versions',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            filename: this.currentFile,
            entries: this.entries,
          }),
        },
      );
      const data = await res.json();
      if (res.ok) {
        this.currentFile = data.filename;
        this.dirty = false;
        await this._refreshVersions();
      } else {
        alert(`Save failed: ${data.detail}`);
      }
    } catch (e) {
      alert(`Save error: ${e}`);
    }
  }

  private _loadIntoSim(): void {
    if (!this.currentFile) return;
    this.onCommand?.(`IC ${this.currentFile}`);
  }
}
