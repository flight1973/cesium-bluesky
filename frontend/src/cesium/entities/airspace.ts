/**
 * Airspace restriction rendering — TFRs and SUAs.
 *
 * Same 3D-extruded-polygon pattern as SIGMETs, but
 * styled for airspace classes rather than weather
 * hazards.  Each feature carries its own ``rings``
 * (list of closed lat/lon rings — supports
 * multi-polygon definitions like fractured MOAs).
 *
 * Color conventions align with FAA chart practice:
 *
 *   TFR           → red (unified, any reason)
 *   Prohibited    → bright red (solid)
 *   Restricted    → magenta
 *   Warning       → orange
 *   Alert         → yellow
 *   MOA           → purple
 *   National Sec. → pink
 *
 * Click support via invisible pick points at each
 * polygon's centroid.
 */
import {
  Cartesian3,
  Color,
  Entity,
  PolygonHierarchy,
  Viewer,
} from 'cesium';
import { SelectionHalo } from './_selection_halo';

export interface AirspaceFeature {
  id: string;
  type: 'TFR' | 'SUA' | 'CLASS';
  // For TFRs:
  title?: string;
  notam_key?: string;
  state?: string;
  legal?: string;
  // For SUAs:
  sua_class?: string;
  sua_class_label?: string;
  sua_id?: string;
  name?: string;
  center_id?: string;
  notes?: string;
  // For Class airspace:
  airspace_class?: string;  // B / C / D / E
  local_type?: string;
  ident?: string;
  rings: [number, number][][];  // [ring][vertex][lat,lon]
  bottom_ft: number;
  top_ft: number;
}

export type AirspaceToggleKey =
  | 'TFR'
  | 'SUA_P'    // Prohibited
  | 'SUA_R'    // Restricted
  | 'SUA_W'    // Warning
  | 'SUA_A'    // Alert
  | 'SUA_M'    // MOA
  | 'CLASS_B'
  | 'CLASS_C'
  | 'CLASS_D'
  // Class E split by ARINC LOCAL_TYPE — E5 dominates
  // by ~2800 shelves (CONUS 1200-AGL blanket) so it
  // defaults off; E2/E3/E4 are tighter local volumes
  // and default on; E6 (federal airway corridors)
  // overlaps the airway polylines so it's also off.
  | 'CLASS_E2' // Surface extension
  | 'CLASS_E3' // Navaid airspace
  | 'CLASS_E4' // Transition area
  | 'CLASS_E5' // 1200-ft AGL CONUS coverage
  | 'CLASS_E6' // Federal airway corridor
  | 'CLASS_E_OTHER';

interface Style { fill: string; outline: string; }

const STYLES: Record<AirspaceToggleKey, Style> = {
  TFR: {
    fill: 'rgba(255, 40, 40, 0.20)',
    outline: '#ff3030',
  },
  SUA_P: {
    fill: 'rgba(255, 40, 40, 0.25)',
    outline: '#ff2020',
  },
  SUA_R: {
    fill: 'rgba(192, 0, 128, 0.20)',
    outline: '#cc0080',
  },
  SUA_W: {
    fill: 'rgba(255, 140, 0, 0.20)',
    outline: '#ff8800',
  },
  SUA_A: {
    fill: 'rgba(240, 220, 0, 0.18)',
    outline: '#e0c800',
  },
  SUA_M: {
    fill: 'rgba(160, 0, 220, 0.18)',
    outline: '#a020d0',
  },
  // Class airspace — FAA sectional conventions:
  // Class B = solid blue, Class C = solid magenta,
  // Class D = dashed blue, Class E = dashed magenta.
  // We approximate with fill-color hue; dashed styling
  // would need a custom outline material.
  CLASS_B: {
    fill: 'rgba(0, 102, 255, 0.12)',
    outline: '#0066ff',
  },
  CLASS_C: {
    fill: 'rgba(255, 0, 128, 0.12)',
    outline: '#ff0080',
  },
  CLASS_D: {
    fill: 'rgba(102, 170, 255, 0.10)',
    outline: '#66aaff',
  },
  // Per-subtype Class E styles — distinct hues
  // within the magenta-pink family so overlapping
  // shelves are still distinguishable.
  CLASS_E2: {
    fill: 'rgba(255, 96, 192, 0.18)',
    outline: '#ff60c0',
  },
  CLASS_E3: {
    fill: 'rgba(220, 80, 220, 0.18)',
    outline: '#dc50dc',
  },
  CLASS_E4: {
    fill: 'rgba(255, 128, 220, 0.16)',
    outline: '#ff80dc',
  },
  CLASS_E5: {
    // E5 is the giant blanket — keep alpha
    // very low so it doesn't drown other layers.
    fill: 'rgba(255, 128, 192, 0.06)',
    outline: '#ff80c0',
  },
  CLASS_E6: {
    fill: 'rgba(200, 100, 200, 0.10)',
    outline: '#c864c8',
  },
  CLASS_E_OTHER: {
    fill: 'rgba(255, 128, 192, 0.10)',
    outline: '#ff80c0',
  },
};


export class AirspaceManager {
  private entities: Map<string, Entity[]> = new Map();
  private _visibleSet: Record<AirspaceToggleKey, boolean> = {
    TFR: false,
    SUA_P: false,
    SUA_R: false,
    SUA_W: false,
    SUA_A: false,
    SUA_M: false,
    CLASS_B: false,
    CLASS_C: false,
    CLASS_D: false,
    CLASS_E2: false,
    CLASS_E3: false,
    CLASS_E4: false,
    CLASS_E5: false,
    CLASS_E6: false,
    CLASS_E_OTHER: false,
  };
  private _altScale = 1;
  private _last: AirspaceFeature[] = [];
  private _halo: SelectionHalo;
  private _selectedId: string | null = null;
  /** Per-key opacity multiplier applied at fill
   * time.  Stored as 0..1; defaults to 1 for every
   * key.  Outline alpha not multiplied — keeps
   * boundaries legible at any fill opacity. */
  private _opacity: Record<AirspaceToggleKey, number> = {
    TFR: 1, SUA_P: 1, SUA_R: 1, SUA_W: 1, SUA_A: 1,
    SUA_M: 1, CLASS_B: 1, CLASS_C: 1, CLASS_D: 1,
    CLASS_E2: 1, CLASS_E3: 1, CLASS_E4: 1,
    CLASS_E5: 1, CLASS_E6: 1, CLASS_E_OTHER: 1,
  };

  constructor(private viewer: Viewer) {
    this._halo = new SelectionHalo(viewer);
  }

  setVisibleFor(key: AirspaceToggleKey, on: boolean): void {
    this._visibleSet[key] = on;
    this._applyVisibility();
  }

  /** Set the per-key fill opacity multiplier (0..1).
   * Re-renders only the affected features. */
  setOpacityFor(key: AirspaceToggleKey, alpha: number): void {
    const a = Math.max(0, Math.min(1, alpha));
    if (this._opacity[key] === a) return;
    this._opacity[key] = a;
    // Re-render features in this key without
    // touching unrelated layers.  Simplest: full
    // re-render from cached _last.
    this.update(this._last);
  }

  getOpacityFor(key: AirspaceToggleKey): number {
    return this._opacity[key];
  }

  anyVisible(): boolean {
    return Object.values(this._visibleSet).some(Boolean);
  }

  anyTfrVisible(): boolean {
    return this._visibleSet.TFR;
  }

  anySuaVisible(): boolean {
    return this._visibleSet.SUA_P
      || this._visibleSet.SUA_R
      || this._visibleSet.SUA_W
      || this._visibleSet.SUA_A
      || this._visibleSet.SUA_M;
  }

  anyClassVisible(): boolean {
    return this._visibleSet.CLASS_B
      || this._visibleSet.CLASS_C
      || this._visibleSet.CLASS_D
      || this.anyClassEVisible();
  }

  anyClassEVisible(): boolean {
    return this._visibleSet.CLASS_E2
      || this._visibleSet.CLASS_E3
      || this._visibleSet.CLASS_E4
      || this._visibleSet.CLASS_E5
      || this._visibleSet.CLASS_E6
      || this._visibleSet.CLASS_E_OTHER;
  }

  isVisible(key: AirspaceToggleKey): boolean {
    return this._visibleSet[key];
  }

  /** Comma-joined single-letter class codes currently on. */
  visibleClassCodes(): string {
    const parts: string[] = [];
    if (this._visibleSet.CLASS_B) parts.push('B');
    if (this._visibleSet.CLASS_C) parts.push('C');
    if (this._visibleSet.CLASS_D) parts.push('D');
    if (this.anyClassEVisible()) parts.push('E');
    return parts.join(',');
  }

  setAltScale(scale: number): void {
    if (this._altScale === scale) return;
    this._altScale = scale;
    this.update(this._last);
    // Re-apply halo with new altitude band.
    if (this._selectedId) this.setSelected(this._selectedId);
  }

  update(items: AirspaceFeature[]): void {
    this._last = items;
    this.clear();
    for (const a of items) this._render(a);
    this._applyVisibility();
    // The selected feature may no longer exist in the
    // new set (e.g., after a bbox refetch); silently
    // drop the halo in that case.
    if (this._selectedId) {
      if (items.some((a) => a.id === this._selectedId)) {
        this.setSelected(this._selectedId);
      } else {
        this.setSelected(null);
      }
    }
  }

  clear(): void {
    for (const ents of this.entities.values()) {
      for (const e of ents) this.viewer.entities.remove(e);
    }
    this.entities.clear();
  }

  findByEntityId(id: string): AirspaceFeature | null {
    if (!id.startsWith('airspace-')) return null;
    // Multi-ring features stamp the extra entities as
    // ``airspace-<id>-r1``, ``-r2`` etc., so strip any
    // ring suffix before lookup.
    const key = id.slice('airspace-'.length)
      .replace(/-r\d+$/, '');
    return this._last.find((a) => a.id === key) ?? null;
  }

  /**
   * Select a single feature by id, or clear if null.
   * Draws a bright halo around the matching polygon.
   */
  setSelected(id: string | null): void {
    this._selectedId = id;
    if (!id) {
      this._halo.show(null);
      return;
    }
    const feat = this._last.find((a) => a.id === id);
    if (!feat) {
      this._halo.show(null);
      return;
    }
    this._halo.show({
      rings: feat.rings,
      bottomM: feat.bottom_ft * 0.3048 * this._altScale,
      topM: feat.top_ft * 0.3048 * this._altScale,
    });
  }

  get selectedId(): string | null { return this._selectedId; }

  /** Map a feature to its visibility key. */
  private _keyFor(a: AirspaceFeature): AirspaceToggleKey {
    if (a.type === 'TFR') return 'TFR';
    if (a.type === 'CLASS') {
      const cls = (a.airspace_class || '').toUpperCase();
      switch (cls) {
        case 'B': return 'CLASS_B';
        case 'C': return 'CLASS_C';
        case 'D': return 'CLASS_D';
        case 'E': {
          // Class E is 2800+ shelves split across
          // distinct LOCAL_TYPE roles — route to
          // the matching subtype so the user can
          // toggle E5 (CONUS blanket) off without
          // losing E2/E3/E4 (terminal-area locals).
          const lt = (a.local_type || '').toUpperCase();
          switch (lt) {
            case 'CLASS_E2': return 'CLASS_E2';
            case 'CLASS_E3': return 'CLASS_E3';
            case 'CLASS_E4': return 'CLASS_E4';
            case 'CLASS_E5': return 'CLASS_E5';
            case 'CLASS_E6': return 'CLASS_E6';
            default:         return 'CLASS_E_OTHER';
          }
        }
      }
    }
    switch ((a.sua_class || '').toUpperCase()) {
      case 'P': return 'SUA_P';
      case 'R': return 'SUA_R';
      case 'W': return 'SUA_W';
      case 'A': return 'SUA_A';
      case 'M': return 'SUA_M';
      default:  return 'SUA_R';  // fallback bucket
    }
  }

  private _applyVisibility(): void {
    for (const a of this._last) {
      const key = this._keyFor(a);
      const show = this._visibleSet[key];
      const ents = this.entities.get(a.id);
      if (ents) for (const e of ents) e.show = show;
    }
  }

  private _render(a: AirspaceFeature): void {
    if (!a.rings || a.rings.length === 0) return;
    const key = this._keyFor(a);
    const style = STYLES[key];
    const baseFill = Color.fromCssColorString(style.fill);
    // Apply per-key opacity multiplier on the fill;
    // outline keeps its native alpha so boundaries
    // remain crisp at any fill setting.
    const fillColor = baseFill.withAlpha(
      baseFill.alpha * this._opacity[key],
    );
    const outColor = Color.fromCssColorString(style.outline);
    const bottomM = a.bottom_ft * 0.3048 * this._altScale;
    const topM = a.top_ft * 0.3048 * this._altScale;

    const ents: Entity[] = [];
    for (let i = 0; i < a.rings.length; i++) {
      const ring = a.rings[i];
      if (ring.length < 3) continue;
      const positions = ring.map(
        ([lat, lon]) => Cartesian3.fromDegrees(lon, lat, 0),
      );
      const entKey = `airspace-${a.id}`;
      const ent = this.viewer.entities.add({
        id: i === 0 ? entKey : `${entKey}-r${i}`,
        name: entKey,
        polygon: {
          hierarchy: new PolygonHierarchy(positions),
          material: fillColor,
          outline: true,
          outlineColor: outColor,
          outlineWidth: 2,
          height: bottomM,
          extrudedHeight: topM,
          perPositionHeight: false,
          show: this._visibleSet[key],
        },
      });
      ents.push(ent);
    }
    this.entities.set(a.id, ents);
  }
}
