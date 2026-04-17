/**
 * Observed (live) aircraft entity manager.
 *
 * Renders real ADS-B-derived aircraft positions on
 * the globe with distinct styling from simulated
 * aircraft — dashed outline, amber tint, "(LIVE)"
 * label suffix — so operators instantly see which
 * contacts are real (read-only) vs sim-controlled.
 *
 * Fed from ``/api/surveillance/live`` on a
 * camera-move + 15-second interval.
 */
import {
  Viewer,
  Cartesian2,
  Cartesian3,
  Color,
  CustomDataSource,
  Entity,
  Math as CesiumMath,
  Matrix4,
  Transforms,
  VerticalOrigin,
  HorizontalOrigin,
  LabelStyle,
  ConstantProperty,
  ConstantPositionProperty,
} from 'cesium';

export interface ObservedAircraft {
  icao24: string;
  callsign: string;
  lat: number;
  lon: number;
  alt_m: number;
  alt_ft: number;
  gs_kt: number;
  trk_deg: number;
  vs_fpm: number;
  on_ground: boolean;
  squawk: string;
  source: string;
  // Enriched from aircraft registry (when populated).
  registration?: string;  // N-number / tail
  typecode?: string;      // ICAO type (B738, A320)
  model?: string;         // Full model name
  operator?: string;      // Airline / operator name
  owner?: string;
}

const LIVE_COLOR = new Color(1.0, 0.75, 0.2, 0.85);    // amber
const LIVE_OUTLINE = new Color(1.0, 0.6, 0.0, 0.9);
const LIVE_LABEL_BG = new Color(0, 0, 0, 0.55);
const TRAIL_COLOR = new Color(1.0, 0.6, 0.0, 0.4);     // dim amber trail
const LEADER_COLOR = new Color(1.0, 0.85, 0.3, 0.7);   // bright amber leader
const TRANS_LVL_FT = 18000;
const VV_SECONDS = 60;  // leader line = 60 s of travel
const MAX_TRAIL_POINTS = 120; // ~30 min at 15s updates
const DR_INTERVAL_MS = 100;  // dead-reckoning tick (10 Hz)
const BLEND_DURATION_S = 2.0; // smooth correction blend

/** Per-aircraft dead-reckoning state. */
interface DrState {
  // Last observed values
  lat: number;
  lon: number;
  alt_m: number;
  gs_ms: number;       // m/s
  trk_rad: number;     // radians
  vs_ms: number;       // m/s
  observedAt: number;  // Date.now() when update arrived
  // Rate-of-change terms — derived from consecutive
  // observations.  Applied in the DR tick so the
  // projection handles turns, accel/decel, and
  // climb/descent transitions.
  accel_ms2: number;   // groundspeed acceleration (m/s²)
  vs_accel_ms2: number; // vertical-rate change (m/s²)
  turn_rad_s: number;  // heading change rate (rad/s)
  // Blend correction — offset from DR prediction to
  // where the next observation says we should be.
  // Fades to zero over BLEND_DURATION_S.
  blendLat: number;
  blendLon: number;
  blendAlt: number;
  blendStart: number;  // Date.now() when blend began
  source: string;
}

const _scratchLocal = new Cartesian3();
const _scratchWorld = new Cartesian3();

function velocityEndpoint(
  origin: Cartesian3,
  headingRad: number,
  distance: number,
): Cartesian3 {
  const enu = Transforms.eastNorthUpToFixedFrame(origin);
  const east = Math.sin(headingRad) * distance;
  const north = Math.cos(headingRad) * distance;
  Cartesian3.fromElements(east, north, 0, _scratchLocal);
  Matrix4.multiplyByPoint(enu, _scratchLocal, _scratchWorld);
  return Cartesian3.clone(_scratchWorld);
}


export class ObservedTrafficManager {
  private source: CustomDataSource;
  private trailSource: CustomDataSource;
  private _visible = false;
  private _leadersVisible = true;
  private _trailsVisible = true;
  private _interpolation = true;
  private _altScale = 1.0;
  private _last: ObservedAircraft[] = [];
  /** Track previous speed per icao24 for accel/decel arrow. */
  private _prevSpd = new Map<string, number>();
  /** Per-aircraft entity refs for in-place updates. */
  private _entities = new Map<string, Entity>();
  private _leaders = new Map<string, Entity>();
  /** Accumulated trail positions per aircraft. */
  private _trails = new Map<string, Cartesian3[]>();
  private _trailEntities = new Map<string, Entity>();

  /** Dead-reckoning state per aircraft. */
  private _dr = new Map<string, DrState>();
  private _drTimer: number | null = null;

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('observed');
    this.trailSource = new CustomDataSource('observed-trails');
    viewer.dataSources.add(this.source);
    viewer.dataSources.add(this.trailSource);
    this.source.show = this._visible;
    this.trailSource.show = this._visible;
  }

  /** Start the dead-reckoning interpolation loop. */
  private _startDrLoop(): void {
    if (this._drTimer !== null) return;
    this._drTimer = window.setInterval(
      () => this._drTick(), DR_INTERVAL_MS,
    );
  }

  private _stopDrLoop(): void {
    if (this._drTimer !== null) {
      clearInterval(this._drTimer);
      this._drTimer = null;
    }
  }

  setInterpolation(on: boolean): void {
    this._interpolation = on;
  }

  get interpolation(): boolean { return this._interpolation; }

  /** Advance every tracked aircraft by dead-reckoning
   *  and update its Cesium entity position. */
  private _drTick(): void {
    if (!this._visible) return;
    if (!this._interpolation) return;
    const now = Date.now();
    for (const [icao, dr] of this._dr) {
      const elapsed = (now - dr.observedAt) / 1000.0;

      // Instantaneous heading with turn rate applied.
      const hdg = dr.trk_rad + dr.turn_rad_s * elapsed;

      // Instantaneous speed with acceleration.
      const gs = Math.max(0,
        dr.gs_ms + dr.accel_ms2 * elapsed);

      // For a turning aircraft, integrate position
      // along the curved path rather than a straight
      // line.  For small turn rates this converges to
      // the linear case; for 3°/s standard-rate turns
      // it produces a proper arc.
      let dLat: number, dLon: number;
      const turnRate = dr.turn_rad_s;
      if (Math.abs(turnRate) > 0.0001) {
        // Arc integration: R = v/ω, then
        // dx = R(sin(θ₁) - sin(θ₀))
        // dy = R(cos(θ₀) - cos(θ₁))
        const theta0 = dr.trk_rad;
        const theta1 = hdg;
        const R = gs / turnRate;  // turn radius in meters
        const dEast = R * (Math.sin(theta1) - Math.sin(theta0));
        const dNorth = R * (Math.cos(theta0) - Math.cos(theta1));
        dLat = dNorth / 111320.0;
        dLon = dEast
          / (111320.0 * Math.cos(dr.lat * Math.PI / 180));
      } else {
        // Straight-line (no turn).
        const dist = dr.gs_ms * elapsed
          + 0.5 * dr.accel_ms2 * elapsed * elapsed;
        dLat = Math.cos(dr.trk_rad) * dist / 111320.0;
        dLon = Math.sin(dr.trk_rad) * dist
          / (111320.0 * Math.cos(dr.lat * Math.PI / 180));
      }

      const dAlt = dr.vs_ms * elapsed
        + 0.5 * dr.vs_accel_ms2 * elapsed * elapsed;

      let lat = dr.lat + dLat;
      let lon = dr.lon + dLon;
      let alt = dr.alt_m + dAlt;

      // Apply decaying blend correction.
      const blendElapsed = (now - dr.blendStart) / 1000.0;
      if (blendElapsed < BLEND_DURATION_S) {
        const t = 1.0 - blendElapsed / BLEND_DURATION_S;
        // Ease-out: correction fades smoothly.
        const w = t * t;
        lat += dr.blendLat * w;
        lon += dr.blendLon * w;
        alt += dr.blendAlt * w;
      }

      const altScaled = alt * this._altScale;
      const position = Cartesian3.fromDegrees(
        lon, lat, altScaled,
      );

      // Update point entity position + label with
      // interpolated altitude + speed.
      const ent = this._entities.get(icao);
      if (ent) {
        (ent.position as ConstantPositionProperty)
          .setValue(position);
        // Interpolated label values.
        const vs = dr.vs_ms + dr.vs_accel_ms2 * elapsed;
        const altFt = (dr.alt_m + dAlt) * 3.28084;
        const spdKt = gs / 0.514444;
        const callsign = ent.name?.replace('live-', '') || icao;
        let altLabel: string;
        if (altFt >= TRANS_LVL_FT) {
          altLabel = `FL${Math.round(altFt / 100)}`;
        } else {
          altLabel = `${Math.round(altFt)}ft`;
        }
        const vsArr = vs > 0.5 ? ' \u2191'
          : vs < -0.5 ? ' \u2193' : '';
        const drTag = dr.source === 'REPLAY' ? '(REPLAY)' : '(LIVE)';
        ent.label!.text = new ConstantProperty(
          `${callsign}\n${altLabel}${vsArr}\n${Math.round(spdKt)}\n${drTag}`,
        );
      }

      // Update leader line — use instantaneous heading
      // + speed so the leader curves during turns.
      const leader = this._leaders.get(icao);
      if (leader) {
        const vvEnd = velocityEndpoint(
          position, hdg, gs * VV_SECONDS,
        );
        leader.polyline!.positions =
          new ConstantProperty([position, vvEnd]);
      }

      // Update PZ position.
      const pz = this._pzEntities.get(icao);
      if (pz) {
        (pz.position as ConstantPositionProperty)
          .setValue(position);
      }
    }
  }

  setVisible(on: boolean): void {
    this._visible = on;
    this.source.show = on;
    this.trailSource.show = on;
    if (on) {
      this._startDrLoop();
    } else {
      this._stopDrLoop();
    }
  }

  get visible(): boolean { return this._visible; }

  setLeadersVisible(on: boolean): void {
    this._leadersVisible = on;
    for (const e of this._leaders.values()) {
      e.show = on;
    }
  }

  setTrailsVisible(on: boolean): void {
    this._trailsVisible = on;
    this.trailSource.show = on && this._visible;
  }

  setAltScale(scale: number): void {
    if (this._altScale === scale) return;
    this._altScale = scale;
    // Full re-render on alt scale change.
    this._entities.clear();
    this._leaders.clear();
    this.source.entities.removeAll();
    for (const ac of this._last) this._render(ac);
  }

  update(items: ObservedAircraft[]): void {
    this._last = items;
    const now = Date.now();
    const seen = new Set<string>();
    for (const ac of items) {
      seen.add(ac.icao24);

      // Compute blend correction: where DR thinks the
      // aircraft is right now vs where the new
      // observation says it is.  The difference
      // becomes a decaying offset applied in _drTick.
      const prev = this._dr.get(ac.icao24);
      let blendLat = 0, blendLon = 0, blendAlt = 0;
      if (prev) {
        const elapsed = (now - prev.observedAt) / 1000.0;
        const dist = prev.gs_ms * elapsed;
        const drLat = prev.lat
          + Math.cos(prev.trk_rad) * dist / 111320.0;
        const drLon = prev.lon
          + Math.sin(prev.trk_rad) * dist
          / (111320.0 * Math.cos(prev.lat * Math.PI / 180));
        const drAlt = prev.alt_m + prev.vs_ms * elapsed;
        // Blend = where-DR-says minus where-obs-says.
        // Applied as a decaying correction in drTick.
        blendLat = drLat - ac.lat;
        blendLon = drLon - ac.lon;
        blendAlt = drAlt - ac.alt_m;
      }

      // Compute acceleration from consecutive
      // observations: a = (v₁ - v₀) / Δt.
      const newGs = ac.gs_kt * 0.514444;
      const newVs = ac.vs_fpm * 0.00508;
      const newTrk = CesiumMath.toRadians(ac.trk_deg);
      let accel = 0;
      let vsAccel = 0;
      let turnRate = 0;
      if (prev) {
        const dt = (now - prev.observedAt) / 1000.0;
        if (dt > 0.5 && dt < 60) {
          // Speed acceleration.
          accel = (newGs - prev.gs_ms) / dt;
          accel = Math.max(-5, Math.min(5, accel));
          // Vertical rate change.
          vsAccel = (newVs - prev.vs_ms) / dt;
          vsAccel = Math.max(-10, Math.min(10, vsAccel));
          // Turn rate — shortest-arc heading delta.
          let dHdg = newTrk - prev.trk_rad;
          // Normalize to [-π, π].
          if (dHdg > Math.PI) dHdg -= 2 * Math.PI;
          if (dHdg < -Math.PI) dHdg += 2 * Math.PI;
          turnRate = dHdg / dt;
          // Clamp to ~6°/s (double standard rate).
          const maxTurn = 6 * Math.PI / 180;
          turnRate = Math.max(-maxTurn, Math.min(maxTurn, turnRate));
        }
      }

      // Store new DR state.
      this._dr.set(ac.icao24, {
        lat: ac.lat,
        lon: ac.lon,
        alt_m: ac.alt_m,
        gs_ms: newGs,
        trk_rad: newTrk,
        vs_ms: newVs,
        observedAt: now,
        accel_ms2: accel,
        vs_accel_ms2: vsAccel,
        turn_rad_s: turnRate,
        blendLat, blendLon, blendAlt,
        blendStart: now,
        source: ac.source || 'OPENSKY',
      });

      this._render(ac);
    }
    // Remove entities for aircraft no longer reported.
    for (const [id, ent] of this._entities) {
      if (!seen.has(id)) {
        this.source.entities.remove(ent);
        const leader = this._leaders.get(id);
        if (leader) this.source.entities.remove(leader);
        const pz = this._pzEntities.get(id);
        if (pz) this.source.entities.remove(pz);
        this._entities.delete(id);
        this._leaders.delete(id);
        this._pzEntities.delete(id);
        this._dr.delete(id);
      }
    }
  }

  private _replayTrailMode = false;

  private _trailHidden = new Set<string>();

  clearTrails(): void {
    this._trails.clear();
    this._trailEntities.clear();
    this.trailSource.entities.removeAll();
    this._replayTrailMode = false;
    this._trailHidden.clear();
  }

  isTrailVisible(icao: string): boolean {
    return !this._trailHidden.has(icao);
  }

  setTrailVisibleForAircraft(icao: string, on: boolean): void {
    if (on) {
      this._trailHidden.delete(icao);
    } else {
      this._trailHidden.add(icao);
    }
    const ent = this._trailEntities.get(icao);
    if (ent) ent.show = on;
  }

  toggleTrailForAircraft(icao: string): boolean {
    const wasVisible = this.isTrailVisible(icao);
    this.setTrailVisibleForAircraft(icao, !wasVisible);
    return !wasVisible;
  }

  getAircraftInfo(icao: string): ObservedAircraft | undefined {
    return this._last.find(a => a.icao24 === icao);
  }

  setFullTrails(
    trails: Record<string, number[][]>,
    altScale: number = this._altScale,
  ): void {
    this._replayTrailMode = true;
    const seen = new Set<string>();

    for (const [icao, points] of Object.entries(trails)) {
      if (points.length < 2) continue;
      seen.add(icao);

      const positions = points.map(p =>
        Cartesian3.fromDegrees(p[1], p[0], (p[2] || 0) * altScale),
      );

      const existing = this._trailEntities.get(icao);
      if (existing) {
        existing.polyline!.positions =
          new ConstantProperty(positions);
      } else {
        const te = this.trailSource.entities.add({
          show: !this._trailHidden.has(icao),
          polyline: {
            positions,
            width: 1.5,
            material: TRAIL_COLOR,
          },
        });
        this._trailEntities.set(icao, te);
      }
      this._trails.set(icao, positions);
    }

    for (const [id, ent] of this._trailEntities) {
      if (!seen.has(id)) {
        this.trailSource.entities.remove(ent);
        this._trailEntities.delete(id);
        this._trails.delete(id);
      }
    }
  }

  count(): number { return this._last.length; }

  // Default protected zone radius for live traffic.
  // 5 NM lateral = standard enroute separation.
  private _pzRadiusM = 5 * 1852;
  private _pzVisible = false;
  private _pzEntities = new Map<string, Entity>();
  private _confSet = new Set<string>();
  private _losSet = new Set<string>();

  updateConflicts(
    confpairs: [string, string][],
    lospairs: [string, string][],
  ): void {
    this._confSet.clear();
    this._losSet.clear();
    for (const [a, b] of lospairs) {
      this._losSet.add(a);
      this._losSet.add(b);
    }
    for (const [a, b] of confpairs) {
      this._confSet.add(a);
      this._confSet.add(b);
    }
    this._recolorPz();
  }

  private _recolorPz(): void {
    for (const [icao, pzEnt] of this._pzEntities) {
      const callsign = this._entities.get(icao)?.name
        ?.replace('live-', '') || icao;
      let color: Color;
      if (this._losSet.has(callsign) || this._losSet.has(icao)) {
        color = Color.RED.withAlpha(0.6);
      } else if (this._confSet.has(callsign) || this._confSet.has(icao)) {
        color = Color.ORANGE.withAlpha(0.5);
      } else {
        color = Color.fromAlpha(LIVE_OUTLINE, 0.4);
      }
      pzEnt.ellipse!.outlineColor = new ConstantProperty(color);
    }
  }

  setPzVisible(on: boolean): void {
    this._pzVisible = on;
    for (const e of this._pzEntities.values()) {
      e.show = on;
    }
  }

  private _render(ac: ObservedAircraft): void {
    if (ac.lat == null || ac.lon == null) return;
    const altM = ac.alt_m * this._altScale;
    const position = Cartesian3.fromDegrees(
      ac.lon, ac.lat, altM,
    );
    const key = `live-${ac.icao24}`;

    // ── Build label text ─────────────────────────────
    // Line 1: callsign + type (e.g., "AAL3192 B738")
    const callsign = ac.callsign || ac.icao24.toUpperCase();
    const typeTag = ac.typecode ? ` ${ac.typecode}` : '';
    const line1 = `${callsign}${typeTag}`;
    // Line 2: altitude + climb/descend arrow
    const altFt = ac.alt_ft;
    let altStr: string;
    if (altFt >= TRANS_LVL_FT) {
      altStr = `FL${Math.round(altFt / 100)}`;
    } else {
      altStr = `${Math.round(altFt)}ft`;
    }
    const vsArrow =
      ac.vs_fpm > 200 ? ' \u2191'
      : ac.vs_fpm < -200 ? ' \u2193' : '';
    // Line 3: speed + accel/decel arrow
    const spdKts = Math.round(ac.gs_kt);
    const prevSpd = this._prevSpd.get(ac.icao24);
    let spdArrow = '';
    if (prevSpd !== undefined) {
      const diff = ac.gs_kt - prevSpd;
      if (diff > 5) spdArrow = ' \u2191';
      else if (diff < -5) spdArrow = ' \u2193';
    }
    this._prevSpd.set(ac.icao24, ac.gs_kt);
    const sourceTag = ac.source === 'REPLAY' ? '(REPLAY)' : '(LIVE)';
    const regTag = ac.registration
      ? `${ac.registration} ${sourceTag}`
      : sourceTag;
    const labelText =
      `${line1}\n${altStr}${vsArrow}\n${spdKts}${spdArrow}\n${regTag}`;

    // ── Velocity vector endpoint ──────────────────
    const headingRad = CesiumMath.toRadians(ac.trk_deg);
    const gs_ms = ac.gs_kt * 0.514444;
    const vvEnd = velocityEndpoint(
      position, headingRad, gs_ms * VV_SECONDS,
    );

    // ── Update existing entity or create new ──────
    const existing = this._entities.get(ac.icao24);
    if (existing) {
      (existing.position as ConstantPositionProperty)
        .setValue(position);
      existing.label!.text =
        new ConstantProperty(labelText);
    } else {
      const ent = this.source.entities.add({
        id: key,
        name: key,
        position,
        point: {
          pixelSize: 6,
          color: LIVE_COLOR,
          outlineColor: LIVE_OUTLINE,
          outlineWidth: 2,
        },
        label: {
          text: labelText,
          font: '10px monospace',
          fillColor: LIVE_COLOR,
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(10, -8),
          verticalOrigin: VerticalOrigin.CENTER,
          horizontalOrigin: HorizontalOrigin.LEFT,
          showBackground: true,
          backgroundColor: LIVE_LABEL_BG,
        },
      });
      this._entities.set(ac.icao24, ent);
    }

    // ── Leader (velocity vector) line ─────────────
    const existingLeader = this._leaders.get(ac.icao24);
    if (existingLeader) {
      existingLeader.polyline!.positions =
        new ConstantProperty([position, vvEnd]);
    } else {
      const leader = this.source.entities.add({
        show: this._leadersVisible,
        polyline: {
          positions: [position, vvEnd],
          width: 1,
          material: LEADER_COLOR,
        },
      });
      this._leaders.set(ac.icao24, leader);
    }

    // ── Trail accumulation (skip in replay mode) ──
    if (this._replayTrailMode) return;
    let trail = this._trails.get(ac.icao24);
    if (!trail) {
      trail = [];
      this._trails.set(ac.icao24, trail);
    }
    trail.push(Cartesian3.clone(position));
    if (trail.length > MAX_TRAIL_POINTS) {
      trail.shift();
    }
    // Update or create trail polyline.
    if (trail.length >= 2) {
      const trailEnt = this._trailEntities.get(ac.icao24);
      if (trailEnt) {
        trailEnt.polyline!.positions =
          new ConstantProperty([...trail]);
      } else {
        const te = this.trailSource.entities.add({
          polyline: {
            positions: [...trail],
            width: 1.5,
            material: TRAIL_COLOR,
          },
        });
        this._trailEntities.set(ac.icao24, te);
      }
    }

    // ── Protected zone circle ─────────────────────
    const pzEnt = this._pzEntities.get(ac.icao24);
    if (pzEnt) {
      (pzEnt.position as ConstantPositionProperty)
        .setValue(position);
    } else {
      const pz = this.source.entities.add({
        position,
        show: this._pzVisible,
        ellipse: {
          semiMajorAxis: this._pzRadiusM,
          semiMinorAxis: this._pzRadiusM,
          height: altM,
          fill: false,
          outline: true,
          outlineColor: Color.fromAlpha(LIVE_OUTLINE, 0.4),
          outlineWidth: 1,
        },
      });
      this._pzEntities.set(ac.icao24, pz);
    }
  }
}
