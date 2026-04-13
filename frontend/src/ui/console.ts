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
}

@customElement('bluesky-console')
export class BlueSkyConsole extends LitElement {
  @state() private outputLines: string[] = [];
  @state() private inputValue = '';
  @state() private hintText = '';
  @query('#cmd-input') private inputEl!: HTMLInputElement;

  private history: string[] = [];
  private historyPos = 0;
  private commandMem = '';
  private cmdBriefs = new Map<string, string>();
  private onCommand: ((cmd: string) => void) | null = null;

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
      <div class="stackwin" id="stackwin">
        ${this.outputLines.map(
          (line) => html`<span class="echo-line">${line}</span>`,
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
    `;
  }

  /** Load command briefs from backend for hint display. */
  async loadCommandBriefs(): Promise<void> {
    try {
      const res = await fetch('/api/commands/list');
      const cmds: CmdInfo[] = await res.json();
      for (const c of cmds) {
        this.cmdBriefs.set(c.name.toUpperCase(), c.brief);
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
