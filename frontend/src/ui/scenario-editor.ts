/**
 * Scenario editor — text-mode editing of .scn files.
 *
 * Layout:
 *   ┌──────────────────────────────────────┐
 *   │ Scenario Editor            [close]    │
 *   │ File: [my_scen.scn ▾] [NEW] [LOAD]   │
 *   │ Versions: [v1] [v2] [v3 (current)]   │
 *   ├──────────────────────────────────────┤
 *   │  1 # Scenario: my flight              │
 *   │  2 00:00:00>CRE KL204 B738 ...        │
 *   │  3 00:00:10>ADDWPT KL204 EHAM         │
 *   │  4 00:00:30>LNAV KL204 ON             │
 *   │  ...                                  │
 *   ├──────────────────────────────────────┤
 *   │ [SAVE] [SAVE AS NEW VERSION] [LOAD]  │
 *   └──────────────────────────────────────┘
 *
 * Edits the raw text of the file directly.  Preserves
 * comments, blank lines, and formatting.  Syntax is
 * simply: ``HH:MM:SS.hh>command`` per line.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, query } from 'lit/decorators.js';

interface VersionInfo {
  filename: string;
  size: number;
  mtime: number;
  writable: boolean;
}

@customElement('scenario-editor')
export class ScenarioEditor extends LitElement {
  @state() private currentFile = '';
  @state() private text = '';
  @state() private writable = true;
  @state() private versions: VersionInfo[] = [];
  @state() private dirty = false;
  @query('#editor') private editor!: HTMLTextAreaElement;

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
      width: 600px;
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
    .file-row input {
      flex: 1;
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      padding: 2px 6px;
      font-family: inherit;
      font-size: 12px;
      border-radius: 2px;
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

    .editor-wrap {
      flex: 1;
      display: flex;
      overflow: hidden;
      background: #0a0a0a;
    }
    .line-gutter {
      padding: 6px 6px;
      color: #555;
      font-size: 11px;
      text-align: right;
      user-select: none;
      background: #111;
      border-right: 1px solid #222;
      overflow: hidden;
      white-space: pre;
      min-width: 38px;
    }
    textarea {
      flex: 1;
      background: transparent;
      color: #00ff00;
      border: none;
      outline: none;
      resize: none;
      padding: 6px 8px;
      font-family: inherit;
      font-size: 12px;
      line-height: 1.4;
      white-space: pre;
      overflow: auto;
      tab-size: 4;
    }
    textarea:focus { outline: none; }

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

    label { color: #888; font-size: 11px; }
    .dirty-marker {
      color: #ffa000;
      margin-left: 4px;
    }
    .readonly {
      color: #ffa000;
      font-size: 10px;
      font-style: italic;
      padding: 4px 8px;
    }
  `;

  render() {
    const lineCount = this.text.split('\n').length;
    const gutter = Array.from(
      { length: lineCount },
      (_, i) => String(i + 1),
    ).join('\n');

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

      <div class="editor-wrap">
        <pre class="line-gutter">${gutter}</pre>
        <textarea
          id="editor"
          .value=${this.text}
          @input=${(e: Event) => {
            this.text =
              (e.target as HTMLTextAreaElement).value;
            this.dirty = true;
          }}
          @keydown=${this._onKey}
          spellcheck="false"
          placeholder="# Scenario commands here
00:00:00>CRE KL204 B738 52.3 4.76 180 FL350 280
00:00:10>ADDWPT KL204 EHAM
00:00:30>LNAV KL204 ON"
        ></textarea>
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

  async loadFile(filename: string): Promise<void> {
    this.currentFile = filename;
    try {
      const res = await fetch(
        `/api/scenarios/text?filename=${
          encodeURIComponent(filename)
        }`,
      );
      if (!res.ok) {
        alert(`Failed to load ${filename}`);
        return;
      }
      const data = await res.json();
      this.text = data.text || '';
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
    this.text = '# New scenario\n00:00:00>';
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

  /** Handle Tab key to insert spaces instead of
   *  switching focus. */
  private _onKey(e: KeyboardEvent): void {
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.target as HTMLTextAreaElement;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const insert = '    ';
      this.text =
        this.text.substring(0, start)
        + insert
        + this.text.substring(end);
      this.dirty = true;
      // Restore cursor after the tab.
      this.updateComplete.then(() => {
        el.selectionStart =
          el.selectionEnd = start + insert.length;
      });
    }
  }

  private async _save(): Promise<void> {
    try {
      const res = await fetch(
        '/api/scenarios/save-text',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            filename: this.currentFile,
            text: this.text,
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
    // Figure out next version name, then save-text to it.
    const stem = this.currentFile
      .replace(/\.scn$/i, '')
      .replace(/_v\d+$/i, '');
    let nextV = 2;
    for (const v of this.versions) {
      const m = v.filename.match(/_v(\d+)\.scn$/i);
      if (m) {
        nextV = Math.max(nextV, parseInt(m[1]) + 1);
      }
    }
    const newName = `${stem}_v${nextV}.scn`;
    try {
      const res = await fetch(
        '/api/scenarios/save-text',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            filename: newName,
            text: this.text,
            overwrite: false,
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
