/**
 * Wind barb rendering on the globe.
 *
 * Each user-defined wind point is rendered as a standard
 * aviation met chart wind barb:
 *
 *   calm (< 3 kt):  small circle
 *   5 kt:           one half barb
 *   10 kt:          one full barb
 *   50 kt:          one flag (pennant)
 *   combined:       stacked at the upwind end of the shaft
 *
 * Conventions follow the WMO / NOAA standard:
 * - Shaft points in the direction the wind is FROM.
 * - Decorations attach at the upwind end, on the
 *   counterclockwise (left) side of the shaft when
 *   looking along the shaft toward upwind — the
 *   Northern-Hemisphere convention, applied globally
 *   here for simplicity.
 */
import {
  Cartesian3,
  Color,
  Entity,
  Viewer,
  Transforms,
  Matrix4,
  Math as CesiumMath,
  PolygonHierarchy,
} from 'cesium';

export interface WindPoint {
  lat: number;
  lon: number;
  /** Altitude in feet.  null = surface / 2D point. */
  altitude_ft: number | null;
  /** Direction wind is *from*, degrees true. */
  direction_deg: number;
  /** Speed in knots. */
  speed_kt: number;
}

// Barb geometry in meters.
const SHAFT_LENGTH_M = 12_000;
const BARB_LENGTH_M = 4_000;
const BARB_SPACING_M = 2_000;
const FLAG_BASE_M = 2_500;
const CALM_RADIUS_M = 1_500;
const CALM_THRESHOLD_KT = 3;
// Defined (user-specified) wind barbs use a warm amber
// so they read as distinct from the cool cyan
// interpolated field.  Muted enough to avoid
// overpowering other map layers.
const BARB_COLOR = Color.fromCssColorString('#ffcd66');
const BARB_WIDTH_PX = 2;


function buildBarbGeometry(
  center: Cartesian3,
  dirFromDeg: number,
  speedKt: number,
): { lines: Cartesian3[][]; flags: Cartesian3[][] } {
  const lines: Cartesian3[][] = [];
  const flags: Cartesian3[][] = [];

  const enu = Transforms.eastNorthUpToFixedFrame(center);
  const dir = CesiumMath.toRadians(dirFromDeg);
  const fwdE = Math.sin(dir);
  const fwdN = Math.cos(dir);
  const leftE = -Math.cos(dir);
  const leftN = Math.sin(dir);

  const local = (e: number, n: number): Cartesian3 => {
    const offset = new Cartesian3(e, n, 0);
    const world = new Cartesian3();
    Matrix4.multiplyByPoint(enu, offset, world);
    return world;
  };

  // Calm: circle.
  if (speedKt < CALM_THRESHOLD_KT) {
    const segments = 16;
    const pts: Cartesian3[] = [];
    for (let i = 0; i <= segments; i++) {
      const a = (i / segments) * Math.PI * 2;
      pts.push(local(
        Math.cos(a) * CALM_RADIUS_M,
        Math.sin(a) * CALM_RADIUS_M,
      ));
    }
    lines.push(pts);
    return { lines, flags };
  }

  // Shaft.
  lines.push([
    local(0, 0),
    local(fwdE * SHAFT_LENGTH_M, fwdN * SHAFT_LENGTH_M),
  ]);

  // Decompose speed.
  let remaining = Math.round(speedKt / 5) * 5;
  const nFlags = Math.floor(remaining / 50);
  remaining -= nFlags * 50;
  const nFullBarbs = Math.floor(remaining / 10);
  remaining -= nFullBarbs * 10;
  const nHalfBarbs = Math.floor(remaining / 5);

  let posAlong = SHAFT_LENGTH_M;

  for (let i = 0; i < nFlags; i++) {
    const apex = local(
      fwdE * posAlong + leftE * BARB_LENGTH_M,
      fwdN * posAlong + leftN * BARB_LENGTH_M,
    );
    const baseUp = local(
      fwdE * posAlong, fwdN * posAlong,
    );
    const baseDown = local(
      fwdE * (posAlong - FLAG_BASE_M),
      fwdN * (posAlong - FLAG_BASE_M),
    );
    flags.push([baseUp, apex, baseDown]);
    posAlong -= FLAG_BASE_M + BARB_SPACING_M * 0.5;
  }

  for (let i = 0; i < nFullBarbs; i++) {
    lines.push([
      local(fwdE * posAlong, fwdN * posAlong),
      local(
        fwdE * posAlong + leftE * BARB_LENGTH_M,
        fwdN * posAlong + leftN * BARB_LENGTH_M,
      ),
    ]);
    posAlong -= BARB_SPACING_M;
  }

  if (nHalfBarbs > 0) {
    lines.push([
      local(fwdE * posAlong, fwdN * posAlong),
      local(
        fwdE * posAlong + leftE * (BARB_LENGTH_M * 0.5),
        fwdN * posAlong + leftN * (BARB_LENGTH_M * 0.5),
      ),
    ]);
  }

  return { lines, flags };
}


export class WindBarbManager {
  /** Entities per wind point, keyed by stable id. */
  private entities: Map<string, Entity[]> = new Map();
  private _visible = true;
  private _altScale = 1;
  private _lastPoints: WindPoint[] = [];

  constructor(private viewer: Viewer) {}

  get visible(): boolean {
    return this._visible;
  }

  setVisible(v: boolean): void {
    this._visible = v;
    for (const ents of this.entities.values()) {
      for (const e of ents) e.show = v;
    }
  }

  setAltScale(scale: number): void {
    if (this._altScale === scale) return;
    this._altScale = scale;
    // Re-render with the new scale.
    this.update(this._lastPoints);
  }

  /** Replace the displayed barbs with a new set. */
  update(points: WindPoint[]): void {
    this._lastPoints = points.map((p) => ({ ...p }));
    this.clear();
    for (const p of points) this._render(p);
  }

  clear(): void {
    for (const ents of this.entities.values()) {
      for (const e of ents) this.viewer.entities.remove(e);
    }
    this.entities.clear();
  }

  private _keyFor(p: WindPoint): string {
    return (
      `windpin-${p.lat.toFixed(4)}-`
      + `${p.lon.toFixed(4)}-${p.altitude_ft ?? 'any'}`
    );
  }

  private _render(p: WindPoint): void {
    const altM = (p.altitude_ft ?? 0) * 0.3048 * this._altScale;
    const center = Cartesian3.fromDegrees(p.lon, p.lat, altM);
    const { lines, flags } = buildBarbGeometry(
      center, p.direction_deg, p.speed_kt,
    );

    const ents: Entity[] = [];
    const key = this._keyFor(p);

    // Polyline entities for shaft + barbs + calm circle.
    for (const positions of lines) {
      ents.push(this.viewer.entities.add({
        polyline: {
          positions,
          width: BARB_WIDTH_PX,
          material: BARB_COLOR,
          clampToGround: false,
          show: this._visible,
        },
      }));
    }

    // Filled polygon entities for flags (pennants).
    for (const tri of flags) {
      ents.push(this.viewer.entities.add({
        polygon: {
          hierarchy: new PolygonHierarchy(tri),
          material: BARB_COLOR,
          perPositionHeight: true,
          outline: true,
          outlineColor: BARB_COLOR,
          outlineWidth: BARB_WIDTH_PX,
          show: this._visible,
        },
      }));
    }

    // Invisible pick point at the observation location
    // so clicking on / near the barb selects it.  The
    // entity's name/id is used by the toolbar to look
    // up the underlying WindPoint.
    ents.push(this.viewer.entities.add({
      id: key,
      name: key,
      position: center,
      point: {
        pixelSize: 18,
        color: Color.TRANSPARENT,
        outlineColor: Color.TRANSPARENT,
        show: this._visible,
      },
    }));

    this.entities.set(key, ents);
  }

  /** Get the WindPoint for a given entity id, or null. */
  findPointByEntityId(id: string): WindPoint | null {
    if (!id.startsWith('windpin-')) return null;
    for (const p of this._lastPoints) {
      if (this._keyFor(p) === id) return p;
    }
    return null;
  }
}
