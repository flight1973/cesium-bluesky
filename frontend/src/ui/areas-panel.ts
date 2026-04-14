/**
 * Areas panel — list and manage all defined shapes.
 *
 * Shows every shape defined on the sim (Box, Poly, Circle)
 * with type, altitude band, and active status. Clicking a
 * shape makes it the active deletion area. Shapes can be
 * deleted. Altitude top/bottom can be edited (which
 * recreates the shape with new alts).
 *
 * BlueSky stores multiple shapes in basic_shapes but only
 * one can be the active deletion area at a time.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

interface ShapeInfo {
  name: string;
  type: string;
  coordinates: number[];
  top: number;
  bottom: number;
}

interface AreasResponse {
  shapes: Record<string, ShapeInfo>;
  active_area: string | null;
}

// BlueSky uses 1e9 as effective infinity.
const INFTY = 1e8;
const FT = 0.3048;

@customElement('areas-panel')
export class AreasPanel extends LitElement {
  @state() private shapes: Record<string, ShapeInfo> = {};
  @state() private activeArea: string | null = null;
  @state() private expandedName: string | null = null;
  @state() private editTop: Record<string, string> = {};
  @state() private editBot: Record<string, string> = {};

  private onCommand:
    ((cmd: string) => void) | null = null;
  private refreshTimer: number | null = null;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
      overflow-y: auto;
      width: 340px;
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
    .empty {
      padding: 12px 8px;
      color: #666;
      font-style: italic;
    }
    .shape {
      padding: 6px 8px;
      border-bottom: 1px solid #222;
    }
    .shape-row {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
    }
    .shape-name {
      flex: 1;
      font-weight: bold;
    }
    .shape-name.active {
      color: #ffff00;
    }
    .shape-name.active::before {
      content: '\\25C9 ';
    }
    .shape-type {
      color: #888;
      font-size: 10px;
    }
    .shape-details {
      margin-top: 4px;
      padding: 4px 0 4px 16px;
      color: #aaa;
      font-size: 11px;
    }
    .shape-details .row {
      padding: 1px 0;
    }
    .label { color: #888; }
    .coord-list {
      max-height: 100px;
      overflow-y: auto;
      font-size: 10px;
      color: #666;
      margin-top: 2px;
    }

    .actions {
      margin-top: 6px;
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    button {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 2px 6px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 10px;
    }
    button:hover {
      background: #00ff00;
      color: #000;
    }
    button.active {
      background: #00ff00;
      color: #000;
    }
    button.danger {
      color: #ff4444;
      border-color: #ff4444;
    }
    button.danger:hover {
      background: #ff4444;
      color: #000;
    }
    .alt-edit {
      display: flex;
      gap: 4px;
      align-items: center;
      margin-top: 4px;
    }
    .alt-edit input {
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      padding: 1px 4px;
      border-radius: 2px;
      font-family: inherit;
      font-size: 11px;
      width: 60px;
    }
    .alt-edit input:focus {
      border-color: #00ff00;
      outline: none;
    }
    .alt-edit .label {
      font-size: 10px;
    }
  `;

  render() {
    const names = Object.keys(this.shapes);
    return html`
      <div class="header">
        <span>Areas (${names.length})</span>
        <button class="close" @click=${this._close}>
          \u2715
        </button>
      </div>
      ${names.length === 0
        ? html`<div class="empty">No areas defined.</div>`
        : names.map(
            (name) => this._renderShape(
              this.shapes[name],
            ),
          )}
    `;
  }

  setCommandHandler(
    handler: (cmd: string) => void,
  ): void {
    this.onCommand = handler;
  }

  /** Show the panel and start refreshing. */
  open(): void {
    this.hidden = false;
    this._refresh();
    this._stopRefresh();
    this.refreshTimer = window.setInterval(
      () => this._refresh(), 2000,
    );
  }

  /** Hide the panel. */
  close(): void {
    this.hidden = true;
    this._stopRefresh();
    this.dispatchEvent(
      new CustomEvent('panel-close', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ── Private ──────────────────────────────────────

  private _close(): void {
    this.close();
  }

  private _renderShape(shape: ShapeInfo) {
    const isActive = shape.name === this.activeArea;
    const expanded = this.expandedName === shape.name;
    return html`
      <div class="shape">
        <div class="shape-row"
          @click=${() => this._toggleExpand(shape.name)}
        >
          <span class="shape-name
            ${isActive ? 'active' : ''}"
          >${shape.name}</span>
          <span class="shape-type">
            ${shape.type}
          </span>
          <span class="label">
            ${expanded ? '\u25BC' : '\u25B6'}
          </span>
        </div>
        ${expanded
          ? this._renderDetails(shape, isActive)
          : nothing}
      </div>
    `;
  }

  private _renderDetails(
    shape: ShapeInfo,
    isActive: boolean,
  ) {
    const topStr = this._fmtAlt(shape.top, true);
    const botStr = this._fmtAlt(shape.bottom, false);
    const coords = this._fmtCoords(shape);
    return html`
      <div class="shape-details">
        <div class="row">
          <span class="label">Top:</span> ${topStr}
          &nbsp;
          <span class="label">Bottom:</span> ${botStr}
        </div>
        <div class="row">
          <span class="label">Coords:</span>
        </div>
        <div class="coord-list">${coords}</div>

        <div class="alt-edit">
          <span class="label">Edit alt:</span>
          <input
            placeholder="top"
            .value=${this.editTop[shape.name] || ''}
            @input=${(e: Event) => this._onEditTop(
              shape.name, e,
            )}
          />
          <input
            placeholder="bot"
            .value=${this.editBot[shape.name] || ''}
            @input=${(e: Event) => this._onEditBot(
              shape.name, e,
            )}
          />
          <button @click=${() => this._applyAlts(shape)}>
            APPLY
          </button>
        </div>

        <div class="actions">
          ${isActive
            ? html`<button class="active"
                @click=${this._deactivate}
              >DEACTIVATE</button>`
            : html`<button
                @click=${() => this._activate(
                  shape.name,
                )}
              >ACTIVATE</button>`}
          <button class="danger"
            @click=${() => this._delete(shape.name)}
          >DELETE</button>
        </div>
      </div>
    `;
  }

  private _fmtAlt(
    val: number,
    isTop: boolean,
  ): string {
    if (Math.abs(val) > INFTY) {
      return isTop
        ? 'unbounded (Kármán line)'
        : 'surface (0)';
    }
    const ft = val / FT;
    if (ft >= 5000) {
      return `FL${Math.round(ft / 100)}`;
    }
    return `${Math.round(ft)} ft (${val.toFixed(0)} m)`;
  }

  private _fmtCoords(shape: ShapeInfo): string {
    const c = shape.coordinates;
    if (shape.type === 'Box' && c.length >= 4) {
      return `(${c[0].toFixed(4)}, ${c[1].toFixed(4)}) ` +
        `- (${c[2].toFixed(4)}, ${c[3].toFixed(4)})`;
    }
    // Circle: [lat, lon, radius]
    if (shape.type === 'Circle' && c.length >= 3) {
      return `center (${c[0].toFixed(4)}, ` +
        `${c[1].toFixed(4)}), r=${c[2].toFixed(2)}`;
    }
    // Poly — list vertices.
    const pairs: string[] = [];
    for (let i = 0; i < c.length - 1; i += 2) {
      pairs.push(
        `(${c[i].toFixed(4)}, ${c[i + 1].toFixed(4)})`,
      );
    }
    return pairs.join(', ');
  }

  private _toggleExpand(name: string): void {
    this.expandedName =
      this.expandedName === name ? null : name;
  }

  private _activate(name: string): void {
    this.onCommand?.(`AREA ${name}`);
    setTimeout(() => this._refresh(), 500);
  }

  private _deactivate(): void {
    this.onCommand?.('AREA OFF');
    setTimeout(() => this._refresh(), 500);
  }

  private _delete(name: string): void {
    this.onCommand?.(`DEL ${name}`);
    this.expandedName = null;
    setTimeout(() => this._refresh(), 500);
  }

  private _onEditTop(name: string, e: Event): void {
    this.editTop = {
      ...this.editTop,
      [name]: (e.target as HTMLInputElement).value,
    };
  }

  private _onEditBot(name: string, e: Event): void {
    this.editBot = {
      ...this.editBot,
      [name]: (e.target as HTMLInputElement).value,
    };
  }

  /**
   * Apply altitude edits by deleting and re-creating the
   * shape with the new top/bottom. BlueSky shapes aren't
   * mutable so we have to recreate.
   */
  private _applyAlts(shape: ShapeInfo): void {
    const top = this.editTop[shape.name] || '';
    const bot = this.editBot[shape.name] || '';
    if (!top && !bot) return;

    const wasActive = shape.name === this.activeArea;

    // Reconstruct the create command with new alts.
    const c = shape.coordinates;
    let createCmd: string | null = null;
    const t = top || '100000';
    const b = bot || '0';

    if (shape.type === 'Box' && c.length >= 4) {
      createCmd =
        `BOX ${shape.name},` +
        `${c[0]},${c[1]},${c[2]},${c[3]},` +
        `${t},${b}`;
    } else if (shape.type === 'Circle' && c.length >= 3) {
      createCmd =
        `CIRCLE ${shape.name},` +
        `${c[0]},${c[1]},${c[2]},${t},${b}`;
    } else if (shape.type === 'Poly') {
      const coordStr = [];
      for (let i = 0; i < c.length - 1; i += 2) {
        coordStr.push(`${c[i]},${c[i + 1]}`);
      }
      createCmd =
        `POLYALT ${shape.name},${t},${b},` +
        coordStr.join(',');
    }

    if (!createCmd) return;

    // Delete old, create new, restore active state.
    this.onCommand?.(`DEL ${shape.name}`);
    setTimeout(() => this.onCommand?.(createCmd!), 100);
    if (wasActive) {
      setTimeout(
        () => this.onCommand?.(`AREA ${shape.name}`),
        300,
      );
    }

    // Clear edit fields and refresh.
    this.editTop = {
      ...this.editTop, [shape.name]: '',
    };
    this.editBot = {
      ...this.editBot, [shape.name]: '',
    };
    setTimeout(() => this._refresh(), 800);
  }

  private async _refresh(): Promise<void> {
    try {
      const res = await fetch('/api/areas');
      if (!res.ok) return;
      const data: AreasResponse = await res.json();
      this.shapes = data.shapes || {};
      this.activeArea = data.active_area;
    } catch {
      // Non-fatal.
    }
  }

  private _stopRefresh(): void {
    if (this.refreshTimer !== null) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }
}
