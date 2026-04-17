import { LitElement, html, css, svg as litSvg } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import type { Viewer } from 'cesium';
import { Cartesian3, Math as CesiumMath } from 'cesium';

@customElement('compass-ring')
export class CompassRing extends LitElement {
  @state() private headingDeg = 0;
  @state() private pitchDeg = -90;
  @state() private heightM = 500000;
  @state() private _hoverTilt = false;
  private viewer: Viewer | null = null;
  private _moveEnd: (() => void) | null = null;
  private _changed: (() => void) | null = null;

  private _dragging = false;
  private _dragStartAngle = 0;
  private _dragStartHeading = 0;
  private _didDrag = false;

  private _tiltDragging = false;

  static styles = css`
    :host {
      display: block;
      user-select: none;
      cursor: default;
    }

    .container {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* ── Compass ring ────────────────── */
    .compass-wrap {
      position: relative;
      width: 150px;
      height: 150px;
    }

    .compass-svg {
      width: 150px;
      height: 150px;
      display: block;
    }

    /* ── D-pad buttons (HTML overlay) ── */
    .dpad {
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      display: grid;
      grid-template-columns: 22px 22px 22px;
      grid-template-rows: 22px 22px 22px;
      gap: 1px;
    }

    .dpad button {
      width: 22px;
      height: 22px;
      background: rgba(34, 34, 34, 0.9);
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 3px;
      cursor: pointer;
      font-size: 11px;
      font-family: inherit;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      line-height: 1;
    }
    .dpad button:hover {
      background: #00ff00;
      color: #000;
    }

    .dpad .center-btn {
      font-size: 9px;
      background: rgba(34, 34, 34, 0.95);
      border-color: #00aa00;
    }
    .dpad .center-btn:hover {
      background: #00ff00;
      color: #000;
    }

    .spacer { width: 22px; height: 22px; }

    /* ── Right column: tilt + zoom ──── */
    .right-col {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }

    /* ── Tilt slider ─────────────────── */
    .tilt-wrap {
      position: relative;
    }

    .tilt-track {
      width: 20px;
      height: 110px;
      background: rgba(0, 0, 0, 0.75);
      border-radius: 10px;
      border: 1px solid #444;
      position: relative;
      cursor: ns-resize;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
      padding: 5px 0;
    }
    .tilt-track:hover { border-color: #00ff00; }

    .tilt-label {
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 7px;
      color: #555;
      pointer-events: none;
    }

    .tilt-zero {
      position: absolute;
      left: 0; right: 0;
      height: 1px;
      background: #444;
      pointer-events: none;
    }

    .tilt-thumb {
      position: absolute;
      left: 2px;
      width: 16px;
      height: 6px;
      background: #00ff00;
      border-radius: 3px;
      pointer-events: none;
    }

    .tilt-value {
      position: absolute;
      left: 24px;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 9px;
      color: #888;
      white-space: nowrap;
      pointer-events: none;
    }

    /* ── Zoom column ─────────────────── */
    .zoom-col {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
    }
    .zoom-col button {
      width: 20px;
      height: 20px;
      background: rgba(34, 34, 34, 0.9);
      color: #00ff00;
      border: 1px solid #00ff00;
      border-radius: 3px;
      cursor: pointer;
      font-size: 13px;
      font-family: inherit;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      line-height: 1;
    }
    .zoom-col button:hover {
      background: #00ff00;
      color: #000;
    }

    .zoom-label {
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 9px;
      color: #00ff00;
      text-align: center;
      min-width: 30px;
    }
  `;

  render() {
    const cx = 75;
    const cy = 75;
    const outerR = 68;
    const innerR = 42;
    const midR = (outerR + innerR) / 2;
    const hdg = this.headingDeg;

    const ticks = [];
    for (let deg = 0; deg < 360; deg += 5) {
      const rad = ((deg - hdg - 90) * Math.PI) / 180;
      const isMajor = deg % 90 === 0;
      const isMedium = deg % 30 === 0;
      const ri = isMajor ? outerR - 11 : isMedium ? outerR - 7 : outerR - 3;
      ticks.push({
        x1: cx + ri * Math.cos(rad), y1: cy + ri * Math.sin(rad),
        x2: cx + outerR * Math.cos(rad), y2: cy + outerR * Math.sin(rad),
        major: isMajor, medium: isMedium,
      });
    }

    const labels: { label: string; x: number; y: number; isN: boolean }[] = [];
    for (const [label, deg] of [['N', 0], ['E', 90], ['S', 180], ['W', 270]] as const) {
      const rad = ((deg - hdg - 90) * Math.PI) / 180;
      labels.push({ label, x: cx + midR * Math.cos(rad), y: cy + midR * Math.sin(rad), isN: label === 'N' });
    }

    const northRad = ((0 - hdg - 90) * Math.PI) / 180;
    const nTip = outerR + 4;
    const nBase = outerR - 1;
    const nx = cx + nTip * Math.cos(northRad);
    const ny = cy + nTip * Math.sin(northRad);
    const nl = cx + nBase * Math.cos(northRad - 0.09);
    const nly = cy + nBase * Math.sin(northRad - 0.09);
    const nr2 = cx + nBase * Math.cos(northRad + 0.09);
    const nry = cy + nBase * Math.sin(northRad + 0.09);

    const ringHover = this._dragging ? 'rgba(0,255,0,0.15)' : 'rgba(0,0,0,0)';

    // Tilt slider: +90 (top) to -90 (bottom)
    const PITCH_MIN = -90;
    const PITCH_MAX = 90;
    const PAD = 5;
    const TRACK_H = 110 - PAD * 2;
    const pitchNorm = (this.pitchDeg - PITCH_MIN) / (PITCH_MAX - PITCH_MIN);
    const thumbTop = PAD + (1 - pitchNorm) * TRACK_H;
    const zeroTop = PAD + 0.5 * TRACK_H;

    return html`
      <div class="container">
        <div class="compass-wrap">
          <svg class="compass-svg" viewBox="0 0 150 150"
            @mousedown=${this._onRingMouseDown}
            @touchstart=${this._onRingTouchStart}>

            <!-- Background -->
            <circle cx=${cx} cy=${cy} r=${outerR}
              fill="rgba(0,0,0,0.7)" stroke="#333" stroke-width="1" />

            <!-- Ring hover highlight -->
            <circle cx=${cx} cy=${cy} r=${midR}
              fill="none" stroke=${ringHover} stroke-width="${outerR - innerR}"
              pointer-events="none" />

            <!-- Inner disc -->
            <circle cx=${cx} cy=${cy} r=${innerR}
              fill="rgba(0,0,0,0.85)" stroke="#444" stroke-width="1"
              pointer-events="none" />

            <!-- Ticks -->
            ${ticks.map(t => litSvg`
              <line x1=${t.x1} y1=${t.y1} x2=${t.x2} y2=${t.y2}
                stroke=${t.major ? '#00ff00' : t.medium ? '#00aa00' : '#555'}
                stroke-width=${t.major ? 2 : t.medium ? 1.2 : 0.7} />
            `)}

            <!-- Cardinal labels -->
            ${labels.map(l => litSvg`
              <text x=${l.x} y=${l.y}
                fill=${l.isN ? '#ff4444' : '#00cc00'}
                font-family="'Consolas','Courier New',monospace"
                font-size=${l.isN ? '13' : '10'}
                font-weight=${l.isN ? 'bold' : 'normal'}
                text-anchor="middle" dominant-baseline="central"
                pointer-events="none">
                ${l.label}
              </text>
            `)}

            <!-- North pointer -->
            <polygon points="${nx},${ny} ${nl},${nly} ${nr2},${nry}"
              fill="#ff4444" stroke="none" pointer-events="none" />
          </svg>

          <!-- D-pad overlay in center -->
          <div class="dpad">
            <div class="spacer"></div>
            <button @click=${this._panUp} title="Pan up">\u25B2</button>
            <div class="spacer"></div>

            <button @click=${this._panLeft} title="Pan left">\u25C0</button>
            <button class="center-btn" @click=${this._resetTop} title="Top-down north-up">\u25CE</button>
            <button @click=${this._panRight} title="Pan right">\u25B6</button>

            <div class="spacer"></div>
            <button @click=${this._panDown} title="Pan down">\u25BC</button>
            <div class="spacer"></div>
          </div>
        </div>

        <!-- Right column: tilt + zoom -->
        <div class="right-col">
          <div class="tilt-wrap">
            <div class="tilt-track"
              @mousedown=${this._onTiltMouseDown}
              @touchstart=${this._onTiltTouchStart}
              @mouseenter=${() => { this._hoverTilt = true; }}
              @mouseleave=${() => { this._hoverTilt = false; }}>
              <span class="tilt-label">\u2191</span>
              <span class="tilt-label">\u2193</span>
              <div class="tilt-zero" style="top:${zeroTop}px"></div>
              <div class="tilt-thumb" style="top:${thumbTop - 3}px"></div>
              ${this._hoverTilt || this._tiltDragging ? html`
                <span class="tilt-value" style="top:${thumbTop - 5}px">
                  ${Math.round(this.pitchDeg)}\u00B0
                </span>
              ` : ''}
            </div>
          </div>

          <div class="zoom-col">
            <button @click=${this._zoomIn} title="Zoom in">+</button>
            <span class="zoom-label">${this._formatHeight()}</span>
            <button @click=${this._zoomOut} title="Zoom out">\u2212</button>
          </div>
        </div>
      </div>
    `;
  }

  setViewer(v: Viewer): void {
    this.viewer = v;
    this._startTracking();
    this._sync();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._stopTracking();
    this._cleanupListeners();
  }

  private _cleanupListeners(): void {
    document.removeEventListener('mousemove', this._boundMouseMove);
    document.removeEventListener('mouseup', this._boundMouseUp);
    document.removeEventListener('touchmove', this._boundTouchMove);
    document.removeEventListener('touchend', this._boundTouchEnd);
    document.removeEventListener('mousemove', this._boundTiltMouseMove);
    document.removeEventListener('mouseup', this._boundTiltMouseUp);
    document.removeEventListener('touchmove', this._boundTiltTouchMove);
    document.removeEventListener('touchend', this._boundTiltTouchUp);
  }

  private _startTracking(): void {
    if (!this.viewer) return;
    this._stopTracking();
    this._moveEnd = () => this._sync();
    this._changed = () => this._sync();
    this.viewer.camera.moveEnd.addEventListener(this._moveEnd);
    this.viewer.camera.changed.addEventListener(this._changed);
  }

  private _stopTracking(): void {
    if (!this.viewer) return;
    if (this._moveEnd) {
      this.viewer.camera.moveEnd.removeEventListener(this._moveEnd);
      this._moveEnd = null;
    }
    if (this._changed) {
      this.viewer.camera.changed.removeEventListener(this._changed);
      this._changed = null;
    }
  }

  private _sync(): void {
    if (!this.viewer) return;
    this.headingDeg = CesiumMath.toDegrees(this.viewer.camera.heading);
    this.pitchDeg = CesiumMath.toDegrees(this.viewer.camera.pitch);
    this.heightM = this.viewer.camera.positionCartographic.height;
  }

  // ── D-pad: pan ──────────────────────────────────────

  private _panAmount(): number {
    if (!this.viewer) return 0;
    return this.viewer.camera.positionCartographic.height * 0.15;
  }

  private _panUp(): void { this.viewer?.camera.moveUp(this._panAmount()); }
  private _panDown(): void { this.viewer?.camera.moveDown(this._panAmount()); }
  private _panLeft(): void { this.viewer?.camera.moveLeft(this._panAmount()); }
  private _panRight(): void { this.viewer?.camera.moveRight(this._panAmount()); }

  private _resetTop(): void {
    if (!this.viewer) return;
    const cam = this.viewer.camera;
    const carto = cam.positionCartographic;
    cam.setView({
      destination: Cartesian3.fromRadians(carto.longitude, carto.latitude, carto.height),
      orientation: { heading: 0, pitch: CesiumMath.toRadians(-90), roll: 0 },
    });
  }

  // ── Zoom ────────────────────────────────────────────

  private _zoomIn(): void {
    this.viewer?.camera.zoomIn(this.viewer.camera.positionCartographic.height * 0.3);
    this._sync();
  }

  private _zoomOut(): void {
    this.viewer?.camera.zoomOut(this.viewer.camera.positionCartographic.height * 0.3);
    this._sync();
  }

  private _formatHeight(): string {
    const h = this.heightM;
    if (h < 1000) return `${Math.round(h)}m`;
    if (h < 10_000) return `${(h / 1000).toFixed(1)}km`;
    if (h < 1_000_000) return `${Math.round(h / 1000)}km`;
    return `${(h / 1_000_000).toFixed(1)}Mm`;
  }

  // ── Compass ring: heading ───────────────────────────

  private _applyHeading(deg: number): void {
    if (!this.viewer) return;
    const cam = this.viewer.camera;
    const carto = cam.positionCartographic;
    cam.setView({
      destination: Cartesian3.fromRadians(carto.longitude, carto.latitude, carto.height),
      orientation: { heading: CesiumMath.toRadians(deg), pitch: cam.pitch, roll: 0 },
    });
  }

  private _clickToFace(clientX: number, clientY: number): void {
    if (!this.viewer) return;
    const svgEl = this.renderRoot.querySelector('.compass-svg') as SVGSVGElement;
    if (!svgEl) return;
    const rect = svgEl.getBoundingClientRect();
    const angle = Math.atan2(clientY - (rect.top + rect.height / 2),
                             clientX - (rect.left + rect.width / 2)) * (180 / Math.PI);
    const targetHdg = ((angle + 90) % 360 + 360) % 360;
    const cam = this.viewer.camera;
    const carto = cam.positionCartographic;
    cam.flyTo({
      destination: Cartesian3.fromRadians(carto.longitude, carto.latitude, carto.height),
      orientation: { heading: CesiumMath.toRadians(targetHdg), pitch: cam.pitch, roll: 0 },
      duration: 0.5,
    });
  }

  private _clientAngle(clientX: number, clientY: number): number {
    const svgEl = this.renderRoot.querySelector('.compass-svg');
    if (!svgEl) return 0;
    const rect = svgEl.getBoundingClientRect();
    return Math.atan2(clientY - (rect.top + rect.height / 2),
                      clientX - (rect.left + rect.width / 2)) * (180 / Math.PI);
  }

  private _isOnRing(clientX: number, clientY: number): boolean {
    const svgEl = this.renderRoot.querySelector('.compass-svg');
    if (!svgEl) return false;
    const rect = svgEl.getBoundingClientRect();
    const scale = rect.width / 150;
    const dx = clientX - (rect.left + rect.width / 2);
    const dy = clientY - (rect.top + rect.height / 2);
    const dist = Math.sqrt(dx * dx + dy * dy);
    return dist >= 36 * scale && dist <= 72 * scale;
  }

  private _onRingMouseDown = (e: MouseEvent): void => {
    if (!this._isOnRing(e.clientX, e.clientY)) return;
    e.preventDefault();
    this._dragging = true;
    this._didDrag = false;
    this._dragStartAngle = this._clientAngle(e.clientX, e.clientY);
    this._dragStartHeading = this.headingDeg;
    document.addEventListener('mousemove', this._boundMouseMove);
    document.addEventListener('mouseup', this._boundMouseUp);
  };

  private _boundMouseMove = (e: MouseEvent): void => {
    e.preventDefault();
    if (!this._dragging) return;
    const cur = this._clientAngle(e.clientX, e.clientY);
    const delta = cur - this._dragStartAngle;
    if (Math.abs(delta) > 2) this._didDrag = true;
    this._applyHeading(((this._dragStartHeading - delta) % 360 + 360) % 360);
  };

  private _boundMouseUp = (e: MouseEvent): void => {
    const didDrag = this._didDrag;
    this._dragging = false;
    this._didDrag = false;
    document.removeEventListener('mousemove', this._boundMouseMove);
    document.removeEventListener('mouseup', this._boundMouseUp);
    if (!didDrag) this._clickToFace(e.clientX, e.clientY);
  };

  private _onRingTouchStart = (e: TouchEvent): void => {
    const t = e.touches[0];
    if (!this._isOnRing(t.clientX, t.clientY)) return;
    e.preventDefault();
    this._dragging = true;
    this._didDrag = false;
    this._dragStartAngle = this._clientAngle(t.clientX, t.clientY);
    this._dragStartHeading = this.headingDeg;
    document.addEventListener('touchmove', this._boundTouchMove, { passive: false });
    document.addEventListener('touchend', this._boundTouchEnd);
  };

  private _boundTouchMove = (e: TouchEvent): void => {
    e.preventDefault();
    if (!this._dragging) return;
    const t = e.touches[0];
    const cur = this._clientAngle(t.clientX, t.clientY);
    const delta = cur - this._dragStartAngle;
    if (Math.abs(delta) > 2) this._didDrag = true;
    this._applyHeading(((this._dragStartHeading - delta) % 360 + 360) % 360);
  };

  private _boundTouchEnd = (e: TouchEvent): void => {
    const didDrag = this._didDrag;
    this._dragging = false;
    this._didDrag = false;
    document.removeEventListener('touchmove', this._boundTouchMove);
    document.removeEventListener('touchend', this._boundTouchEnd);
    if (!didDrag && e.changedTouches[0]) {
      this._clickToFace(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
    }
  };

  // ── Tilt slider (full range: +90 to -90) ────────────

  private _pitchFromY(clientY: number): number {
    const track = this.renderRoot.querySelector('.tilt-track') as HTMLElement;
    if (!track) return this.pitchDeg;
    const rect = track.getBoundingClientRect();
    const pad = 5;
    const usable = rect.height - pad * 2;
    const norm = 1 - Math.max(0, Math.min(1, (clientY - rect.top - pad) / usable));
    return -90 + norm * 180;
  }

  private _applyPitch(deg: number): void {
    if (!this.viewer) return;
    const clamped = Math.max(-90, Math.min(90, deg));
    const cam = this.viewer.camera;
    const carto = cam.positionCartographic;
    cam.setView({
      destination: Cartesian3.fromRadians(carto.longitude, carto.latitude, carto.height),
      orientation: { heading: cam.heading, pitch: CesiumMath.toRadians(clamped), roll: 0 },
    });
  }

  private _onTiltMouseDown = (e: MouseEvent): void => {
    e.preventDefault();
    this._tiltDragging = true;
    this._applyPitch(this._pitchFromY(e.clientY));
    document.addEventListener('mousemove', this._boundTiltMouseMove);
    document.addEventListener('mouseup', this._boundTiltMouseUp);
  };

  private _boundTiltMouseMove = (e: MouseEvent): void => {
    e.preventDefault();
    if (this._tiltDragging) this._applyPitch(this._pitchFromY(e.clientY));
  };

  private _boundTiltMouseUp = (): void => {
    this._tiltDragging = false;
    document.removeEventListener('mousemove', this._boundTiltMouseMove);
    document.removeEventListener('mouseup', this._boundTiltMouseUp);
  };

  private _onTiltTouchStart = (e: TouchEvent): void => {
    e.preventDefault();
    this._tiltDragging = true;
    this._applyPitch(this._pitchFromY(e.touches[0].clientY));
    document.addEventListener('touchmove', this._boundTiltTouchMove, { passive: false });
    document.addEventListener('touchend', this._boundTiltTouchUp);
  };

  private _boundTiltTouchMove = (e: TouchEvent): void => {
    e.preventDefault();
    if (this._tiltDragging) this._applyPitch(this._pitchFromY(e.touches[0].clientY));
  };

  private _boundTiltTouchUp = (): void => {
    this._tiltDragging = false;
    document.removeEventListener('touchmove', this._boundTiltTouchMove);
    document.removeEventListener('touchend', this._boundTiltTouchUp);
  };
}
