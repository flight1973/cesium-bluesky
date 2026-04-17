/**
 * Interpolated wind-field visualization.
 *
 * Renders a grid of wind barbs showing the sampled
 * wind field at a chosen altitude.  Uses a batched
 * `PolylineCollection` primitive so rendering hundreds
 * of cells stays fast — no per-barb entities, no click
 * handling (interpolated points are read-only).
 *
 * Visually dimmer and thinner than user-defined barbs
 * (``WindBarbManager``) so the defined points remain
 * the eye-catching elements.
 */
import {
  Cartesian3,
  Color,
  Viewer,
  Transforms,
  Matrix4,
  Math as CesiumMath,
  PolylineCollection,
  Material,
} from 'cesium';

export interface WindGridCell {
  lat: number;
  lon: number;
  direction_deg: number;
  speed_kt: number;
}

// Smaller than user-defined barbs so a grid of them
// doesn't crowd the screen.
const SHAFT_LENGTH_M = 6_000;
const BARB_LENGTH_M = 2_200;
const BARB_SPACING_M = 1_100;
const FLAG_BASE_M = 1_400;
const CALM_RADIUS_M = 800;
const CALM_THRESHOLD_KT = 3;

// Interpolated field barbs: cool cyan, translucent and
// thin so a dense grid of them remains easy to look
// past toward the defined (warm-amber) barbs and the
// aircraft beneath.
const FIELD_COLOR = Color.fromCssColorString(
  'rgba(140, 200, 230, 0.45)',
);
const FIELD_WIDTH_PX = 1.2;


function addFieldBarbLines(
  pc: PolylineCollection,
  center: Cartesian3,
  dirFromDeg: number,
  speedKt: number,
  material: Material,
): void {
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

  const addLine = (a: Cartesian3, b: Cartesian3): void => {
    pc.add({
      positions: [a, b],
      width: FIELD_WIDTH_PX,
      material,
    });
  };

  if (speedKt < CALM_THRESHOLD_KT) {
    // Calm: short ring approximated by a dodecagon.
    const segs = 12;
    let prev = local(CALM_RADIUS_M, 0);
    for (let i = 1; i <= segs; i++) {
      const a = (i / segs) * Math.PI * 2;
      const next = local(
        Math.cos(a) * CALM_RADIUS_M,
        Math.sin(a) * CALM_RADIUS_M,
      );
      addLine(prev, next);
      prev = next;
    }
    return;
  }

  // Shaft.
  addLine(
    local(0, 0),
    local(fwdE * SHAFT_LENGTH_M, fwdN * SHAFT_LENGTH_M),
  );

  let remaining = Math.round(speedKt / 5) * 5;
  const nFlags = Math.floor(remaining / 50);
  remaining -= nFlags * 50;
  const nFull = Math.floor(remaining / 10);
  remaining -= nFull * 10;
  const nHalf = Math.floor(remaining / 5);

  let posAlong = SHAFT_LENGTH_M;

  // Flags rendered as triangles (3 lines) — no filled
  // polygons in a PolylineCollection, so the "solid"
  // look of a flag is approximated with the outline.
  for (let i = 0; i < nFlags; i++) {
    const apex = local(
      fwdE * posAlong + leftE * BARB_LENGTH_M,
      fwdN * posAlong + leftN * BARB_LENGTH_M,
    );
    const baseUp = local(fwdE * posAlong, fwdN * posAlong);
    const baseDown = local(
      fwdE * (posAlong - FLAG_BASE_M),
      fwdN * (posAlong - FLAG_BASE_M),
    );
    addLine(baseUp, apex);
    addLine(apex, baseDown);
    addLine(baseDown, baseUp);
    posAlong -= FLAG_BASE_M + BARB_SPACING_M * 0.5;
  }

  for (let i = 0; i < nFull; i++) {
    addLine(
      local(fwdE * posAlong, fwdN * posAlong),
      local(
        fwdE * posAlong + leftE * BARB_LENGTH_M,
        fwdN * posAlong + leftN * BARB_LENGTH_M,
      ),
    );
    posAlong -= BARB_SPACING_M;
  }

  if (nHalf > 0) {
    addLine(
      local(fwdE * posAlong, fwdN * posAlong),
      local(
        fwdE * posAlong + leftE * (BARB_LENGTH_M * 0.5),
        fwdN * posAlong + leftN * (BARB_LENGTH_M * 0.5),
      ),
    );
  }
}


export class WindFieldManager {
  private collection: PolylineCollection;
  private _visible = false;
  private _altScale = 1;
  private _material: Material;

  constructor(private viewer: Viewer) {
    this.collection = new PolylineCollection();
    this.collection.show = false;
    this.viewer.scene.primitives.add(this.collection);
    this._material = Material.fromType('Color', {
      color: FIELD_COLOR,
    });
  }

  get visible(): boolean {
    return this._visible;
  }

  setVisible(v: boolean): void {
    this._visible = v;
    this.collection.show = v;
  }

  setAltScale(scale: number): void {
    this._altScale = scale;
  }

  /** Replace all rendered cells with a new grid. */
  update(cells: WindGridCell[], altitudeFt: number): void {
    this.collection.removeAll();
    const altM = altitudeFt * 0.3048 * this._altScale;
    for (const c of cells) {
      const center = Cartesian3.fromDegrees(
        c.lon, c.lat, altM,
      );
      addFieldBarbLines(
        this.collection,
        center,
        c.direction_deg,
        c.speed_kt,
        this._material,
      );
    }
  }

  clear(): void {
    this.collection.removeAll();
  }
}
