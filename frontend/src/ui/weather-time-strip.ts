/**
 * Time scrubber for radar / satellite imagery.
 *
 * Floats at the bottom-center of the viewer when
 * either radar or satellite is enabled.  Slides
 * through the last 2 hours of imagery in 5-minute
 * steps (24 frames), with a [LIVE] anchor at the
 * rightmost position that defers to "latest" on the
 * upstream source.
 *
 * Play ▶ animates through the frames; pause ⏸ stops.
 * Prev/next buttons step one frame at a time.
 */
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';

const FRAMES = 24;               // 2 hours at 5-min steps
const STEP_MIN = 5;              // minutes between frames
const PLAY_INTERVAL_MS = 600;    // animation speed

@customElement('weather-time-strip')
export class WeatherTimeStrip extends LitElement {
  /** Which frame index is selected.  FRAMES-1 = LIVE. */
  @state() private frameIdx = FRAMES - 1;
  @state() private playing = false;
  private playTimer: number | null = null;
  /** Coalesces rapid slider drags into one fetch. */
  private dispatchDebounce: number | null = null;
  private static readonly DEBOUNCE_MS = 120;

  connectedCallback(): void {
    super.connectedCallback();
  }

  disconnectedCallback(): void {
    this._stopPlay();
    super.disconnectedCallback();
  }

  static styles = css`
    :host {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 6px 14px;
      background: rgba(0, 0, 0, 0.85);
      color: #00ff00;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 12px;
      border-radius: 4px;
      border: 1px solid #333;
    }
    :host([hidden]) { display: none; }
    button {
      background: #222;
      color: #00ff00;
      border: 1px solid #00ff00;
      padding: 2px 8px;
      border-radius: 2px;
      cursor: pointer;
      font-family: inherit;
      font-size: 12px;
      min-width: 28px;
    }
    button:hover { background: #00ff00; color: #000; }
    button.active { background: #00ff00; color: #000; }
    input[type=range] {
      -webkit-appearance: none;
      width: 260px;
      height: 4px;
      background: #444;
      border-radius: 2px;
      outline: none;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      background: #00ff00;
      border-radius: 50%;
      cursor: pointer;
    }
    .timestamp {
      min-width: 110px;
      text-align: center;
      font-weight: bold;
    }
    .live-badge {
      color: #000;
      background: #00ff00;
      padding: 1px 8px;
      border-radius: 3px;
      font-weight: bold;
      letter-spacing: 0.5px;
    }
    .offset {
      color: #888;
      font-size: 11px;
      min-width: 50px;
      text-align: right;
    }
  `;

  render() {
    const t = this._frameTime();
    const isLive = this.frameIdx === FRAMES - 1;
    const utc = t.toISOString()
      .slice(0, 19).replace('T', ' ') + ' Z';
    const minsAgo = Math.round(
      (Date.now() - t.getTime()) / 60_000,
    );
    return html`
      <button
        @click=${this._stepPrev}
        title="Previous frame (5 min back)"
      >◀</button>
      <button
        class=${this.playing ? 'active' : ''}
        @click=${this._togglePlay}
        title="Play / pause animation"
      >${this.playing ? '⏸' : '▶'}</button>
      <button
        @click=${this._stepNext}
        title="Next frame"
      >▶▶</button>
      <input
        type="range"
        min="0" max=${FRAMES - 1} step="1"
        .value=${String(this.frameIdx)}
        @input=${this._onSlide}
      />
      <span class="timestamp">
        ${isLive
          ? html`<span class="live-badge">LIVE</span>`
          : html`${utc}`}
      </span>
      <span class="offset">${
        isLive
          ? '(latest)'
          : `−${minsAgo} min`
      }</span>
    `;
  }

  /** Return the timestamp (Date) for the current
   *  frame, or "now" rounded down to the nearest step
   *  if at LIVE. */
  private _frameTime(): Date {
    const stepMs = STEP_MIN * 60_000;
    const now = Date.now();
    const latest = Math.floor(now / stepMs) * stepMs;
    const offset = (FRAMES - 1 - this.frameIdx) * stepMs;
    return new Date(latest - offset);
  }

  private _onSlide(e: Event): void {
    const v = parseInt(
      (e.target as HTMLInputElement).value, 10,
    );
    this.frameIdx = v;
    // During a fast drag the slider fires many
    // input events in quick succession.  Coalesce
    // them so we only kick off one network fetch
    // once the user settles.
    this._dispatchDebounced();
  }

  private _stepPrev(): void {
    if (this.frameIdx > 0) {
      this.frameIdx -= 1;
      this._dispatch();
    }
  }

  private _stepNext(): void {
    if (this.frameIdx < FRAMES - 1) {
      this.frameIdx += 1;
      this._dispatch();
    }
  }

  private _dispatchDebounced(): void {
    if (this.dispatchDebounce !== null) {
      clearTimeout(this.dispatchDebounce);
    }
    this.dispatchDebounce = window.setTimeout(() => {
      this.dispatchDebounce = null;
      this._dispatch();
    }, WeatherTimeStrip.DEBOUNCE_MS);
  }

  private _togglePlay(): void {
    this.playing = !this.playing;
    if (this.playing) {
      this._startPlay();
    } else {
      this._stopPlay();
    }
  }

  private _startPlay(): void {
    this._stopPlay();
    this.playTimer = window.setInterval(() => {
      if (this.frameIdx >= FRAMES - 1) {
        // Looped back to start of history.
        this.frameIdx = 0;
      } else {
        this.frameIdx += 1;
      }
      this._dispatch();
    }, PLAY_INTERVAL_MS);
  }

  private _stopPlay(): void {
    if (this.playTimer !== null) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
  }

  /** Jump to LIVE (called by main.ts on auto-refresh). */
  jumpLive(): void {
    this.frameIdx = FRAMES - 1;
    this._dispatch();
  }

  private _dispatch(): void {
    const isLive = this.frameIdx === FRAMES - 1;
    const time = isLive
      ? null
      : this._frameTime().toISOString();
    this.dispatchEvent(
      new CustomEvent('weather-time-change', {
        detail: { time, frameIdx: this.frameIdx },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
