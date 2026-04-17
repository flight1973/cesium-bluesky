/**
 * Layer-opacity service.
 *
 * Single source of truth for per-layer alpha
 * multipliers.  Each layer key is a stable string
 * (e.g., ``'TFR'``, ``'CLASS_B'``, ``'PIREP'``,
 * ``'PROCEDURE'``, ``'SIGMET'``, ``'AIRMET'``,
 * ``'G-AIRMET'``); values are 0..1.
 *
 * Persisted to ``localStorage`` under
 * ``cesium-bluesky.opacity`` so user choices
 * survive reloads.  Subscribers are notified when
 * any layer changes.
 */

const STORAGE_KEY = 'cesium-bluesky.opacity';

export type OpacityChangeListener = (
  key: string, alpha: number,
) => void;

class OpacityService {
  private _values: Record<string, number> = {};
  private _listeners: OpacityChangeListener[] = [];

  constructor() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) this._values = JSON.parse(raw);
    } catch {
      // Corrupt entry — start fresh.
      this._values = {};
    }
  }

  /** Current alpha (default 1.0 if unset). */
  get(key: string): number {
    const v = this._values[key];
    return v === undefined ? 1.0 : v;
  }

  /** Update + persist + notify subscribers. */
  set(key: string, alpha: number): void {
    const a = Math.max(0, Math.min(1, alpha));
    if (this._values[key] === a) return;
    this._values[key] = a;
    try {
      window.localStorage.setItem(
        STORAGE_KEY, JSON.stringify(this._values),
      );
    } catch {
      // localStorage full or disabled — proceed.
    }
    for (const l of this._listeners) l(key, a);
  }

  onChange(l: OpacityChangeListener): () => void {
    this._listeners.push(l);
    return () => {
      const i = this._listeners.indexOf(l);
      if (i >= 0) this._listeners.splice(i, 1);
    };
  }

  /** Snapshot of all current values (read-only copy). */
  all(): Record<string, number> {
    return { ...this._values };
  }
}

export const opacity = new OpacityService();
