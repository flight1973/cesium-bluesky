/**
 * Global unit-system preference and conversion helpers.
 *
 * One source of truth for whether the UI shows speeds as
 * knots (aviation), m/s (SI), or mph (imperial).  The
 * preference is persisted to localStorage and broadcast
 * via a DOM custom event (`units-changed`) so any
 * component can reactively re-render.
 *
 * Direction is always degrees true, met convention (the
 * direction wind is *from*).  Altitude display follows
 * the aviation/imperial convention (ft and FL) unless the
 * user selects SI, which switches to meters.
 */
import type { UnitSystem } from '../types';

const STORAGE_KEY = 'bluesky.unitSystem';
const EVENT_NAME = 'units-changed';

const KT_PER_MS = 1.0 / 0.514444;
const MPH_PER_MS = 2.23693629;

let _current: UnitSystem = (
  (localStorage.getItem(STORAGE_KEY) as UnitSystem)
  || 'aviation'
);

export function getUnits(): UnitSystem {
  return _current;
}

export function setUnits(u: UnitSystem): void {
  if (u === _current) return;
  _current = u;
  localStorage.setItem(STORAGE_KEY, u);
  document.dispatchEvent(
    new CustomEvent(EVENT_NAME, {
      detail: { units: u },
    }),
  );
}

/** Subscribe to unit-system changes.  Returns an unsub. */
export function onUnitsChange(
  cb: (u: UnitSystem) => void,
): () => void {
  const listener = (e: Event) =>
    cb((e as CustomEvent).detail.units);
  document.addEventListener(EVENT_NAME, listener);
  return () => document.removeEventListener(
    EVENT_NAME, listener,
  );
}

// ── Speed conversions ────────────────────────────────

export function msToUser(
  ms: number,
  u: UnitSystem = _current,
): number {
  if (u === 'si') return ms;
  if (u === 'imperial') return ms * MPH_PER_MS;
  return ms * KT_PER_MS;
}

export function userToMs(
  value: number,
  u: UnitSystem = _current,
): number {
  if (u === 'si') return value;
  if (u === 'imperial') return value / MPH_PER_MS;
  return value / KT_PER_MS;
}

export function speedUnitLabel(
  u: UnitSystem = _current,
): string {
  return {
    aviation: 'kt',
    si: 'm/s',
    imperial: 'mph',
  }[u];
}

/**
 * Convert a (north m/s, east m/s) wind vector into a met-
 * convention "from" direction (deg) and speed in user
 * units.  Matches the backend helper exactly — BlueSky
 * stores wind as a "toward" vector; we rotate 180° to get
 * "from" for display.
 */
export function windVectorToFrom(
  north_ms: number,
  east_ms: number,
  u: UnitSystem = _current,
): { direction_deg: number; speed: number; label: string } {
  const spdMs = Math.hypot(north_ms, east_ms);
  if (spdMs < 1e-6) {
    return {
      direction_deg: 0,
      speed: 0,
      label: speedUnitLabel(u),
    };
  }
  const dirFrom = (
    (Math.atan2(east_ms, north_ms) * 180) / Math.PI + 180
    + 360
  ) % 360;
  return {
    direction_deg: dirFrom,
    speed: msToUser(spdMs, u),
    label: speedUnitLabel(u),
  };
}

/** Format as "270°/28 kt" or "CALM" under threshold. */
export function formatWind(
  north_ms: number,
  east_ms: number,
  u: UnitSystem = _current,
): string {
  const { direction_deg, speed, label } = windVectorToFrom(
    north_ms, east_ms, u,
  );
  // Use m/s threshold so the "CALM" boundary is unit-
  // independent; 0.5 m/s ~ 1 kt ~ 1.1 mph.
  if (Math.hypot(north_ms, east_ms) < 0.5) {
    return 'CALM';
  }
  return `${Math.round(direction_deg)
    .toString().padStart(3, '0')}°/${
    Math.round(speed)} ${label}`;
}
