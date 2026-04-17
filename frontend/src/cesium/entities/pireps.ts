/**
 * PIREP entity manager — pilot reports as 3D-
 * positioned points on the globe.
 *
 * Each PIREP is a single point with published
 * altitude (``alt_ft``), so we render at the
 * reported flight level.  Colored by the first
 * hazard keyword we find in the raw text
 * (turbulence, icing, visibility, clouds) so
 * operators can scan for trouble at a glance.
 *
 * Click opens a panel with the decoded narrative
 * — the raw report string is standardized UA text
 * that reads naturally with a small decoder.
 */
import {
  Viewer,
  Cartesian2,
  Cartesian3,
  Color,
  CustomDataSource,
  VerticalOrigin,
  LabelStyle,
  HorizontalOrigin,
} from 'cesium';

export interface PirepReport {
  id: string;
  icao: string | null;
  lat: number;
  lon: number;
  fl_100ft: number | null;     // hundreds of feet
  alt_ft: number | null;        // explicit feet for renderers
  ac_type: string | null;
  aircraft: string | null;
  obs_time: string | null;
  raw: string;
}

/** Keyword → (fill, outline) for hazard coloring. */
const HAZ_KEYWORDS: Array<[RegExp, string, string]> = [
  // Order matters — earlier matches win.
  [/ TB\b|TURB\b|CHOP\b/i, '#A06000', '#8a5000'],  // turbulence
  [/ IC\b|ICE|ICNG\b/i,    '#1e3fbf', '#0a1e7a'],  // icing
  [/ WX\b|TS\b|CB\b/i,     '#800000', '#5a0000'],  // convective
  [/ LLWS\b|WS\b/i,        '#990099', '#6b006b'],  // wind shear
];
const NEUTRAL_FILL = '#3fbf3f';
const NEUTRAL_OUTLINE = '#0f7a0f';


export class PirepManager {
  private source: CustomDataSource;
  private _visible = false;
  private _altScale = 1.0;
  private _opacity = 1.0;
  private _last: PirepReport[] = [];

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('pireps');
    viewer.dataSources.add(this.source);
    this.source.show = this._visible;
  }

  setVisible(v: boolean): void {
    this._visible = v;
    this.source.show = v;
  }

  anyVisible(): boolean { return this._visible; }

  setAltScale(scale: number): void {
    if (this._altScale === scale) return;
    this._altScale = scale;
    this.update(this._last);
  }

  /** Multiply marker + label alpha by ``alpha`` (0..1). */
  setOpacity(alpha: number): void {
    const a = Math.max(0, Math.min(1, alpha));
    if (this._opacity === a) return;
    this._opacity = a;
    this.update(this._last);
  }

  getOpacity(): number { return this._opacity; }

  update(items: PirepReport[]): void {
    this._last = items;
    this.source.entities.removeAll();
    for (const p of items) this._render(p);
  }

  /** Find a report by entity id for click handling. */
  findByEntityId(id: string): PirepReport | null {
    if (!id.startsWith('pirep-')) return null;
    const key = id.slice('pirep-'.length);
    return this._last.find((p) => p.id === key) ?? null;
  }

  private _hazardColors(raw: string): [string, string] {
    for (const [re, fill, out] of HAZ_KEYWORDS) {
      if (re.test(raw)) return [fill, out];
    }
    return [NEUTRAL_FILL, NEUTRAL_OUTLINE];
  }

  private _render(p: PirepReport): void {
    const altFt = p.alt_ft ?? 0;
    const altM = altFt * 0.3048 * this._altScale;
    const [fill, outline] = this._hazardColors(p.raw || '');
    const fillC = Color.fromCssColorString(fill).withAlpha(this._opacity);
    const outC = Color.fromCssColorString(outline).withAlpha(this._opacity);
    // Short label: aircraft type + FL.  The full
    // report text goes into the click-opened panel.
    const ac = p.ac_type || '';
    const flStr = p.fl_100ft != null ? `FL${p.fl_100ft}` : '';
    const label = [ac, flStr].filter(Boolean).join(' ');
    const key = `pirep-${p.id}`;

    this.source.entities.add({
      id: key,
      name: key,
      position: Cartesian3.fromDegrees(p.lon, p.lat, altM),
      point: {
        pixelSize: 8,
        color: fillC,
        outlineColor: outC,
        outlineWidth: 2,
      },
      label: label ? {
        text: label,
        font: '10px monospace',
        fillColor: fillC,
        outlineColor: Color.BLACK.withAlpha(this._opacity),
        outlineWidth: 2,
        style: LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cartesian2(10, 0),
        verticalOrigin: VerticalOrigin.CENTER,
        horizontalOrigin: HorizontalOrigin.LEFT,
        showBackground: true,
        backgroundColor: new Color(0, 0, 0, 0.55 * this._opacity),
      } : undefined,
    });
  }
}
