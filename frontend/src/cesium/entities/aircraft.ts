/**
 * Aircraft entity manager.
 *
 * Renders each aircraft as:
 *  - A point at its 3D position
 *  - A velocity vector line extending in the heading
 *    direction (length proportional to ground speed)
 *  - A text label (callsign + FL + speed)
 *
 * This approach works correctly in both 2D top-down and
 * 3D tilted views — the heading line always points in the
 * true world-space direction of travel, matching how real
 * ATC radar displays show traffic.
 */
import {
  Viewer,
  Entity,
  Cartesian2,
  Cartesian3,
  Color,
  VerticalOrigin,
  HorizontalOrigin,
  LabelStyle,
  Math as CesiumMath,
  ConstantProperty,
  ConstantPositionProperty,
  Transforms,
  Matrix4,
  Cartesian4,
} from 'cesium';
import type { AcData } from '../../types';
import { FT, KTS } from '../../types';

// ── Colors (matching BlueSky palette) ───────────────
const COLOR_NORMAL = Color.LIME;
const COLOR_CONFLICT = Color.ORANGE;  // predicted conflict
const COLOR_LOS = Color.RED;  // active loss of separation
const COLOR_SELECTED = Color.CYAN;

// Point size in pixels.
const DOT_PX = 7;

// Velocity vector length: seconds of travel to show.
const VV_SECONDS = 60;

// Scratch objects to avoid per-frame allocation.
const _scratchLocal = new Cartesian3();
const _scratchWorld = new Cartesian3();

/**
 * Compute the endpoint of a velocity vector line.
 *
 * From a position on the globe, extends `distance` meters
 * in the direction of `headingRad` (clockwise from north).
 */
function velocityEndpoint(
  origin: Cartesian3,
  lon: number,
  lat: number,
  headingRad: number,
  distance: number,
): Cartesian3 {
  // Build an East-North-Up frame at the origin.
  const enu = Transforms.eastNorthUpToFixedFrame(origin);

  // Heading in ENU: north = +Y, east = +X.
  const east = Math.sin(headingRad) * distance;
  const north = Math.cos(headingRad) * distance;

  Cartesian3.fromElements(east, north, 0, _scratchLocal);
  Matrix4.multiplyByPoint(enu, _scratchLocal, _scratchWorld);
  return Cartesian3.clone(_scratchWorld);
}


// Color for CPA conflict lines.
const COLOR_CPA_LINE = Color.ORANGE.withAlpha(0.6);

// Separation ring color.
const COLOR_PZ = new Color(0, 1, 0, 0.12);        // green — safe
const COLOR_PZ_PREDICT = new Color(1, 0.6, 0, 0.20); // orange — conflict predicted
const COLOR_PZ_LOS = new Color(1, 0, 0, 0.32);    // red — LoS

export class AircraftManager {
  private entities = new Map<string, Entity>();
  private vvEntities = new Map<string, Entity>();
  private cpaEntities = new Map<string, Entity>();
  private pzEntities = new Map<string, Entity>();
  private selectedAcid: string | null = null;
  private _altScale = 1.0;
  private _labelsVisible = true;
  private _leadersVisible = true;
  private _pzVisible = false;

  // Previous CAS per aircraft for accel/decel detection.
  private _prevCas = new Map<string, number>();

  // Last known position/heading per aircraft for
  // pilot-view camera tracking (always unscaled alts).
  private _lastState = new Map<string, {
    lat: number;
    lon: number;
    alt: number;
    trk: number;
  }>();

  constructor(private viewer: Viewer) {}

  /** Set altitude exaggeration factor (1 = real). */
  setAltScale(scale: number): void {
    this._altScale = scale;
  }

  get altScale(): number {
    return this._altScale;
  }

  /** Update all aircraft from an ACDATA frame. */
  update(data: AcData): void {
    const currentIds = new Set(data.id);

    // Remove departed aircraft.
    for (const [acid] of this.entities) {
      if (!currentIds.has(acid)) {
        this._removeAircraft(acid);
      }
    }

    // Transition level (meters). Default 5486m = FL180.
    const translvl = data.translvl ?? 5486;

    // Add or update each aircraft.
    for (let i = 0; i < data.id.length; i++) {
      const acid = data.id[i];
      const lat = data.lat[i];
      const lon = data.lon[i];
      const alt = data.alt[i];
      const trk = data.trk[i];
      const gs = data.gs[i];
      const cas = data.cas[i];
      const vs = data.vs[i];
      const inconf = data.inconf?.[i] ?? false;
      const inlos = data.inlos?.[i] ?? false;

      // ── Line 2: Altitude + climb/descend arrow ───
      const altFt = alt / FT;
      let altStr: string;
      if (alt >= translvl) {
        altStr = `FL${Math.round(altFt / 100)}`;
      } else {
        altStr = `${Math.round(altFt)}ft`;
      }
      // Only show arrow when actually changing.
      const vsArrow =
        vs > 0.5 ? ' \u2191'
          : vs < -0.5 ? ' \u2193' : '';

      // ── Line 3: Speed + accel/decel arrow ────────
      const spdKts = Math.round(cas / KTS);
      const prevCas = this._prevCas.get(acid);
      let spdArrow = '';
      if (prevCas !== undefined) {
        const diff = cas - prevCas;
        if (diff > 0.3) {
          spdArrow = ' \u2191';
        } else if (diff < -0.3) {
          spdArrow = ' \u2193';
        }
      }
      this._prevCas.set(acid, cas);
      this._lastState.set(acid, { lat, lon, alt, trk });

      const position = Cartesian3.fromDegrees(
        lon, lat, alt * this._altScale,
      );
      const headingRad = CesiumMath.toRadians(trk);

      // Velocity vector endpoint.
      const vvLen = gs * VV_SECONDS;
      const vvEnd = velocityEndpoint(
        position, lon, lat, headingRad, vvLen,
      );

      const isSelected = acid === this.selectedAcid;
      let color: Color;
      if (isSelected) {
        color = COLOR_SELECTED;
      } else if (inlos) {
        color = COLOR_LOS;       // red = actual LoS
      } else if (inconf) {
        color = COLOR_CONFLICT;  // orange = predicted
      } else {
        color = COLOR_NORMAL;
      }

      const labelText =
        `${acid}\n${altStr}${vsArrow}\n${spdKts}${spdArrow}`;

      // ── Update or create point + label entity ─────
      let entity = this.entities.get(acid);
      if (entity) {
        const pos =
          entity.position as ConstantPositionProperty;
        pos.setValue(position);
        entity.point!.color =
          new ConstantProperty(color);
        entity.label!.text =
          new ConstantProperty(labelText);
        entity.label!.fillColor =
          new ConstantProperty(color);
      } else {
        entity = this.viewer.entities.add({
          id: `ac-${acid}`,
          name: acid,
          position,
          point: {
            pixelSize: DOT_PX,
            color,
            outlineColor: Color.BLACK,
            outlineWidth: 1,
            // Render on top of other geometry (PZ, etc.).
            disableDepthTestDistance: Infinity,
          },
          label: {
            text: labelText,
            font: '12px monospace',
            fillColor: color,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.TOP,
            pixelOffset: new Cartesian2(12, 6),
            showBackground: true,
            backgroundColor: new Color(0, 0, 0, 0.2),
            show: this._labelsVisible,
            // Always render on top — never occluded by PZ.
            disableDepthTestDistance: Infinity,
          },
        });
        this.entities.set(acid, entity);
      }

      // ── Update or create velocity vector line ─────
      let vvEntity = this.vvEntities.get(acid);
      if (vvEntity) {
        vvEntity.polyline!.positions =
          new ConstantProperty([position, vvEnd]);
        (vvEntity.polyline!.material as any) = color;
      } else {
        vvEntity = this.viewer.entities.add({
          id: `vv-${acid}`,
          show: this._leadersVisible,
          polyline: {
            positions: [position, vvEnd],
            width: 1.5,
            material: color,
          },
        });
        this.vvEntities.set(acid, vvEntity);
      }

      // ── CPA conflict line ─────────────────────────
      const tcpa = data.tcpamax?.[i] ?? 0;
      if (inconf && tcpa > 0) {
        // Line from aircraft to predicted CPA point.
        const cpaDist = gs * tcpa;
        const cpaEnd = velocityEndpoint(
          position, lon, lat, headingRad, cpaDist,
        );
        let cpaEntity = this.cpaEntities.get(acid);
        if (cpaEntity) {
          cpaEntity.show = true;
          cpaEntity.polyline!.positions =
            new ConstantProperty([position, cpaEnd]);
        } else {
          cpaEntity = this.viewer.entities.add({
            id: `cpa-${acid}`,
            polyline: {
              positions: [position, cpaEnd],
              width: 1,
              material: COLOR_CPA_LINE,
            },
          });
          this.cpaEntities.set(acid, cpaEntity);
        }
      } else {
        // Hide CPA line when not in conflict.
        const cpaEntity = this.cpaEntities.get(acid);
        if (cpaEntity) {
          cpaEntity.show = false;
        }
      }

      // ── Protected zone cylinder (3D) ──────────────
      const rpz = data.rpz?.[i] ?? 0;
      // Default hpz = 1000 ft if not sent.
      const hpz = data.hpz?.[i] ?? 304.8;
      if (this._pzVisible && rpz > 0) {
        const pzColor = inlos
          ? COLOR_PZ_LOS
          : inconf
            ? COLOR_PZ_PREDICT
            : COLOR_PZ;
        const altScaled = alt * this._altScale;
        const hpzScaled = hpz * this._altScale;
        const bottomAlt = altScaled - hpzScaled;
        const topAlt = altScaled + hpzScaled;

        let pzEntity = this.pzEntities.get(acid);
        if (pzEntity) {
          pzEntity.show = true;
          pzEntity.position =
            new ConstantPositionProperty(position);
          pzEntity.ellipse!.semiMajorAxis =
            new ConstantProperty(rpz);
          pzEntity.ellipse!.semiMinorAxis =
            new ConstantProperty(rpz);
          pzEntity.ellipse!.height =
            new ConstantProperty(bottomAlt);
          pzEntity.ellipse!.extrudedHeight =
            new ConstantProperty(topAlt);
          (pzEntity.ellipse!.material as any) = pzColor;
          (pzEntity.ellipse!.outlineColor as any) =
            pzColor.withAlpha(0.7);
        } else {
          pzEntity = this.viewer.entities.add({
            id: `pz-${acid}`,
            position,
            ellipse: {
              semiMajorAxis: rpz,
              semiMinorAxis: rpz,
              material: pzColor,
              outline: true,
              outlineColor: pzColor.withAlpha(0.7),
              outlineWidth: 1,
              height: bottomAlt,
              extrudedHeight: topAlt,
            },
          });
          this.pzEntities.set(acid, pzEntity);
        }
      } else {
        const pzEntity = this.pzEntities.get(acid);
        if (pzEntity) {
          pzEntity.show = false;
        }
      }
    }
  }

  /** Select an aircraft (highlight it). */
  select(acid: string | null): void {
    this.selectedAcid = acid;
  }

  /** Get the currently selected aircraft ID. */
  getSelected(): string | null {
    return this.selectedAcid;
  }

  /** Toggle speed leader line visibility. */
  setLeadersVisible(visible: boolean): void {
    this._leadersVisible = visible;
    for (const vv of this.vvEntities.values()) {
      vv.show = visible;
    }
  }

  /** Toggle separation ring visibility. */
  setPzVisible(visible: boolean): void {
    this._pzVisible = visible;
    if (!visible) {
      for (const pz of this.pzEntities.values()) {
        pz.show = false;
      }
    }
  }

  /** Toggle label visibility on all aircraft. */
  setLabelsVisible(visible: boolean): void {
    this._labelsVisible = visible;
    for (const entity of this.entities.values()) {
      if (entity.label) {
        entity.label.show =
          new ConstantProperty(visible);
      }
    }
  }

  /** Number of managed aircraft entities. */
  get count(): number {
    return this.entities.size;
  }

  /** Look up the Cesium Entity for an aircraft. */
  getEntity(acid: string): Entity | null {
    return this.entities.get(acid) ?? null;
  }

  /** Get last-known position data (for pilot view). */
  getAircraftState(acid: string): {
    lat: number;
    lon: number;
    alt: number;
    trk: number;
  } | null {
    const state = this._lastState.get(acid);
    return state ?? null;
  }

  /** Remove all aircraft entities (for RESET / IC). */
  clearAll(): void {
    const ids = Array.from(this.entities.keys());
    for (const acid of ids) {
      this._removeAircraft(acid);
    }
    this.selectedAcid = null;
  }

  private _removeAircraft(acid: string): void {
    const entity = this.entities.get(acid);
    if (entity) {
      this.viewer.entities.remove(entity);
      this.entities.delete(acid);
    }
    const vv = this.vvEntities.get(acid);
    if (vv) {
      this.viewer.entities.remove(vv);
      this.vvEntities.delete(acid);
    }
    const cpa = this.cpaEntities.get(acid);
    if (cpa) {
      this.viewer.entities.remove(cpa);
      this.cpaEntities.delete(acid);
    }
    const pz = this.pzEntities.get(acid);
    if (pz) {
      this.viewer.entities.remove(pz);
      this.pzEntities.delete(acid);
    }
    this._prevCas.delete(acid);
    this._lastState.delete(acid);
  }
}
