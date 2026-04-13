/**
 * Trail entity manager — accumulates trail line segments
 * from the TRAILS WebSocket topic as cyan polylines in 3D.
 *
 * Since BlueSky trail data only contains lat/lon (no alt),
 * we use a position lookup from the latest ACDATA to stamp
 * altitude onto each trail endpoint, so trails render at
 * the actual flight level in 3D space.
 */
import {
  Viewer,
  Cartesian3,
  Color,
  CustomDataSource,
} from 'cesium';
import type { TrailData, AcData } from '../../types';

const TRAIL_COLOR = Color.CYAN.withAlpha(0.7);
const MAX_SEGMENTS = 50000;

export class TrailManager {
  private source: CustomDataSource;
  private segCount = 0;
  private _visible = true;
  private _altScale = 1.0;

  // Lookup: lat/lon → altitude from latest ACDATA.
  private _posAlt = new Map<string, number>();

  constructor(private viewer: Viewer) {
    this.source = new CustomDataSource('trails');
    viewer.dataSources.add(this.source);
  }

  /** Set altitude exaggeration to match aircraft. */
  setAltScale(scale: number): void {
    this._altScale = scale;
  }

  /**
   * Update the position→altitude lookup from ACDATA.
   * Call this every ACDATA frame before addSegments.
   */
  updateAltLookup(data: AcData): void {
    this._posAlt.clear();
    for (let i = 0; i < data.id.length; i++) {
      // Key: lat/lon rounded to match trail precision.
      const key = this._posKey(
        data.lat[i], data.lon[i],
      );
      this._posAlt.set(key, data.alt[i]);
    }
  }

  /** Append new trail segments from a TRAILS frame. */
  addSegments(data: TrailData): void {
    if (!this._visible) return;
    const s = this._altScale;

    for (let i = 0; i < data.traillat0.length; i++) {
      if (this.segCount >= MAX_SEGMENTS) {
        const ents = this.source.entities.values;
        if (ents.length > 0) {
          this.source.entities.remove(ents[0]);
          this.segCount--;
        }
      }

      // Look up altitude for each endpoint.
      const alt0 = this._findAlt(
        data.traillat0[i], data.traillon0[i],
      ) * s;
      const alt1 = this._findAlt(
        data.traillat1[i], data.traillon1[i],
      ) * s;

      this.source.entities.add({
        polyline: {
          positions:
            Cartesian3.fromDegreesArrayHeights([
              data.traillon0[i], data.traillat0[i], alt0,
              data.traillon1[i], data.traillat1[i], alt1,
            ]),
          width: 1,
          material: TRAIL_COLOR,
        },
      });
      this.segCount++;
    }
  }

  /** Toggle trail visibility. */
  setVisible(visible: boolean): void {
    this._visible = visible;
    this.source.show = visible;
  }

  get visible(): boolean {
    return this._visible;
  }

  /** Remove all trail segments. */
  clear(): void {
    this.source.entities.removeAll();
    this.segCount = 0;
  }

  /** Build a lookup key from lat/lon. */
  private _posKey(lat: number, lon: number): string {
    return `${lat.toFixed(4)},${lon.toFixed(4)}`;
  }

  /**
   * Find altitude for a lat/lon from the lookup.
   * Falls back to 0 if no match found.
   */
  private _findAlt(lat: number, lon: number): number {
    // Try exact key first.
    const key = this._posKey(lat, lon);
    const alt = this._posAlt.get(key);
    if (alt !== undefined) return alt;

    // Fallback: find closest aircraft within tolerance.
    let best = 0;
    let bestDist = Infinity;
    for (const [k, a] of this._posAlt) {
      const [la, lo] = k.split(',').map(Number);
      const d = (la - lat) ** 2 + (lo - lon) ** 2;
      if (d < bestDist) {
        bestDist = d;
        best = a;
      }
    }
    // Only use if reasonably close (< ~1 degree).
    return bestDist < 1 ? best : 0;
  }
}
