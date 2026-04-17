/**
 * UI mode presets — persona-aware default layouts.
 *
 * Each mode controls which layers are on, which
 * toolbar tab is active, and which panels are
 * visible.  The full feature set stays accessible
 * from every mode via the toolbar — modes only
 * change *defaults*, not capabilities.
 *
 * Persisted to ``localStorage`` so the user's
 * choice survives reloads.
 */

export type ModeId =
  | 'controller'
  | 'cockpit'
  | 'ops'
  | 'observer';

export interface ModePreset {
  id: ModeId;
  label: string;
  description: string;
  defaultTab: string;
  /** Layers that start ON when entering this mode. */
  layersOn: string[];
  /** Panels that start visible. */
  panelsVisible: string[];
  /** Panels that start hidden (override any prior state). */
  panelsHidden: string[];
  /** Whether the traffic-list sidebar is shown. */
  trafficListVisible: boolean;
  /** Whether the console is expanded. */
  consoleExpanded: boolean;
}

export const MODE_PRESETS: Record<ModeId, ModePreset> = {
  controller: {
    id: 'controller',
    label: 'Controller',
    description: 'ATC — traffic separation, sector ownership, conflicts, comms',
    defaultTab: 'sim',
    layersOn: [
      'trails', 'routes', 'labels', 'leaders', 'pz',
      'airports',
      'metars', 'sigmets', 'radar',
      'tfrs', 'sua-p', 'sua-r',
      'class-b', 'class-c', 'class-d',
      'class-e2', 'class-e4',
    ],
    panelsVisible: [],
    panelsHidden: ['weather-panel', 'airport-panel', 'fms-panel'],
    trafficListVisible: true,
    consoleExpanded: true,
  },

  cockpit: {
    id: 'cockpit',
    label: 'Cockpit',
    description: 'Pilot / flight planning — routes, weather briefing, procedures',
    defaultTab: 'wx',
    layersOn: [
      'labels', 'routes', 'airports', 'waypoints',
      'metars', 'pireps', 'sigmets', 'gairmets',
      'class-b', 'class-c', 'class-d', 'class-e2',
      'chart-sectional',
    ],
    panelsVisible: ['weather-panel'],
    panelsHidden: ['fms-panel'],
    trafficListVisible: false,
    consoleExpanded: false,
  },

  ops: {
    id: 'ops',
    label: 'Ops',
    description: 'Dispatcher / flow control — fleet, schedule, IROPS',
    defaultTab: 'sim',
    layersOn: [
      'labels', 'routes', 'airports',
      'metars', 'wx-wwa', 'wx-spc-outlook',
      'tfrs',
      'class-b', 'class-c', 'class-d',
    ],
    panelsVisible: [],
    panelsHidden: ['weather-panel', 'airport-panel', 'fms-panel'],
    trafficListVisible: true,
    consoleExpanded: true,
  },

  observer: {
    id: 'observer',
    label: 'Observer',
    description: 'Planespotter / public demo — clean live view',
    defaultTab: 'layers',
    layersOn: [
      'labels', 'trails', 'airports',
      'radar', 'satellite',
    ],
    panelsVisible: [],
    panelsHidden: [
      'weather-panel', 'airport-panel',
      'fms-panel', 'areas-panel', 'wind-point-panel',
    ],
    trafficListVisible: false,
    consoleExpanded: false,
  },
};

const STORAGE_KEY = 'cesium-bluesky.mode';

export function getSavedMode(): ModeId {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw && raw in MODE_PRESETS) return raw as ModeId;
  } catch { /* ignore */ }
  return 'controller';  // default
}

export function saveMode(id: ModeId): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch { /* ignore */ }
}


// ─── Custom layout persistence ──────────────────────
// Beyond the 4 presets, users can customize exactly
// which toolbar tabs, layer chips, and panels are
// visible in their layout.  Stored separately so
// switching to a preset doesn't wipe customizations.

const CUSTOM_KEY = 'cesium-bluesky.custom-layout';

export interface CustomLayout {
  /** Toolbar tabs to show (others hidden). */
  visibleTabs: string[];
  /** Layer chip IDs to show in the toolbar. */
  visibleLayerChips: string[];
  /** Panels the user has enabled. */
  enabledPanels: string[];
}

const DEFAULT_CUSTOM: CustomLayout = {
  visibleTabs: [
    'sim', 'layers', 'view', 'areas',
    'wind', 'cameras', 'wx', 'notam',
  ],
  visibleLayerChips: [], // empty = show all
  enabledPanels: [],     // empty = show all
};

export function getCustomLayout(): CustomLayout {
  try {
    const raw = window.localStorage.getItem(CUSTOM_KEY);
    if (raw) return { ...DEFAULT_CUSTOM, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return { ...DEFAULT_CUSTOM };
}

export function saveCustomLayout(layout: CustomLayout): void {
  try {
    window.localStorage.setItem(
      CUSTOM_KEY, JSON.stringify(layout),
    );
  } catch { /* ignore */ }
}
