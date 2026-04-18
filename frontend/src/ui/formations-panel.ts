/**
 * Formations management panel.
 *
 * Lists active formations and lets the user create a
 * new one (leader + followers + geometry + spacing),
 * dissolve existing formations, and compute the
 * wake-surfing offset for a leader/follower type pair.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

interface FormationInfo {
  id: string;
  type: string;
  leader: string;
  followers: string[];
  size: number;
  separation_nm: number;
}

interface FormationType {
  id: string;
  label: string;
}

@customElement('formations-panel')
export class FormationsPanel extends LitElement {
  @state() private formations: FormationInfo[] = [];
  @state() private types: FormationType[] = [];
  @state() private expanded = false;
  @state() private _creating = false;
  @state() private _newId = '';
  @state() private _newLeader = '';
  @state() private _newFollowers = '';
  @state() private _newType = 'trail';
  @state() private _newSpacing = 1.0;
  @state() private _status = '';
  private _pollTimer: number | null = null;

  static styles = css`
    :host {
      display: block;
      background: rgba(0, 0, 0, 0.92);
      color: #0cf;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 11px;
      border: 1px solid #333;
      border-radius: 4px;
      overflow: hidden;
      max-height: 400px;
      width: 320px;
    }
    :host([hidden]) { display: none; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 8px;
      background: #002233;
      border-bottom: 1px solid #333;
      cursor: pointer;
      user-select: none;
    }
    .header:hover { background: #003344; }
    .title { font-weight: bold; font-size: 12px; }
    .count {
      background: #0cf; color: #000;
      padding: 1px 6px; border-radius: 8px;
      font-size: 10px; font-weight: bold;
    }
    .count.zero { background: #333; color: #888; }
    .list {
      overflow-y: auto;
      max-height: 240px;
    }
    .row {
      padding: 4px 8px;
      border-bottom: 1px solid #111;
      font-size: 10px;
    }
    .row:hover { background: #0a1a22; }
    .row-id { color: #0cf; font-weight: bold; }
    .row-sub { color: #888; font-size: 9px; }
    .row-del {
      float: right;
      background: transparent;
      border: 1px solid #f44;
      color: #f44;
      cursor: pointer;
      font-size: 9px;
      padding: 0 4px;
      font-family: inherit;
    }
    .row-del:hover { background: #f44; color: #000; }
    .empty {
      padding: 12px;
      text-align: center;
      color: #555;
    }
    .create-btn {
      width: 100%;
      background: #001a2a;
      color: #0cf;
      border: none;
      border-top: 1px solid #333;
      padding: 6px;
      cursor: pointer;
      font-family: inherit;
      font-size: 11px;
    }
    .create-btn:hover { background: #002a4a; }
    .form {
      padding: 8px;
      background: #0a0a0a;
      border-top: 1px solid #222;
      display: flex; flex-direction: column; gap: 4px;
    }
    .form label {
      font-size: 10px;
      color: #888;
      margin-top: 2px;
    }
    .form input, .form select {
      background: #111; color: #0cf;
      border: 1px solid #333; border-radius: 3px;
      font-family: inherit; font-size: 10px;
      padding: 2px 4px;
    }
    .form-buttons {
      display: flex; gap: 4px; margin-top: 4px;
    }
    .form-buttons button {
      flex: 1;
      background: #222; color: #0cf;
      border: 1px solid #0cf; border-radius: 3px;
      cursor: pointer; font-family: inherit;
      font-size: 10px; padding: 3px;
    }
    .form-buttons button:hover { background: #0cf; color: #000; }
    .form-buttons button.cancel {
      border-color: #888; color: #888;
    }
    .status {
      font-size: 10px;
      padding: 4px 8px;
      color: #888;
    }
    .status.error { color: #f66; }
    .status.success { color: #0f0; }
  `;

  connectedCallback(): void {
    super.connectedCallback();
    this._loadTypes();
    this._loadFormations();
    this._pollTimer = window.setInterval(
      () => this._loadFormations(), 5000,
    );
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._pollTimer !== null) {
      clearInterval(this._pollTimer);
    }
  }

  /** Public method: main.ts calls this to get the latest
   *  formation list for map rendering. */
  async refresh(): Promise<FormationInfo[]> {
    await this._loadFormations();
    return this.formations;
  }

  private async _loadTypes(): Promise<void> {
    try {
      const res = await fetch('/api/formations/types');
      if (!res.ok) return;
      const data = await res.json();
      this.types = data.types || [];
    } catch {
      // non-fatal
    }
  }

  private async _loadFormations(): Promise<void> {
    try {
      const res = await fetch('/api/formations');
      if (!res.ok) return;
      const data = await res.json();
      this.formations = data.formations || [];
      this.dispatchEvent(new CustomEvent('formations-updated', {
        detail: { formations: this.formations },
        bubbles: true, composed: true,
      }));
    } catch {
      // non-fatal
    }
  }

  render() {
    const n = this.formations.length;
    return html`
      <div class="header" @click=${() => this.expanded = !this.expanded}>
        <span class="title">FORMATIONS</span>
        <span class="count ${n === 0 ? 'zero' : ''}">${n}</span>
      </div>
      ${this.expanded ? this._renderList() : nothing}
    `;
  }

  private _renderList() {
    return html`
      ${!this.formations.length ? html`
        <div class="empty">No active formations</div>
      ` : html`
        <div class="list">
          ${this.formations.map(f => this._renderRow(f))}
        </div>
      `}
      ${this._creating
        ? this._renderForm()
        : html`<button class="create-btn"
                       @click=${this._startCreate}>
          + CREATE FORMATION
        </button>`}
      ${this._status ? html`
        <div class="status ${this._status.startsWith('Error') ? 'error' : 'success'}">
          ${this._status}
        </div>
      ` : nothing}
    `;
  }

  private _renderRow(f: FormationInfo) {
    return html`
      <div class="row">
        <button class="row-del" title="Dissolve"
          @click=${() => this._dissolve(f.id)}>\u2716</button>
        <div class="row-id">${f.id}</div>
        <div class="row-sub">
          ${f.type.toUpperCase()} · lead ${f.leader} ·
          ${f.followers.length} followers · ${f.separation_nm.toFixed(1)} NM
        </div>
      </div>
    `;
  }

  private _renderForm() {
    return html`
      <div class="form">
        <label>ID</label>
        <input type="text" .value=${this._newId}
          @input=${(e: Event) =>
            this._newId = (e.target as HTMLInputElement).value}
          placeholder="e.g. lead1" />

        <label>Leader (callsign)</label>
        <input type="text" .value=${this._newLeader}
          @input=${(e: Event) =>
            this._newLeader = (e.target as HTMLInputElement).value}
          placeholder="AAL100" />

        <label>Followers (comma-separated callsigns)</label>
        <input type="text" .value=${this._newFollowers}
          @input=${(e: Event) =>
            this._newFollowers = (e.target as HTMLInputElement).value}
          placeholder="AAL200, AAL300" />

        <label>Geometry</label>
        <select .value=${this._newType}
          @change=${(e: Event) =>
            this._newType = (e.target as HTMLSelectElement).value}>
          ${this.types.map(t => html`
            <option value=${t.id}
              ?selected=${t.id === this._newType}>${t.label}</option>
          `)}
        </select>

        <label>Spacing (NM)</label>
        <input type="number" min="0.1" max="10" step="0.1"
          .value=${String(this._newSpacing)}
          @input=${(e: Event) =>
            this._newSpacing = parseFloat((e.target as HTMLInputElement).value)} />

        <div class="form-buttons">
          <button @click=${this._submitCreate}>CREATE</button>
          <button class="cancel" @click=${this._cancelCreate}>CANCEL</button>
        </div>
      </div>
    `;
  }

  private _startCreate(): void {
    this._creating = true;
    this._status = '';
  }

  private _cancelCreate(): void {
    this._creating = false;
    this._newId = '';
    this._newLeader = '';
    this._newFollowers = '';
    this._status = '';
  }

  private async _submitCreate(): Promise<void> {
    if (!this._newId || !this._newLeader) {
      this._status = 'Error: id and leader required';
      return;
    }
    const followers = this._newFollowers
      .split(',').map(s => s.trim()).filter(Boolean);
    try {
      const res = await fetch('/api/formations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          formation_id: this._newId,
          leader: this._newLeader,
          followers,
          formation_type: this._newType,
          spacing_nm: this._newSpacing,
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        this._status = `Error: ${txt.slice(0, 100)}`;
        return;
      }
      this._status = `Created ${this._newId}`;
      this._cancelCreate();
      this._creating = false;
      await this._loadFormations();
    } catch (e: any) {
      this._status = `Error: ${e.message}`;
    }
  }

  private async _dissolve(id: string): Promise<void> {
    try {
      await fetch(`/api/formations/${id}`, { method: 'DELETE' });
      await this._loadFormations();
    } catch {
      // non-fatal
    }
  }
}
