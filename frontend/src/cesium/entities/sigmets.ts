/**
 * AIRMET / SIGMET polygon rendering.
 *
 * Each advisory is a 3D extruded polygon between its
 * ``bottom_ft`` and ``top_ft`` altitudes, colored by
 * hazard type.  The shape stays visible from any
 * camera angle, so it's easy to tell at a glance
 * whether an aircraft's flight path intersects a
 * hazard band.
 */
import {
  Cartesian3,
  Color,
  Entity,
  PolygonHierarchy,
  Viewer,
} from 'cesium';
import { SelectionHalo } from './_selection_halo';

export interface SigmetAdvisory {
  id: string;
  type: string | null;     // SIGMET / AIRMET / ...
  hazard: string | null;   // CONVECTIVE, TURB, ICE, ...
  severity: number | null;
  valid_from: number | null;
  valid_to: number | null;
  bottom_ft: number;
  top_ft: number;
  movement_dir: number | null;
  movement_spd: number | null;
  coords: [number, number][]; // [lat, lon] pairs
  raw: string | null;
  icao: string | null;
}

// Hazard palette reverse-engineered from the
// aviationweather.gov GFA tool's actual renderer
// (minified ``class Ve`` / getColor + getFeatureColor
// functions in its map JS bundle).  These are the
// exact hex values AWC uses in production, so our
// rendering matches theirs pixel-for-pixel in hue.
//
// Fill is the same hue at 0.25 alpha; outline is the
// opaque hex.
//
//   SIGMET class (primary hazards):
//     TS / TC / default → #800000  (dark maroon)
//     ICE               → #000080  (navy)
//     TURB              → #A06000  (dark orange-brown)
//     VA / ASH          → #FF5F15  (vivid orange)
//     IFR               → #990099  (purple)
//     OUTLOOK modifier  → #FFAA00  (gold)
//
//   G-AIRMET class (brighter/informational variants):
//     ICE               → #8080FF outline / #0000FF text
//     TURB              → #FFA000
//     IFR / PCPN        → #FF00FF
//     MT-OBSC / MTN-OBSCN → #FF00FF
//     default highlight  → #FF8080
const HAZARD_COLORS: Record<string,
  { fill: string; outline: string }> = {
  // Convective SIGMETs fall through to the AWC
  // default maroon in their SIGMET class.
  CONVECTIVE: {
    fill: 'rgba(128, 0, 0, 0.25)',
    outline: '#800000',
  },
  TS: {
    fill: 'rgba(128, 0, 0, 0.25)',
    outline: '#800000',
  },
  TC: {
    fill: 'rgba(128, 0, 0, 0.25)',
    outline: '#800000',
  },
  TURB: {
    fill: 'rgba(160, 96, 0, 0.25)',
    outline: '#A06000',
  },
  ICE: {
    fill: 'rgba(0, 0, 128, 0.25)',
    outline: '#000080',
  },
  IFR: {
    fill: 'rgba(153, 0, 153, 0.25)',
    outline: '#990099',
  },
  // Mountain obscuration: AWC treats it as an AIRMET-
  // family hazard with the brighter magenta variant.
  MT_OBSC: {
    fill: 'rgba(255, 0, 255, 0.22)',
    outline: '#FF00FF',
  },
  MTN_OBSCN: {
    fill: 'rgba(255, 0, 255, 0.22)',
    outline: '#FF00FF',
  },
  VA: {
    fill: 'rgba(255, 95, 21, 0.25)',
    outline: '#FF5F15',
  },
  ASH: {
    fill: 'rgba(255, 95, 21, 0.25)',
    outline: '#FF5F15',
  },
};
const DEFAULT_COLORS = {
  fill: 'rgba(128, 0, 0, 0.25)',
  outline: '#800000',
};


export type AdvisoryType = 'SIGMET' | 'AIRMET' | 'G-AIRMET';

export class SigmetManager {
  private entities: Map<string, Entity[]> = new Map();
  private _visibleSet: Record<AdvisoryType, boolean> = {
    SIGMET: false,
    AIRMET: false,
    'G-AIRMET': false,
  };
  private _altScale = 1;
  private _last: SigmetAdvisory[] = [];
  private _halo: SelectionHalo;
  private _selectedId: string | null = null;
  /** Per-type fill-opacity multiplier (0..1); 1 = native. */
  private _opacity: Record<AdvisoryType, number> = {
    SIGMET: 1, AIRMET: 1, 'G-AIRMET': 1,
  };

  constructor(private viewer: Viewer) {
    this._halo = new SelectionHalo(viewer);
  }

  /**
   * Turn a category on/off.  SIGMET covers convective
   * / turb / ice SIGMETs; AIRMET covers text AIRMETs;
   * G-AIRMET covers the graphical AIRMET product.
   * Each is independently toggleable.
   */
  setVisibleFor(
    type: AdvisoryType,
    on: boolean,
  ): void {
    this._visibleSet[type] = on;
    this._applyVisibility();
  }

  /** Set per-type fill opacity (0..1).  Re-renders. */
  setOpacityFor(type: AdvisoryType, alpha: number): void {
    const a = Math.max(0, Math.min(1, alpha));
    if (this._opacity[type] === a) return;
    this._opacity[type] = a;
    this.update(this._last);
  }

  getOpacityFor(type: AdvisoryType): number {
    return this._opacity[type];
  }

  anyVisible(): boolean {
    return this._visibleSet.SIGMET
      || this._visibleSet.AIRMET
      || this._visibleSet['G-AIRMET'];
  }

  setAltScale(scale: number): void {
    if (this._altScale === scale) return;
    this._altScale = scale;
    // Re-render to apply new extrusion heights.
    this.update(this._last);
    if (this._selectedId) this.setSelected(this._selectedId);
  }

  /** Replace the displayed set with a fresh list. */
  update(items: SigmetAdvisory[]): void {
    this._last = items;
    this.clear();
    for (const a of items) this._render(a);
    this._applyVisibility();
    if (this._selectedId) {
      if (items.some((a) => a.id === this._selectedId)) {
        this.setSelected(this._selectedId);
      } else {
        this.setSelected(null);
      }
    }
  }

  /** Draw a bright halo around the selected advisory. */
  setSelected(id: string | null): void {
    this._selectedId = id;
    if (!id) {
      this._halo.show(null);
      return;
    }
    const adv = this._last.find((a) => a.id === id);
    if (!adv) {
      this._halo.show(null);
      return;
    }
    this._halo.show({
      rings: [adv.coords],
      bottomM: adv.bottom_ft * 0.3048 * this._altScale,
      topM: adv.top_ft * 0.3048 * this._altScale,
    });
  }

  get selectedId(): string | null { return this._selectedId; }

  clear(): void {
    for (const ents of this.entities.values()) {
      for (const e of ents) this.viewer.entities.remove(e);
    }
    this.entities.clear();
  }

  /** Find advisory from an entity id (for click handling). */
  findByEntityId(id: string): SigmetAdvisory | null {
    if (!id.startsWith('sigmet-')) return null;
    const key = id.slice('sigmet-'.length);
    return this._last.find((a) => a.id === key) ?? null;
  }

  private _isAdvisoryVisible(a: SigmetAdvisory): boolean {
    const t = (a.type || '').toUpperCase();
    if (t === 'SIGMET') return this._visibleSet.SIGMET;
    // Text AIRMETs are almost always empty in the
    // modern feed; when they appear we show them
    // alongside G-AIRMETs since they describe the same
    // underlying advisory.
    if (t === 'AIRMET' || t === 'G-AIRMET') {
      return this._visibleSet['G-AIRMET'];
    }
    // Unknown types (CWA, etc.) bundle under G-AIRMET.
    return this._visibleSet['G-AIRMET'];
  }

  private _applyVisibility(): void {
    for (const a of this._last) {
      const show = this._isAdvisoryVisible(a);
      const ents = this.entities.get(a.id);
      if (ents) for (const e of ents) e.show = show;
    }
  }

  private _render(a: SigmetAdvisory): void {
    if (a.coords.length < 3) return;
    const haz = (a.hazard || '').toUpperCase();
    const colors = HAZARD_COLORS[haz] || DEFAULT_COLORS;
    const baseFill = Color.fromCssColorString(colors.fill);
    // Apply per-type opacity multiplier so the
    // SIGMET / AIRMET / G-AIRMET buckets dim
    // independently.  CWAs and ISIGMETs share
    // their parent type and inherit the same
    // multiplier — reasonable since they're folded
    // in for rendering.
    const t = (a.type || '').toUpperCase();
    const bucket: AdvisoryType = (
      t === 'SIGMET' ? 'SIGMET'
      : t === 'AIRMET' ? 'AIRMET'
      : 'G-AIRMET'
    );
    const fillColor = baseFill.withAlpha(
      baseFill.alpha * this._opacity[bucket],
    );
    const outColor = Color.fromCssColorString(colors.outline);

    const bottomM = a.bottom_ft * 0.3048 * this._altScale;
    const topM = a.top_ft * 0.3048 * this._altScale;

    // Build the polygon positions (lat/lon pairs).
    const positions = a.coords.map(
      ([lat, lon]) => Cartesian3.fromDegrees(lon, lat, 0),
    );

    const key = `sigmet-${a.id}`;
    const ent = this.viewer.entities.add({
      id: key,
      name: key,
      polygon: {
        hierarchy: new PolygonHierarchy(positions),
        material: fillColor,
        outline: true,
        outlineColor: outColor,
        outlineWidth: 2,
        height: bottomM,
        extrudedHeight: topM,
        perPositionHeight: false,
        show: this._isAdvisoryVisible(a),
      },
    });
    this.entities.set(a.id, [ent]);
  }
}
