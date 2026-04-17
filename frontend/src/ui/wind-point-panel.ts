/**
 * Wind-point detail + editor panel.
 *
 * Two modes:
 *
 * **View mode** (default when opened by clicking a
 * barb): read-only display with LAT / LON / ALT /
 * FROM / SPEED, a mini barb SVG, and EDIT / DELETE
 * buttons.
 *
 * **Edit mode** (entered from EDIT, or from
 * ``showPointForCreate`` for a brand-new point): same
 * layout, but all fields become inputs, with SAVE and
 * CANCEL buttons.  Saving an existing point is a
 * DELETE-and-POST combo (BlueSky has no per-point
 * update); saving a new point is a straight POST.
 */
import { LitElement, html, css, nothing, svg } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import {
  msToUser, userToMs, getUnits, speedUnitLabel,
  onUnitsChange,
} from '../services/units';

export interface WindPointDetail {
  lat: number;
  lon: number;
  altitude_ft: number | null;
  direction_deg: number;
  /** Speed in knots (native barb unit). */
  speed_kt: number;
}

@customElement('wind-point-panel')
export class WindPointPanel extends LitElement {
  @state() private point: WindPointDetail | null = null;
  @state() private editMode = false;
  @state() private isNew = false;
  @state() private editLat = 0;
  @state() private editLon = 0;
  @state() private editDir = 270;
  // Speed in the user's unit system.
  @state() private editSpeed = 0;
  @state() private editAltText = '';
  @state() private saving = false;
  private unitsUnsub: (() => void) | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this.unitsUnsub = onUnitsChange(() =>
      this.requestUpdate(),
    );
  }

  disconnectedCallback(): void {
    this.unitsUnsub?.();
    this.unitsUnsub = null;
    super.disconnectedCallback();
  }

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-left: 1px solid #333;
      overflow-y: auto;
      width: 280px;
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
    .mode-badge {
      font-size: 10px;
      color: #ffcd66;
      border: 1px solid #ffcd66;
      padding: 1px 6px;
      border-radius: 2px;
      margin-left: 8px;
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
      padding: 8px;
      border-bottom: 1px solid #222;
    }
    .field-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 4px 0;
    }
    .field-label {
      width: 54px;
      color: #888;
      font-size: 11px;
    }
    .field-value {
      flex: 1;
      color: #00ff00;
    }
    input.edit {
      flex: 1;
      background: #222;
      border: 1px solid #444;
      color: #00ff00;
      font-family: inherit;
      font-size: 12px;
      padding: 2px 4px;
      border-radius: 2px;
    }
    input.edit:focus {
      border-color: #00ff00;
      outline: none;
    }
    .barb-box {
      display: flex;
      justify-content: center;
      padding: 12px 0;
    }
    .barb-box svg {
      width: 140px;
      height: 100px;
      background: #0a0a0a;
      border: 1px solid #222;
      border-radius: 2px;
    }
    .barb-stroke {
      stroke: #ffcd66;
      stroke-width: 1.5;
      fill: none;
    }
    .barb-fill {
      stroke: #ffcd66;
      stroke-width: 1.5;
      fill: #ffcd66;
    }
    .breakdown {
      color: #888;
      font-size: 11px;
      margin-top: 6px;
      text-align: center;
    }
    .actions {
      display: flex;
      gap: 8px;
      padding: 8px;
    }
    .action-btn {
      flex: 1;
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 4px 8px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    .action-btn:hover { background: #00ff00; color: #000; }
    .action-btn[disabled] {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .action-btn.danger {
      color: #ff6666;
      border-color: #ff6666;
    }
    .action-btn.danger:hover {
      background: #ff4444;
      color: #000;
    }
    .suffix {
      color: #888;
      font-size: 11px;
      min-width: 28px;
    }
  `;

  // ── Public API ────────────────────────────────────

  /** Show an existing point in read-only view mode. */
  showPoint(point: WindPointDetail): void {
    this.point = point;
    this.editMode = false;
    this.isNew = false;
    this.hidden = false;
  }

  /**
   * Show the panel in edit mode for a brand-new point
   * at the given lat/lon.  Called from the "+ Add on
   * map" flow after the user clicks the globe.
   */
  showPointForCreate(lat: number, lon: number): void {
    this.point = null;
    this.isNew = true;
    this.editMode = true;
    this.editLat = lat;
    this.editLon = lon;
    this.editDir = 270;
    this.editSpeed = 0;
    this.editAltText = '';
    this.hidden = false;
  }

  /** Hide the panel. */
  hide(): void {
    this.hidden = true;
    this.point = null;
    this.editMode = false;
    this.isNew = false;
    this.dispatchEvent(
      new CustomEvent('wind-panel-close', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ── Render ────────────────────────────────────────

  render() {
    if (this.editMode) return this._renderEdit();
    return this._renderView();
  }

  private _renderView() {
    if (!this.point) return nothing;
    const p = this.point;
    const unitLabel = speedUnitLabel();
    const speedUser = Math.round(
      msToUser(p.speed_kt * 0.514444),
    );
    const dirStr = `${
      Math.round(p.direction_deg).toString().padStart(3, '0')
    }°`;
    const altStr = p.altitude_ft === null
      ? 'All altitudes (2D)'
      : p.altitude_ft >= 18000
        ? `FL${Math.round(p.altitude_ft / 100)}`
        : `${Math.round(p.altitude_ft)} ft`;

    return html`
      <div class="header">
        <span>WIND POINT</span>
        <button class="close" @click=${this._close}>
          \u2715
        </button>
      </div>

      <div class="section">
        <div class="field-row">
          <span class="field-label">LAT</span>
          <span class="field-value">${p.lat.toFixed(4)}°</span>
        </div>
        <div class="field-row">
          <span class="field-label">LON</span>
          <span class="field-value">${p.lon.toFixed(4)}°</span>
        </div>
        <div class="field-row">
          <span class="field-label">ALT</span>
          <span class="field-value">${altStr}</span>
        </div>
      </div>

      <div class="section">
        <div class="field-row">
          <span class="field-label">FROM</span>
          <span class="field-value">${dirStr}</span>
        </div>
        <div class="field-row">
          <span class="field-label">SPEED</span>
          <span class="field-value">
            ${speedUser} ${unitLabel}
            ${unitLabel !== 'kt'
              ? html`<span style="color:#666">
                (${Math.round(p.speed_kt)} kt)
              </span>` : nothing}
          </span>
        </div>
        <div class="barb-box">
          ${this._renderBarb(p.direction_deg, p.speed_kt)}
        </div>
        <div class="breakdown">
          ${this._speedBreakdown(p.speed_kt)}
        </div>
      </div>

      <div class="actions">
        <button class="action-btn"
          @click=${this._enterEditMode}
        >EDIT</button>
        <button class="action-btn danger"
          @click=${this._delete}
        >DELETE</button>
      </div>
    `;
  }

  private _renderEdit() {
    const unitLabel = speedUnitLabel();
    // Live preview of the barb while typing.
    const previewSpeedKt = (() => {
      const ms = userToMs(this.editSpeed);
      return ms / 0.514444;
    })();
    return html`
      <div class="header">
        <span>
          WIND POINT
          <span class="mode-badge">
            ${this.isNew ? 'NEW' : 'EDIT'}
          </span>
        </span>
        <button class="close" @click=${this._cancel}>
          \u2715
        </button>
      </div>

      <div class="section">
        <div class="field-row">
          <span class="field-label">LAT</span>
          <input class="edit" type="number" step="0.0001"
            .value=${String(this.editLat)}
            @input=${(e: Event) => this.editLat =
              parseFloat((e.target as HTMLInputElement).value) || 0}
          />
          <span class="suffix">°</span>
        </div>
        <div class="field-row">
          <span class="field-label">LON</span>
          <input class="edit" type="number" step="0.0001"
            .value=${String(this.editLon)}
            @input=${(e: Event) => this.editLon =
              parseFloat((e.target as HTMLInputElement).value) || 0}
          />
          <span class="suffix">°</span>
        </div>
        <div class="field-row">
          <span class="field-label">ALT</span>
          <input class="edit" type="number" step="100"
            placeholder="blank = all alts"
            .value=${this.editAltText}
            @input=${(e: Event) => this.editAltText =
              (e.target as HTMLInputElement).value}
          />
          <span class="suffix">ft</span>
        </div>
      </div>

      <div class="section">
        <div class="field-row">
          <span class="field-label">FROM</span>
          <input class="edit" type="number"
            min="0" max="360" step="1"
            .value=${String(this.editDir)}
            @input=${(e: Event) => this.editDir =
              parseFloat((e.target as HTMLInputElement).value) || 0}
          />
          <span class="suffix">°</span>
        </div>
        <div class="field-row">
          <span class="field-label">SPEED</span>
          <input class="edit" type="number"
            min="0" step="1"
            .value=${String(this.editSpeed)}
            @input=${(e: Event) => this.editSpeed =
              parseFloat((e.target as HTMLInputElement).value) || 0}
          />
          <span class="suffix">${unitLabel}</span>
        </div>
        <div class="barb-box">
          ${this._renderBarb(this.editDir, previewSpeedKt)}
        </div>
        <div class="breakdown">
          ${this._speedBreakdown(previewSpeedKt)}
        </div>
      </div>

      <div class="actions">
        <button class="action-btn"
          @click=${this._save}
          ?disabled=${this.saving}
        >${this.saving ? 'SAVING…' : 'SAVE'}</button>
        <button class="action-btn"
          @click=${this._cancel}
          ?disabled=${this.saving}
        >CANCEL</button>
      </div>
    `;
  }

  // ── Actions ───────────────────────────────────────

  private _close(): void {
    this.hide();
  }

  private _cancel(): void {
    if (this.isNew) {
      this.hide();
      return;
    }
    this.editMode = false;
  }

  private _enterEditMode(): void {
    if (!this.point) return;
    this.editLat = this.point.lat;
    this.editLon = this.point.lon;
    this.editDir = this.point.direction_deg;
    // Convert stored knots → user's unit system for
    // the input field.
    this.editSpeed = Math.round(
      msToUser(this.point.speed_kt * 0.514444),
    );
    this.editAltText = this.point.altitude_ft === null
      ? ''
      : String(this.point.altitude_ft);
    this.editMode = true;
    this.isNew = false;
  }

  private async _save(): Promise<void> {
    this.saving = true;
    const units = getUnits();
    const altText = this.editAltText.trim();
    const altitude_ft = altText === ''
      ? null
      : parseFloat(altText);

    // If we're editing an existing point, DELETE the old
    // first; BlueSky doesn't support per-point updates,
    // so "save-edit" = clear-old + post-new.
    try {
      if (!this.isNew && this.point) {
        const delBody: any = {
          lat: this.point.lat, lon: this.point.lon,
        };
        if (this.point.altitude_ft !== null) {
          delBody.altitude_ft = this.point.altitude_ft;
        }
        await fetch('/api/wind/points', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(delBody),
        });
      }
      const postBody: any = {
        lat: this.editLat,
        lon: this.editLon,
        direction_deg: this.editDir,
        speed: this.editSpeed,
        units,
      };
      if (altitude_ft !== null) {
        postBody.altitude_ft = altitude_ft;
      }
      await fetch('/api/wind/points', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(postBody),
      });
    } catch (err) {
      this.saving = false;
      alert(`Failed to save wind point: ${err}`);
      return;
    }

    // Update local state: view mode showing the new
    // values so the user sees SAVE succeeded.
    const newSpeedKt = userToMs(this.editSpeed) / 0.514444;
    this.point = {
      lat: this.editLat,
      lon: this.editLon,
      altitude_ft,
      direction_deg: this.editDir,
      speed_kt: newSpeedKt,
    };
    this.editMode = false;
    this.isNew = false;
    this.saving = false;
    // Ask the app to refresh its defined-points data
    // (which refreshes the barbs on the globe).
    this.dispatchEvent(
      new CustomEvent('wind-refresh-needed', {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _delete(): void {
    if (!this.point) return;
    if (!confirm('Delete this wind point?')) return;
    this.dispatchEvent(
      new CustomEvent('wind-delete', {
        detail: {
          lat: this.point.lat,
          lon: this.point.lon,
          altitude_ft: this.point.altitude_ft,
        },
        bubbles: true,
        composed: true,
      }),
    );
    this.hide();
  }

  // ── Mini barb SVG (same logic as before) ─────────

  private _renderBarb(dirFromDeg: number, speedKt: number) {
    const cx = 70;
    const cy = 50;
    const shaftLen = 40;
    const barbLen = 14;
    const barbSpacing = 6;
    const flagBase = 8;

    if (speedKt < 3) {
      return svg`
        <svg viewBox="0 0 140 100">
          <circle cx="${cx}" cy="${cy}" r="6"
            class="barb-stroke" />
        </svg>
      `;
    }

    let speed = Math.round(speedKt / 5) * 5;
    const nFlags = Math.floor(speed / 50);
    speed -= nFlags * 50;
    const nFull = Math.floor(speed / 10);
    speed -= nFull * 10;
    const nHalf = Math.floor(speed / 5);

    const elements: any[] = [];
    elements.push(svg`
      <line x1="0" y1="0" x2="0" y2="${-shaftLen}"
        class="barb-stroke" />
    `);

    let yAlong = -shaftLen;
    for (let i = 0; i < nFlags; i++) {
      const pts = [
        `0,${yAlong}`,
        `${barbLen},${yAlong + flagBase / 2}`,
        `0,${yAlong + flagBase}`,
      ].join(' ');
      elements.push(svg`
        <polygon points="${pts}" class="barb-fill" />
      `);
      yAlong += flagBase + barbSpacing * 0.5;
    }

    for (let i = 0; i < nFull; i++) {
      elements.push(svg`
        <line x1="0" y1="${yAlong}"
          x2="${barbLen}" y2="${yAlong - barbSpacing * 0.4}"
          class="barb-stroke" />
      `);
      yAlong += barbSpacing;
    }
    if (nHalf > 0) {
      elements.push(svg`
        <line x1="0" y1="${yAlong}"
          x2="${barbLen / 2}"
          y2="${yAlong - barbSpacing * 0.4}"
          class="barb-stroke" />
      `);
    }

    return svg`
      <svg viewBox="0 0 140 100">
        <g transform="translate(${cx} ${cy})
          rotate(${dirFromDeg})">
          ${elements}
        </g>
      </svg>
    `;
  }

  private _speedBreakdown(speedKt: number): string {
    if (speedKt < 3) return 'CALM';
    let speed = Math.round(speedKt / 5) * 5;
    const flags = Math.floor(speed / 50);
    speed -= flags * 50;
    const full = Math.floor(speed / 10);
    speed -= full * 10;
    const half = Math.floor(speed / 5);
    const parts: string[] = [];
    if (flags) parts.push(`${flags} flag${flags > 1 ? 's' : ''}`);
    if (full) parts.push(`${full} full barb${full > 1 ? 's' : ''}`);
    if (half) parts.push(`${half} half barb`);
    return parts.join(' + ');
  }
}
