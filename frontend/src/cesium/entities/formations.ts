/**
 * Formation rendering on the Cesium globe.
 *
 * Draws:
 *   - A dashed line from leader → each follower
 *   - A slot-position marker at the follower's assigned
 *     offset (wake-surfing target)
 *   - A small leader badge with formation id + size
 *
 * Color-coded per formation. Toggleable via layer panel.
 */
import {
  Cartesian3,
  Color,
  CustomDataSource,
  Entity,
  LabelStyle,
  HorizontalOrigin,
  VerticalOrigin,
  ConstantProperty,
  PolylineDashMaterialProperty,
  Viewer,
} from 'cesium';

interface FormationData {
  id: string;
  type: string;
  leader: string;
  followers: string[];
  size: number;
  separation_nm: number;
  slots?: Record<string, { forward_m: number; right_m: number; up_m: number }>;
}

interface Aircraft {
  icao24: string;
  callsign: string;
  lat: number;
  lon: number;
  alt_m: number;
}

const PALETTE: Color[] = [
  Color.fromCssColorString('#00ccff'),
  Color.fromCssColorString('#ff44aa'),
  Color.fromCssColorString('#ffcc00'),
  Color.fromCssColorString('#44ff88'),
  Color.fromCssColorString('#aa88ff'),
  Color.fromCssColorString('#ff6644'),
];


export class FormationManager {
  private source: CustomDataSource;
  private _visible = false;
  private _formations: FormationData[] = [];
  private _lines = new Map<string, Entity>();
  private _badges = new Map<string, Entity>();

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('formations');
    viewer.dataSources.add(this.source);
    this.source.show = false;
  }

  setVisible(on: boolean): void {
    this._visible = on;
    this.source.show = on;
  }

  get visible(): boolean { return this._visible; }

  setFormations(formations: FormationData[]): void {
    this._formations = formations;
    // Badges only need to be recreated when formation list changes.
    this._rebuildBadges();
  }

  /** Update rendered lines given the current aircraft positions. */
  update(aircraft: Aircraft[]): void {
    if (!this._visible) return;

    const byCallsign = new Map<string, Aircraft>();
    for (const ac of aircraft) {
      byCallsign.set(ac.callsign.trim(), ac);
      byCallsign.set(ac.icao24.toLowerCase(), ac);
    }

    const seenLines = new Set<string>();
    const seenBadges = new Set<string>();

    this._formations.forEach((f, idx) => {
      const color = PALETTE[idx % PALETTE.length];
      const leader = byCallsign.get(f.leader) ||
                     byCallsign.get(f.leader.toLowerCase());
      if (!leader) return;
      const leaderPos = Cartesian3.fromDegrees(
        leader.lon, leader.lat, leader.alt_m || 0,
      );

      // Badge at leader position
      seenBadges.add(f.id);
      const badgeKey = `badge-${f.id}`;
      let badge = this._badges.get(f.id);
      const label = `${f.id} (${f.size})\n${f.type.toUpperCase()}`;
      if (badge) {
        (badge.position as any).setValue(leaderPos);
        badge.label!.text = new ConstantProperty(label);
      } else {
        badge = this.source.entities.add({
          name: badgeKey,
          position: leaderPos,
          label: {
            text: label,
            font: '11px Consolas, monospace',
            fillColor: color,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            style: LabelStyle.FILL_AND_OUTLINE,
            horizontalOrigin: HorizontalOrigin.LEFT,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian3(12, -12, 0) as any,
            showBackground: true,
            backgroundColor: Color.BLACK.withAlpha(0.6),
            backgroundPadding: new Cartesian3(4, 2, 0) as any,
          },
        });
        this._badges.set(f.id, badge);
      }

      // Lines from leader to each follower
      for (const follower of f.followers) {
        const fac = byCallsign.get(follower) ||
                    byCallsign.get(follower.toLowerCase());
        if (!fac) continue;
        const fpos = Cartesian3.fromDegrees(
          fac.lon, fac.lat, fac.alt_m || 0,
        );
        const key = `${f.id}|${follower}`;
        seenLines.add(key);
        const existing = this._lines.get(key);
        if (existing) {
          existing.polyline!.positions =
            new ConstantProperty([leaderPos, fpos]);
          existing.polyline!.material =
            new PolylineDashMaterialProperty({
              color, dashLength: 12,
            }) as any;
        } else {
          const line = this.source.entities.add({
            name: key,
            polyline: {
              positions: [leaderPos, fpos],
              width: 2,
              material: new PolylineDashMaterialProperty({
                color, dashLength: 12,
              }),
            },
          });
          this._lines.set(key, line);
        }
      }
    });

    // Remove lines for formations that no longer exist
    for (const [key, ent] of this._lines) {
      if (!seenLines.has(key)) {
        this.source.entities.remove(ent);
        this._lines.delete(key);
      }
    }
  }

  private _rebuildBadges(): void {
    // Drop any badges for formations no longer present
    const ids = new Set(this._formations.map(f => f.id));
    for (const [id, ent] of this._badges) {
      if (!ids.has(id)) {
        this.source.entities.remove(ent);
        this._badges.delete(id);
      }
    }
    // Lines likewise — the next update() will rebuild
    for (const [key, ent] of this._lines) {
      const fid = key.split('|')[0];
      if (!ids.has(fid)) {
        this.source.entities.remove(ent);
        this._lines.delete(key);
      }
    }
  }

  clear(): void {
    this.source.entities.removeAll();
    this._lines.clear();
    this._badges.clear();
    this._formations = [];
  }
}
