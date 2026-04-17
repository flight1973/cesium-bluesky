/**
 * METAR station rendering.
 *
 * Each station is a small dot colored by flight
 * category, with its ICAO identifier as a label.
 * Clicking a station opens the METAR detail panel.
 *
 * Color convention matches FAA standard:
 *   VFR   — green   (visibility > 5 SM, ceiling > 3000 ft)
 *   MVFR  — blue    (3–5 SM, 1000–3000 ft)
 *   IFR   — red     (1–3 SM, 500–1000 ft)
 *   LIFR  — magenta (< 1 SM, < 500 ft)
 *   unknown — white
 */
import {
  Cartesian3,
  Color,
  Entity,
  HorizontalOrigin,
  VerticalOrigin,
  LabelStyle,
  Viewer,
} from 'cesium';

export interface MetarObs {
  icao: string;
  name?: string;
  lat: number;
  lon: number;
  elev_m?: number | null;
  obs_time?: string;
  temp_c?: number | null;
  dewp_c?: number | null;
  wdir_deg?: number | null;
  wspd_kt?: number | null;
  wgst_kt?: number | null;
  visib?: string | null;
  altim_hpa?: number | null;
  cover?: string | null;
  clouds?: any[];
  flt_cat?: string | null;
  raw?: string | null;
  decoded?: string | null;
}

const CAT_COLORS: Record<string, Color> = {
  VFR: Color.fromCssColorString('#3fbf3f'),
  MVFR: Color.fromCssColorString('#4080ff'),
  IFR: Color.fromCssColorString('#ff4040'),
  LIFR: Color.fromCssColorString('#ff40c0'),
};

const DEFAULT_COLOR = Color.fromCssColorString('#dddddd');

const DOT_PX = 8;
const LABEL_FONT = "10px 'Consolas', 'Courier New', monospace";


export class MetarManager {
  private entities: Map<string, Entity> = new Map();
  private _visible = false;
  private _last: MetarObs[] = [];

  constructor(private viewer: Viewer) {}

  get visible(): boolean { return this._visible; }

  setVisible(v: boolean): void {
    this._visible = v;
    for (const e of this.entities.values()) {
      e.show = v;
    }
  }

  /** Replace all displayed METARs with a fresh set. */
  update(metars: MetarObs[]): void {
    this._last = metars;
    // Build a set of new keys.
    const nextKeys = new Set(metars.map((m) => m.icao));
    // Remove stale entries.
    for (const [icao, ent] of this.entities) {
      if (!nextKeys.has(icao)) {
        this.viewer.entities.remove(ent);
        this.entities.delete(icao);
      }
    }
    // Upsert.
    for (const m of metars) {
      this._upsert(m);
    }
  }

  clear(): void {
    for (const ent of this.entities.values()) {
      this.viewer.entities.remove(ent);
    }
    this.entities.clear();
    this._last = [];
  }

  /** Look up a METAR observation by entity id. */
  findByEntityId(id: string): MetarObs | null {
    if (!id.startsWith('metar-')) return null;
    const icao = id.slice(6);
    return this._last.find((m) => m.icao === icao) ?? null;
  }

  private _upsert(m: MetarObs): void {
    const pos = Cartesian3.fromDegrees(m.lon, m.lat, 0);
    const color = (m.flt_cat && CAT_COLORS[m.flt_cat])
      || DEFAULT_COLOR;
    const existing = this.entities.get(m.icao);
    if (existing) {
      existing.position = pos as any;
      if (existing.point) {
        existing.point.color = color as any;
      }
      existing.show = this._visible;
      return;
    }
    const ent = this.viewer.entities.add({
      id: `metar-${m.icao}`,
      name: `metar-${m.icao}`,
      position: pos,
      show: this._visible,
      point: {
        pixelSize: DOT_PX,
        color,
        outlineColor: Color.BLACK,
        outlineWidth: 1,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: m.icao,
        font: LABEL_FONT,
        fillColor: Color.WHITE,
        outlineColor: Color.BLACK,
        outlineWidth: 2,
        style: LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cartesian3(0, -14, 0) as any,
        horizontalOrigin: HorizontalOrigin.CENTER,
        verticalOrigin: VerticalOrigin.BOTTOM,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        show: true,
      },
    });
    this.entities.set(m.icao, ent);
  }
}
