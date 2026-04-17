/**
 * Settings popup with a unit-system toggle.
 *
 * Rendered as a gear icon in the top-right of the viewport.
 * Clicking opens a small dropdown where the user picks
 * aviation (kt/ft), SI (m/s/m), or imperial (mph/ft).  The
 * choice is persisted via the units service; components
 * that depend on it subscribe to `units-changed`.
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import {
  getUnits, setUnits, onUnitsChange,
} from '../services/units';
import type { UnitSystem } from '../types';

@customElement('settings-panel')
export class SettingsPanel extends LitElement {
  @state() private open = false;
  @state() private units: UnitSystem = getUnits();
  private unsub: (() => void) | null = null;

  static styles = css`
    :host {
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 100;
      font-family: 'Consolas', 'Courier New', monospace;
    }
    .gear {
      width: 32px;
      height: 32px;
      background: rgba(0, 0, 0, 0.7);
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 4px;
      cursor: pointer;
      font-size: 18px;
      display: flex;
      align-items: center;
      justify-content: center;
      user-select: none;
    }
    .gear:hover { background: #00ff00; color: #000; }
    .menu {
      margin-top: 4px;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 4px;
      padding: 8px 10px;
      min-width: 180px;
      font-size: 12px;
    }
    .row { margin: 4px 0; }
    .title {
      color: #888;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }
    label {
      display: block;
      padding: 3px 0;
      cursor: pointer;
    }
    label:hover { color: #00ff00; }
    input[type=radio] {
      accent-color: #00ff00;
      margin-right: 6px;
    }
    .unit-desc { color: #666; font-size: 10px; }
    .doc-link {
      display: block;
      color: #66d9ef;
      text-decoration: none;
      padding: 3px 0;
    }
    .doc-link:hover { color: #00ff00; }
  `;

  connectedCallback(): void {
    super.connectedCallback();
    this.unsub = onUnitsChange((u) => {
      this.units = u;
    });
  }

  disconnectedCallback(): void {
    this.unsub?.();
    super.disconnectedCallback();
  }

  render() {
    return html`
      <div class="gear" @click=${this._toggle}
        title="Settings">\u2699</div>
      ${this.open ? this._renderMenu() : ''}
    `;
  }

  private _renderMenu() {
    return html`
      <div class="menu">
        <div class="title">Units</div>
        ${this._opt('aviation', 'Aviation', 'kt / ft')}
        ${this._opt('si', 'SI', 'm/s / m')}
        ${this._opt('imperial', 'Imperial', 'mph / ft')}
        <div class="title" style="margin-top:8px">
          Help
        </div>
        <a
          href="/docs/"
          target="_blank"
          rel="noopener"
          class="doc-link"
        >\uD83D\uDCD6 Documentation \u2197</a>
      </div>
    `;
  }

  private _opt(value: UnitSystem, label: string, desc: string) {
    return html`
      <label class="row">
        <input
          type="radio"
          name="units"
          value=${value}
          ?checked=${this.units === value}
          @change=${() => this._pick(value)}
        />${label}
        <span class="unit-desc"> ${desc}</span>
      </label>
    `;
  }

  private _toggle(): void {
    this.open = !this.open;
  }

  private _pick(u: UnitSystem): void {
    setUnits(u);
  }
}
