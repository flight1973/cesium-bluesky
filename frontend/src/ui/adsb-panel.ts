/**
 * Local ADS-B feed configuration panel.
 *
 * Configures the BlueSky DATAFEED plugin (Mode-S Beast
 * TCP client) host/port and toggles the feed on/off.
 *
 * Typical use: a local dump1090 / readsb instance on the
 * same LAN, eliminating rate limits from cloud feeds like
 * OpenSky while providing sub-second updates.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';

interface AdsbStatus {
  host: string;
  port: number;
  connected: boolean;
  plugin_loaded: boolean;
  tracked_aircraft: number;
}

@customElement('adsb-panel')
export class AdsbPanel extends LitElement {
  @state() private _host = '';
  @state() private _port = 30005;
  @state() private _connected = false;
  @state() private _pluginLoaded = false;
  @state() private _trackedCount = 0;
  @state() private _status = '';
  @state() private _busy = false;
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
      width: 320px;
    }
    :host([hidden]) { display: none; }
    .header {
      padding: 6px 8px;
      background: #002233;
      border-bottom: 1px solid #333;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .title { font-weight: bold; font-size: 12px; }
    .dot {
      display: inline-block;
      width: 8px; height: 8px;
      border-radius: 50%;
      margin-right: 4px;
      background: #666;
    }
    .dot.on { background: #0f0; box-shadow: 0 0 4px #0f0; }
    .dot.off { background: #f44; }
    .body { padding: 8px; display: flex;
      flex-direction: column; gap: 6px; }
    label {
      font-size: 10px; color: #888;
      display: block;
    }
    input {
      background: #111; color: #0cf;
      border: 1px solid #333; border-radius: 3px;
      font-family: inherit; font-size: 11px;
      padding: 3px 5px;
      width: 100%;
      box-sizing: border-box;
    }
    input:focus { outline: 1px solid #0cf; border-color: #0cf; }
    .row { display: flex; gap: 6px; }
    .row > div { flex: 1; }
    .row > div.small { flex: 0 0 90px; }
    .buttons {
      display: flex; gap: 6px;
      margin-top: 4px;
    }
    button {
      flex: 1;
      background: #222; color: #0cf;
      border: 1px solid #0cf; border-radius: 3px;
      cursor: pointer; font-family: inherit;
      font-size: 11px; padding: 4px;
    }
    button:hover:not(:disabled) { background: #0cf; color: #000; }
    button.off { border-color: #f66; color: #f66; }
    button.off:hover:not(:disabled) { background: #f66; color: #000; }
    button:disabled {
      opacity: 0.4; cursor: not-allowed;
    }
    .info {
      font-size: 10px; color: #888;
      line-height: 1.4;
    }
    .info .k { color: #0cf; }
    .status {
      font-size: 10px;
      padding: 4px 0 0;
      color: #888;
    }
    .status.error { color: #f66; }
    .status.success { color: #0f0; }
    .hint {
      font-size: 10px;
      color: #666;
      font-style: italic;
      line-height: 1.4;
    }
  `;

  connectedCallback(): void {
    super.connectedCallback();
    this._loadConfig();
    this._pollTimer = window.setInterval(
      () => this._pollStatus(), 3000,
    );
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._pollTimer !== null) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  private async _loadConfig(): Promise<void> {
    try {
      const res = await fetch('/api/adsb/config');
      if (!res.ok) return;
      const s: AdsbStatus = await res.json();
      this._host = s.host || '';
      this._port = s.port || 30005;
      this._connected = s.connected;
      this._pluginLoaded = s.plugin_loaded;
      this._trackedCount = s.tracked_aircraft;
    } catch {
      // non-fatal
    }
  }

  private async _pollStatus(): Promise<void> {
    try {
      const res = await fetch('/api/adsb/status');
      if (!res.ok) return;
      const s = await res.json();
      this._connected = s.connected;
      this._trackedCount = s.tracked_aircraft;
    } catch {
      // non-fatal
    }
  }

  private async _save(): Promise<void> {
    this._busy = true;
    this._status = '';
    try {
      const res = await fetch('/api/adsb/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host: this._host.trim(),
          port: this._port,
        }),
      });
      if (!res.ok) {
        this._status = `Error: ${await res.text()}`;
      } else {
        this._status = 'Saved';
      }
    } catch (e: any) {
      this._status = `Error: ${e.message}`;
    } finally {
      this._busy = false;
    }
  }

  private async _toggle(on: boolean): Promise<void> {
    this._busy = true;
    this._status = '';
    try {
      // Always save the latest inputs before toggling on.
      if (on) await this._save();
      const res = await fetch(
        `/api/adsb/toggle?on=${on ? 'true' : 'false'}`,
        { method: 'POST' },
      );
      if (!res.ok) {
        this._status = `Error: ${await res.text()}`;
      } else {
        this._status = on ? 'Connecting...' : 'Disconnected';
        setTimeout(() => this._pollStatus(), 500);
      }
    } catch (e: any) {
      this._status = `Error: ${e.message}`;
    } finally {
      this._busy = false;
    }
  }

  render() {
    return html`
      <div class="header">
        <span class="title">LOCAL ADS-B FEED</span>
        <span>
          <span class="dot ${this._connected ? 'on' : 'off'}"></span>
          ${this._connected ? 'connected' : 'offline'}
        </span>
      </div>
      <div class="body">
        <div class="hint">
          Mode-S Beast TCP (dump1090 / readsb).
          Default port 30005.
        </div>
        <div class="row">
          <div>
            <label>Host</label>
            <input type="text" .value=${this._host}
              placeholder="localhost"
              @input=${(e: Event) =>
                this._host = (e.target as HTMLInputElement).value} />
          </div>
          <div class="small">
            <label>Port</label>
            <input type="number" min="1" max="65535"
              .value=${String(this._port)}
              @input=${(e: Event) =>
                this._port = parseInt(
                  (e.target as HTMLInputElement).value, 10,
                ) || 0} />
          </div>
        </div>

        <div class="info">
          Tracked aircraft:
          <span class="k">${this._trackedCount}</span>
          ${!this._pluginLoaded ? html`
            <br/><span style="color:#f66">
              Plugin not loaded (check settings.cfg
              enabled_plugins)
            </span>
          ` : nothing}
        </div>

        <div class="buttons">
          ${this._connected ? html`
            <button class="off"
              ?disabled=${this._busy}
              @click=${() => this._toggle(false)}>
              DISCONNECT
            </button>
          ` : html`
            <button
              ?disabled=${this._busy || !this._host || this._port <= 0}
              @click=${() => this._toggle(true)}>
              CONNECT
            </button>
          `}
          <button
            ?disabled=${this._busy}
            @click=${this._save}>
            SAVE
          </button>
        </div>

        ${this._status ? html`
          <div class="status ${
            this._status.startsWith('Error') ? 'error' : 'success'
          }">${this._status}</div>
        ` : nothing}
      </div>
    `;
  }
}
