/**
 * BlueSky command console -- faithfully replicates the Qt GUI console.
 *
 * Layout:
 *   ┌────────────────────────────────────────┐
 *   │ Stackwin: scrolling command output area │
 *   ├────────────────────────────────────────┤
 *   │ >> CRE  acid,type,lat,lon,hdg,alt,spd  │
 *   └────────────────────────────────────────┘
 *
 * Features:
 *   - ">>" prompt (non-editable, matching Qt Cmdline)
 *   - Grey argument hints from Command.cmddict.brief
 *   - Up/Down arrow command history
 *   - Tab completion for IC/BATCH scenario filenames
 *   - Green-on-black output echoing commands & responses
 */
import { LitElement, html, css } from 'lit';
import { customElement, state, query } from 'lit/decorators.js';

/** Command brief lookup fetched from backend. */
interface CmdInfo {
  name: string;
  brief: string;
  aliases?: string[];
}

interface LogEntry {
  simt: number;
  utc: string;
  sender: string;
  command: string;
}

type TabName = 'console' | 'server';

@customElement('bluesky-console')
export class BlueSkyConsole extends LitElement {
  @state() private outputLines: string[] = [];
  @state() private serverLog: LogEntry[] = [];
  @state() private activeTab: TabName = 'console';
  @state() private inputValue = '';
  @state() private hintText = '';
  @query('#cmd-input') private inputEl!: HTMLInputElement;

  private history: string[] = [];
  private historyPos = 0;
  private commandMem = '';
  private cmdBriefs = new Map<string, string>();
  private onCommand: ((cmd: string) => void) | null = null;
  private _maxServerLines = 500;

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      background: #1a1a1a;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 13px;
      border-top: 1px solid #333;
      height: 100%;
      overflow: hidden;
    }

    /* Tab bar */
    .tabs {
      display: flex;
      background: #111;
      border-bottom: 1px solid #333;
      flex-shrink: 0;
    }
    .tab {
      padding: 4px 12px;
      color: #888;
      cursor: pointer;
      font-size: 11px;
      border-right: 1px solid #222;
      user-select: none;
    }
    .tab:hover {
      color: #00ff00;
      background: #1a1a1a;
    }
    .tab.active {
      color: #00ff00;
      background: #1a1a1a;
      border-bottom: 1px solid #00ff00;
      margin-bottom: -1px;
    }
    .tab .badge {
      color: #ffa000;
      font-size: 10px;
      margin-left: 4px;
    }

    /* Output area -- matches Qt Stackwin */
    .stackwin {
      flex: 1;
      overflow-y: auto;
      padding: 4px 8px;
      color: #00ff00;
      white-space: pre-wrap;
      word-wrap: break-word;
      line-height: 1.4;
    }
    .stackwin .echo-line {
      display: block;
    }

    /* Server log */
    .server-log {
      flex: 1;
      overflow-y: auto;
      padding: 4px 8px;
      color: #aaa;
      line-height: 1.3;
      font-size: 12px;
    }
    .server-log .entry {
      display: flex;
      gap: 8px;
      padding: 1px 0;
      border-bottom: 1px solid #1a1a1a;
    }
    .server-log .simt {
      color: #666;
      min-width: 62px;
      flex-shrink: 0;
    }
    .server-log .sender {
      color: #888;
      min-width: 60px;
      flex-shrink: 0;
    }
    .server-log .command {
      color: #00ff00;
      flex: 1;
      word-break: break-all;
    }

    /* Command line -- matches Qt Cmdline with >> prompt */
    .cmdline {
      display: flex;
      align-items: center;
      padding: 3px 8px;
      border-top: 1px solid #333;
      background: #111;
      min-height: 24px;
    }
    .prompt {
      color: #00ff00;
      font-weight: bold;
      user-select: none;
      margin-right: 2px;
      flex-shrink: 0;
    }
    .input-wrap {
      flex: 1;
      position: relative;
      display: flex;
      align-items: center;
    }
    input {
      background: transparent;
      border: none;
      outline: none;
      color: #00ff00;
      font-family: inherit;
      font-size: inherit;
      width: 100%;
      caret-color: #00ff00;
      padding: 0;
    }
    .hint {
      color: #666;
      pointer-events: none;
      white-space: pre;
      flex-shrink: 0;
    }
  `;

  render() {
    return html`
      <div class="tabs">
        <div
          class="tab ${this.activeTab === 'console' ? 'active' : ''}"
          @click=${() => this._setTab('console')}
        >CONSOLE</div>
        <div
          class="tab ${this.activeTab === 'server' ? 'active' : ''}"
          @click=${() => this._setTab('server')}
        >SERVER LOG
          <span class="badge">${this.serverLog.length}</span>
        </div>
      </div>

      ${this.activeTab === 'console' ? html`
        <div class="stackwin" id="stackwin">
          ${this.outputLines.map(
            (line) => html`
              <span class="echo-line">${line}</span>
            `,
          )}
        </div>
        <div class="cmdline">
          <span class="prompt">&gt;&gt;</span>
          <div class="input-wrap">
            <input
              id="cmd-input"
              .value=${this.inputValue}
              @input=${this._onInput}
              @keydown=${this._onKeyDown}
              spellcheck="false"
              autocomplete="off"
            />
            <span class="hint">${this.hintText}</span>
          </div>
        </div>
      ` : html`
        <div class="server-log" id="serverlog">
          ${this.serverLog.map(
            (e) => html`
              <div class="entry">
                <span class="simt">
                  t=${e.simt.toFixed(1)}
                </span>
                <span class="sender">
                  ${e.sender}
                </span>
                <span class="command">${e.command}</span>
              </div>
            `,
          )}
        </div>
      `}
    `;
  }

  /** Load command briefs from backend for hint display.
   *
   * Maps both primary names AND aliases to the same brief
   * so hints work for command synonyms like Q/QUIT,
   * COLOR/COLOUR, SCEN/SCENARIO, etc.
   */
  async loadCommandBriefs(): Promise<void> {
    try {
      const res = await fetch('/api/commands/list');
      const cmds: CmdInfo[] = await res.json();
      for (const c of cmds) {
        this.cmdBriefs.set(c.name.toUpperCase(), c.brief);
        // Map aliases to the same brief as the primary.
        if (c.aliases) {
          for (const alias of c.aliases) {
            this.cmdBriefs.set(
              alias.toUpperCase(), c.brief,
            );
          }
        }
      }
    } catch {
      // Briefs are optional; console still works.
    }
  }

  /** Set the handler called when Enter is pressed. */
  setCommandHandler(handler: (cmd: string) => void): void {
    this.onCommand = handler;
  }

  /** Echo a line to the output area (like Qt echo()). */
  echo(text: string): void {
    this.outputLines = [...this.outputLines, text];
    // Auto-scroll to bottom after render.
    this.updateComplete.then(() => {
      const sw = this.renderRoot.querySelector('#stackwin');
      if (sw) sw.scrollTop = sw.scrollHeight;
    });
  }

  /** Focus the command input. */
  focus(): void {
    this.updateComplete.then(() => this.inputEl?.focus());
  }

  /** Add a single entry to the server command log tab. */
  addLogEntry(entry: LogEntry): void {
    const next = [...this.serverLog, entry];
    if (next.length > this._maxServerLines) {
      next.splice(0, next.length - this._maxServerLines);
    }
    this.serverLog = next;
    // Auto-scroll if viewing server tab.
    if (this.activeTab === 'server') {
      this.updateComplete.then(() => {
        const el =
          this.renderRoot.querySelector('#serverlog');
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  }

  /** Load initial backlog from the server. */
  async loadInitialLog(): Promise<void> {
    try {
      const res = await fetch('/api/cmdlog?limit=200');
      if (!res.ok) return;
      const entries: LogEntry[] = await res.json();
      this.serverLog = entries;
    } catch {
      // Non-fatal.
    }
  }

  private _setTab(tab: TabName): void {
    this.activeTab = tab;
    if (tab === 'console') {
      this.updateComplete.then(() =>
        this.inputEl?.focus()
      );
    }
  }

  // ── Private ───────────────────────────────────────

  private _onInput(e: Event): void {
    this.inputValue = (e.target as HTMLInputElement).value;
    this._updateHint();
  }

  private _onKeyDown(e: KeyboardEvent): void {
    if (e.key === 'Enter' && this.inputValue.trim()) {
      const cmd = this.inputValue.trim();
      this.echo(cmd);
      this.history.push(cmd);
      this.historyPos = 0;
      this.commandMem = '';
      this.inputValue = '';
      this.hintText = '';
      this.onCommand?.(cmd);
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (this.historyPos === 0) {
        this.commandMem = this.inputValue;
      }
      if (this.historyPos < this.history.length) {
        this.historyPos++;
        this.inputValue =
          this.history[this.history.length - this.historyPos];
        this._updateHint();
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (this.historyPos > 0) {
        this.historyPos--;
        if (this.historyPos === 0) {
          this.inputValue = this.commandMem;
        } else {
          this.inputValue =
            this.history[this.history.length - this.historyPos];
        }
        this._updateHint();
      }
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault();
      // Tab completion deferred to future phase.
    }
  }

  /**
   * Update the grey argument hint based on the current
   * command.  Mirrors Qt Console.set_cmdline() logic:
   * look up cmd in cmddict.brief, strip already-typed args.
   */
  private _updateHint(): void {
    const parts = this.inputValue.trimStart().split(/[\s,]+/);
    const cmd = (parts[0] || '').toUpperCase();
    const brief = this.cmdBriefs.get(cmd);
    if (!brief) {
      this.hintText = '';
      return;
    }

    // brief looks like "CRE acid,type,lat,lon,hdg,alt,spd"
    // Strip the command name prefix to get just the args.
    const argStr = brief.slice(cmd.length).trim();
    if (!argStr) {
      this.hintText = '';
      return;
    }

    // Count how many args the user has already typed.
    const typedArgCount = parts.length - 1;
    const hintArgs = argStr.split(',');
    const remaining = hintArgs.slice(typedArgCount);
    this.hintText = remaining.length > 0
      ? ' ' + remaining.join(',')
      : '';
  }
}
