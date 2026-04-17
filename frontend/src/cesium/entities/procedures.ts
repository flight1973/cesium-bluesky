/**
 * Procedure entity manager — renders compiled CIFP
 * SID / STAR / IAP polylines on the globe.
 *
 * The backend ships ``polyline: [[lat, lon, hae_m,
 * msl_ft], ...]`` and ``fixes: [{fix_ident,
 * leg_type, lat, lon, alt_hae_m, alt_1_ft,
 * speed_kt}, ...]`` — the client just has to turn
 * lat/lon/HAE triples into ``Cartesian3`` and draw
 * a dashed polyline plus per-fix altitude labels.
 *
 * Multiple procedures can be displayed at once; each
 * is keyed by its stable ``procedure_id``
 * (e.g., ``KDFW-IAP-H13RZ-ALL``).  Colors follow
 * Jeppesen chart convention:
 *
 *   SID  → green   (departure)
 *   STAR → cyan    (arrival)
 *   IAP  → magenta (final approach)
 */
import {
  Viewer,
  Cartesian2,
  Cartesian3,
  Color,
  CustomDataSource,
  PolylineDashMaterialProperty,
  VerticalOrigin,
  HorizontalOrigin,
  LabelStyle,
} from 'cesium';

export interface CompiledProcedure {
  id: string;
  compiled: boolean;
  polyline?: [number, number, number, number][]; // lat, lon, hae_m, msl_ft
  fixes?: {
    fix_ident: string;
    leg_type: string;
    lat?: number;
    lon?: number;
    alt_hae_m?: number;
    alt_1_ft?: number | null;
    speed_kt?: number | null;
  }[];
}

const COLORS = {
  SID: Color.fromCssColorString('#30e030'),
  STAR: Color.fromCssColorString('#30d0e0'),
  IAP: Color.fromCssColorString('#e040e0'),
  DEFAULT: Color.WHITE,
};

function colorFor(id: string): Color {
  if (id.includes('-SID-')) return COLORS.SID;
  if (id.includes('-STAR-')) return COLORS.STAR;
  if (id.includes('-IAP-')) return COLORS.IAP;
  return COLORS.DEFAULT;
}

export class ProcedureManager {
  private source: CustomDataSource;
  private _shown = new Map<string, CompiledProcedure>();
  private _altScale = 1.0;
  private _opacity = 1.0;

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('procedures');
    viewer.dataSources.add(this.source);
  }

  /** Multiply polyline + label alpha by ``alpha`` (0..1). */
  setOpacity(alpha: number): void {
    const a = Math.max(0, Math.min(1, alpha));
    if (this._opacity === a) return;
    this._opacity = a;
    const current = Array.from(this._shown.values());
    this.source.entities.removeAll();
    for (const p of current) this._render(p);
  }

  getOpacity(): number { return this._opacity; }

  /**
   * Toggle a compiled procedure on/off.  Same API as
   * the airspace / SIGMET managers so the side panel
   * just calls ``show(id, geom)`` or ``hide(id)``.
   */
  show(proc: CompiledProcedure): void {
    if (!proc.compiled || !proc.polyline) return;
    this.hide(proc.id);
    this._shown.set(proc.id, proc);
    this._render(proc);
  }

  hide(id: string): void {
    this._shown.delete(id);
    // Remove by name prefix.
    const ents = this.source.entities.values.slice();
    for (const e of ents) {
      if (e.name && e.name.startsWith(`proc-${id}-`)) {
        this.source.entities.remove(e);
      }
    }
  }

  isShown(id: string): boolean {
    return this._shown.has(id);
  }

  shownIds(): string[] {
    return Array.from(this._shown.keys());
  }

  clear(): void {
    this._shown.clear();
    this.source.entities.removeAll();
  }

  setAltScale(scale: number): void {
    if (this._altScale === scale) return;
    this._altScale = scale;
    // Rebuild everything so altitudes reflect the
    // new exaggeration.
    const current = Array.from(this._shown.values());
    this.source.entities.removeAll();
    for (const p of current) this._render(p);
  }

  private _render(proc: CompiledProcedure): void {
    const pts = proc.polyline;
    if (!pts || pts.length < 2) return;
    const baseColor = colorFor(proc.id);
    // Apply manager-level opacity to the polyline +
    // labels.  Selected/halo elements live on the
    // SelectionHalo and aren't dimmed.
    const color = baseColor.withAlpha(this._opacity);
    const dashColor = color;
    const scale = this._altScale;
    const entKeyBase = `proc-${proc.id}`;

    // Flatten [lat, lon, hae_m] → Cesium positions.
    const positions: Cartesian3[] = pts.map(
      ([lat, lon, hae_m]) => Cartesian3.fromDegrees(
        lon, lat, hae_m * scale,
      ),
    );

    this.source.entities.add({
      id: `${entKeyBase}-line`,
      name: `${entKeyBase}-line`,
      polyline: {
        positions,
        width: 3,
        material: new PolylineDashMaterialProperty({
          color: dashColor,
          dashLength: 16,
        }),
      },
    });

    // Per-fix altitude / speed labels at annotated fixes.
    if (proc.fixes) {
      for (const f of proc.fixes) {
        if (f.lat == null || f.lon == null) continue;
        const altM = (f.alt_hae_m ?? 0) * scale;
        const altLabel = f.alt_1_ft != null
          ? `${Math.round(f.alt_1_ft)} ft`
          : '';
        const spdLabel = f.speed_kt != null
          ? ` / ${f.speed_kt} kt`
          : '';
        const details = `${altLabel}${spdLabel}`.trim();
        const text = details
          ? `${f.fix_ident}\n${details}`
          : f.fix_ident;
        this.source.entities.add({
          name: `${entKeyBase}-fix-${f.fix_ident}`,
          position: Cartesian3.fromDegrees(
            f.lon, f.lat, altM,
          ),
          point: {
            pixelSize: 5,
            color,
            outlineColor: Color.BLACK,
            outlineWidth: 1,
          },
          label: {
            text,
            font: '10px monospace',
            fillColor: color,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            style: LabelStyle.FILL_AND_OUTLINE,
            pixelOffset: new Cartesian2(8, -4),
            verticalOrigin: VerticalOrigin.CENTER,
            horizontalOrigin: HorizontalOrigin.LEFT,
            showBackground: true,
            backgroundColor: new Color(0, 0, 0, 0.55),
          },
        });
      }
    }
  }
}
