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
const COLOR_CONFLICT = Color.ORANGE;
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


export class AircraftManager {
  private entities = new Map<string, Entity>();
  private vvEntities = new Map<string, Entity>();
  private selectedAcid: string | null = null;
  private _altScale = 1.0;
  private _labelsVisible = true;
  private _leadersVisible = true;

  // Previous CAS per aircraft for accel/decel detection.
  private _prevCas = new Map<string, number>();

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

      // ── Line 2: Altitude + climb/descend arrow ───
      const altFt = alt / FT;
      let altStr: string;
      if (alt >= translvl) {
        altStr = `FL${Math.round(altFt / 100)}`;
      } else {
        altStr = `${Math.round(altFt)}ft`;
      }
      const vsArrow =
        vs > 0.5 ? '\u2191'
          : vs < -0.5 ? '\u2193' : '\u2192';

      // ── Line 3: Speed + accel/decel arrow ────────
      const spdKts = Math.round(cas / KTS);
      const prevCas = this._prevCas.get(acid);
      let spdArrow = '\u2192'; // → steady
      if (prevCas !== undefined) {
        const diff = cas - prevCas;
        // Threshold: ~1 knot change per update cycle.
        if (diff > 0.3) {
          spdArrow = '\u2191'; // ↑ accelerating
        } else if (diff < -0.3) {
          spdArrow = '\u2193'; // ↓ decelerating
        }
      }
      this._prevCas.set(acid, cas);

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
      } else if (inconf) {
        color = COLOR_CONFLICT;
      } else {
        color = COLOR_NORMAL;
      }

      const labelText =
        `${acid}\n${altStr} ${vsArrow}\n${spdKts} ${spdArrow}`;

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
    this._prevCas.delete(acid);
  }
}
