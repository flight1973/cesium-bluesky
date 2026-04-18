/**
 * Main entry point — wires Cesium viewer, WebSocket, and
 * all BlueSky UI components together.
 */
import {
  Cartographic,
  Cartesian3,
  Ellipsoid,
  Matrix4,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  SceneMode,
  HeadingPitchRange,
  HeadingPitchRoll,
  Transforms,
  Math as CesiumMath,
  defined,
  GridImageryProvider,
  ImageryLayer,
} from 'cesium';
import {
  createViewer,
  applyIonConfig,
  setImagery,
  setTerrain,
  setIonToken,
  isIonEnabled,
  ALL_IMAGERY,
  ALL_TERRAIN,
} from './cesium/viewer';
import { AircraftManager } from './cesium/entities/aircraft';
import { TrailManager } from './cesium/entities/trails';
import { RouteManager } from './cesium/entities/routes';
import { NavdataManager } from './cesium/entities/navdata';
import { AreaManager } from './cesium/entities/areas';
import { WindBarbManager } from './cesium/entities/wind-barbs';
import { WindFieldManager } from './cesium/entities/wind-field';
import { MetarManager } from './cesium/entities/metars';
import { SigmetManager } from './cesium/entities/sigmets';
import { WeatherImageryManager } from './cesium/entities/weather-imagery';
import { AirspaceManager } from './cesium/entities/airspace';
import { ChartOverlayManager } from './cesium/entities/chart-overlays';
import { ObservedTrafficManager } from './cesium/entities/observed-traffic';
import { PirepManager } from './cesium/entities/pireps';
import { ProcedureManager } from './cesium/entities/procedures';
import { SimWebSocket } from './services/websocket';
import type { AcData, SimInfo, TrailData } from './types';

// Import Lit components (self-registering).
import './ui/toolbar';
import './ui/status-bar';
import './ui/traffic-list';
import './ui/console';
import './ui/aircraft-panel';
import './ui/fms-panel';
import './ui/area-tool';
import './ui/areas-panel';
import './ui/wind-point-panel';
import './ui/weather-panel';
import './ui/airport-panel';
import './ui/opacity-panel';
import './ui/conflicts-panel';
import './ui/scenario-editor';
import './ui/camera-controls';
import './ui/scale-bar';
import './ui/compass-ring';
import './ui/layer-panel';
import './ui/measure-tool';
import './ui/formations-panel';
import { FormationManager as FormationMapManager } from './cesium/entities/formations';
import './ui/settings-panel';
import './ui/weather-time-strip';
import './ui/replay-panel';

import type { BlueSkyToolbar } from './ui/toolbar';
import type { BlueSkyStatusBar } from './ui/status-bar';
import type { BlueSkyTrafficList } from './ui/traffic-list';
import type { BlueSkyConsole } from './ui/console';
import type { AircraftPanel } from './ui/aircraft-panel';
import type { FmsPanel } from './ui/fms-panel';
import type { AreaTool } from './ui/area-tool';
import type { AreasPanel } from './ui/areas-panel';
import type { WindPointPanel } from './ui/wind-point-panel';
import type { WeatherPanel } from './ui/weather-panel';
import type { AirportPanel } from './ui/airport-panel';
import type { OpacityPanel } from './ui/opacity-panel';
import { opacity } from './services/opacity';
import {
  type ModeId,
  MODE_PRESETS,
  getSavedMode,
  saveMode,
} from './services/modes';
import type { ScenarioEditor } from './ui/scenario-editor';
import type { CameraControls } from './ui/camera-controls';
import type { ScaleBar } from './ui/scale-bar';
import type { WeatherTimeStrip } from './ui/weather-time-strip';
import type { CompassRing } from './ui/compass-ring';
import type { LayerPanel } from './ui/layer-panel';
import type { MeasureTool } from './ui/measure-tool';

// ── Initialize Cesium viewer ────────────────────────
const viewer = createViewer('cesium-container');
viewer.scene.mode = SceneMode.SCENE2D;
const aircraftMgr = new AircraftManager(viewer);
const trailMgr = new TrailManager(viewer);
const routeMgr = new RouteManager(viewer);
const navMgr = new NavdataManager(viewer);
const areaMgr = new AreaManager(viewer);
areaMgr.startPolling(2000);
const windBarbMgr = new WindBarbManager(viewer);
const windFieldMgr = new WindFieldManager(viewer);
const metarMgr = new MetarManager(viewer);
const sigmetMgr = new SigmetManager(viewer);
const wxImageryMgr = new WeatherImageryManager(viewer);
const airspaceMgr = new AirspaceManager(viewer);
const procedureMgr = new ProcedureManager(viewer);
const pirepMgr = new PirepManager(viewer);
const formationMgr = new FormationMapManager(viewer);
const observedMgr = new ObservedTrafficManager(viewer, 'live');
const replayMgr = new ObservedTrafficManager(viewer, 'replay');
replayMgr.setLerpMode(true, 500);
const chartMgr = new ChartOverlayManager(viewer);

// ── Connect WebSocket ───────────────────────────────
const wsUrl = `ws://${window.location.host}/ws/sim`;
const ws = new SimWebSocket(wsUrl);

// ── Get UI component references ─────────────────────
const toolbar = document.querySelector(
  'bluesky-toolbar',
) as BlueSkyToolbar;
const statusBar = document.querySelector(
  'bluesky-statusbar',
) as BlueSkyStatusBar;
const trafficList = document.querySelector(
  'bluesky-traffic-list',
) as BlueSkyTrafficList;
const cmdConsole = document.querySelector(
  'bluesky-console',
) as BlueSkyConsole;
const acPanel = document.querySelector(
  'aircraft-panel',
) as AircraftPanel;
const fmsPanel = document.querySelector(
  'fms-panel',
) as FmsPanel;
const areaTool = document.querySelector(
  'area-tool',
) as AreaTool;
const areasPanel = document.querySelector(
  'areas-panel',
) as AreasPanel;
const windPanel = document.querySelector(
  'wind-point-panel',
) as WindPointPanel;
const weatherPanel = document.querySelector(
  'weather-panel',
) as WeatherPanel;
const airportPanel = document.querySelector(
  'airport-panel',
) as AirportPanel;
const opacityPanel = document.querySelector(
  'opacity-panel',
) as OpacityPanel;
const scenarioEditor = document.querySelector(
  'scenario-editor',
) as ScenarioEditor;
const camCtrl = document.querySelector(
  'camera-controls',
) as CameraControls;
camCtrl.setViewer(viewer);
const scaleBar = document.querySelector(
  'scale-bar',
) as ScaleBar;
scaleBar.setViewer(viewer);
const compassRing = document.querySelector(
  'compass-ring',
) as CompassRing;
compassRing.setViewer(viewer);
const measureTool = document.querySelector(
  'measure-tool',
) as MeasureTool;
measureTool.setViewer(viewer);
const wxTimeStrip = document.querySelector(
  'weather-time-strip',
) as WeatherTimeStrip;

const layerPanel = document.querySelector(
  'layer-panel',
) as LayerPanel;

// ── Wire ACDATA → entities + traffic list ───────────
const conflictsPanel = document.querySelector(
  'conflicts-panel',
) as any;

ws.on('ACDATA', (data: AcData) => {
  aircraftMgr.update(data);
  trafficList.updateFromAcData(data);
  trailMgr.updateAltLookup(data);
  toolbar.setAircraftIds(data.id);
  statusBar.updateConflicts(
    data.nconf_cur,
    data.nconf_tot,
    data.nlos_cur,
    data.nlos_tot,
  );
  // Feed the conflicts panel with per-pair detail
  // (skip when replay is active — replay provides its own).
  if (conflictsPanel && !replayController.state.active) {
    conflictsPanel.update_conflicts(
      (data as any).confpairs || [],
      (data as any).lospairs || [],
      (data as any).conf_tcpa || [],
      (data as any).conf_dcpa || [],
    );
  }
});

// ── Wire SIMINFO → status bar + toolbar ─────────────
ws.on('SIMINFO', (data: SimInfo) => {
  statusBar.updateFromSimInfo(data);
  toolbar.updateState(
    data.state_name, data.dtmult, data.scenname,
  );
});

// ── Wire TRAILS → trail manager ─────────────────────
ws.on('TRAILS', (data: TrailData) => {
  trailMgr.addSegments(data);
});

// ── Wire CMDLOG → console server tab ────────────────
ws.on('CMDLOG', (entry: any) => {
  cmdConsole.addLogEntry(entry);
});


// ── Client-side cleanup for RESET / IC ─────────────
async function clearSimState(): Promise<void> {
  trailMgr.clear();
  routeMgr.clear();
  acPanel.hide();
  fmsPanel.close();
  aircraftMgr.clearAll();

  // Clear the rendered area boundaries immediately.
  areaMgr.clear();

  // Also explicitly delete shapes on the backend since
  // bs.sim.reset() can race with scenario replay.
  try {
    const res = await fetch('/api/areas');
    if (res.ok) {
      const data = await res.json();
      ws.sendCommand('AREA OFF');
      for (const name of Object.keys(
        data.shapes || {},
      )) {
        ws.sendCommand(`DEL ${name}`);
      }
    }
  } catch {
    // Non-fatal.
  }

  // Poll a few times to catch the post-RESET state.
  for (const delay of [200, 800, 2000]) {
    setTimeout(() => areaMgr.refresh(), delay);
  }
}

// ── Command handler (shared by console + panel) ─────
function sendCommand(cmd: string): void {
  const trimmed = cmd.trim();
  const upper = trimmed.toUpperCase();

  // PAN is a per-client camera command.  Handle it
  // locally in this browser instead of sending to the
  // sim — otherwise every connected browser would fly
  // to the same target.
  if (upper.startsWith('PAN ')) {
    cmdConsole.echo(cmd);
    handlePan(trimmed.slice(4).trim());
    return;
  }

  ws.sendCommand(cmd);
  cmdConsole.echo(cmd);

  // Clear frontend state on RESET or IC commands.
  if (
    upper === 'RESET'
    || upper.startsWith('IC ')
  ) {
    clearSimState();
  }
}

/** Resolve a PAN identifier via REST, then fly to it
 *  locally.  No WebSocket broadcast, no side effects
 *  on other clients. */
async function handlePan(identifier: string): Promise<void> {
  if (!identifier) {
    cmdConsole.echo('PAN: missing identifier');
    return;
  }
  try {
    const res = await fetch(
      `/api/pan/resolve?id=${encodeURIComponent(identifier)}`,
    );
    if (!res.ok) {
      cmdConsole.echo(
        `PAN: could not resolve '${identifier}'`,
      );
      return;
    }
    const data = await res.json();
    const altM = typeof data.alt_m_view === 'number'
      ? data.alt_m_view
      : 100_000;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(
        data.lon, data.lat, altM,
      ),
      orientation: {
        heading: 0,
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
      duration: 1.0,
    });
    cmdConsole.echo(
      `PAN → ${data.identifier} (${data.kind})`,
    );
  } catch (err) {
    cmdConsole.echo(`PAN: ${err}`);
  }
}
cmdConsole.setCommandHandler(sendCommand);
acPanel.setCommandHandler(sendCommand);
fmsPanel.setCommandHandler(sendCommand);
areaTool.setCommandHandler(sendCommand);
areasPanel.setCommandHandler(sendCommand);
scenarioEditor.setCommandHandler(sendCommand);
areaTool.setViewer(viewer);
cmdConsole.loadCommandBriefs();
cmdConsole.loadInitialLog();

// ── Echo events (console-only, no sim command) ──────
document.addEventListener(
  'echo',
  ((e: CustomEvent) => {
    cmdConsole.echo(e.detail.text);
  }) as EventListener,
);

// ── Area state changes → refresh display ───────────
document.addEventListener(
  'area-changed',
  (() => {
    // Poll a couple times to catch backend state.
    for (const d of [200, 800]) {
      setTimeout(() => areaMgr.refresh(), d);
    }
  }) as EventListener,
);

// ── RESET button → clear all client state ───────────
document.addEventListener(
  'sim-reset',
  (() => {
    cmdConsole.echo('RESET');
    clearSimState();
  }) as EventListener,
);

// ── Aircraft selection logic ────────────────────────
function selectAircraft(
  acid: string | null,
  flyTo = false,
): void {
  aircraftMgr.select(acid);
  if (acid) {
    // Selecting an aircraft clears any polygon
    // highlight — only one thing is selected at a time.
    airspaceMgr.setSelected(null);
    sigmetMgr.setSelected(null);
    windPanel.hide();
    weatherPanel.hide();
    routeMgr.showRoute(acid);
    acPanel.showAircraft(acid);
    if (flyTo) {
      const entity = viewer.entities.getById(
        `ac-${acid}`,
      );
      if (entity) {
        viewer.flyTo(entity, {
          offset: new HeadingPitchRange(
            0,
            CesiumMath.toRadians(-90),  // straight down
            100000,
          ),
          duration: 1.0,
        });
      }
    }
  } else {
    routeMgr.clear();
    acPanel.hide();
  }
}

// Traffic list click → select + fly to.
document.addEventListener(
  'aircraft-select',
  ((e: CustomEvent) => {
    selectAircraft(e.detail.acid, true);
  }) as EventListener,
);

// Panel close → deselect.
document.addEventListener(
  'panel-close',
  (() => {
    aircraftMgr.select(null);
    routeMgr.clear();
  }) as EventListener,
);

// Conflict panel click → select first aircraft of pair.
document.addEventListener(
  'conflict-select',
  ((e: Event) => {
    const ce = e as CustomEvent<{ ac1: string; ac2: string }>;
    selectAircraft(ce.detail.ac1, true);
  }) as EventListener,
);

// Weather / advisory panel close → clear polygon halo.
document.addEventListener(
  'weather-panel-close',
  (() => {
    sigmetMgr.setSelected(null);
    airspaceMgr.setSelected(null);
  }) as EventListener,
);

// Airport panel → toggle a procedure polyline on globe.
// On enable: fetch the compiled geometry, render.
// On disable: just hide locally.
document.addEventListener(
  'toggle-procedure',
  ((e: Event) => {
    const ce = e as CustomEvent<
      { id: string; on: boolean }
    >;
    const { id, on } = ce.detail;
    void _handleToggleProcedure(id, on);
  }) as EventListener,
);

async function _handleToggleProcedure(
  id: string, on: boolean,
): Promise<void> {
  if (!on) {
    procedureMgr.hide(id);
    airportPanel.markInactive(id);
    return;
  }
  try {
    const res = await fetch(
      `/api/navdata/procedures/${id}`,
    );
    if (!res.ok) {
      cmdConsole.echo(
        `[procedure] ${id}: HTTP ${res.status}`,
      );
      return;
    }
    const geom = await res.json();
    if (!geom.compiled) {
      cmdConsole.echo(
        `[procedure] ${id}: not compiled — `
        + `${geom.raw?.legs?.length ?? 0} raw legs.  `
        + `See project_procedure_compile_gaps.md.`,
      );
      return;
    }
    procedureMgr.show(geom);
    airportPanel.markActive(id);
  } catch (err) {
    cmdConsole.echo(`[procedure] ${id}: ${err}`);
  }
}

// ── FMS panel open event ────────────────────────────
document.addEventListener(
  'open-fms',
  ((e: CustomEvent) => {
    fmsPanel.open(e.detail.acid);
  }) as EventListener,
);

// ── Areas panel open event ──────────────────────────
document.addEventListener(
  'open-areas-panel',
  (() => {
    areasPanel.open();
  }) as EventListener,
);

// ── Scenario editor open event ──────────────────────
document.addEventListener(
  'open-scenario-editor',
  (() => {
    scenarioEditor.open();
  }) as EventListener,
);

// ── Aircraft follow camera ───────────────────────────
// Preset-based: each mode is a position offset in the
// aircraft's local ENU frame plus an orientation offset
// relative to the aircraft track.  New modes only need a
// new preset entry; the update loop stays the same.
//
// Forward = along aircraft track (positive = ahead).
// Right   = starboard side (positive = right of track).
// Up      = vertical (positive = above).
// yawDeg  = camera heading offset from aircraft track
//           (0 = forward, +90 = right, -90 = left).
// pitchDeg = camera pitch (negative = looking down).
type CamMode = 'chase' | 'pilot' | 'starboard' | 'port';

interface CamPreset {
  forward: number;  // meters
  right: number;    // meters
  up: number;       // meters
  yawDeg: number;
  pitchDeg: number;
  label: string;
}

const CAM_PRESETS: Record<CamMode, CamPreset> = {
  chase: {
    forward: -150, right: 0, up: 25,
    yawDeg: 0, pitchDeg: -5,
    label: 'Chase (behind & above)',
  },
  pilot: {
    forward: 3, right: 0, up: 2,
    yawDeg: 0, pitchDeg: -2,
    label: 'Pilot (cockpit forward)',
  },
  starboard: {
    forward: 0, right: 2, up: 2,
    yawDeg: 90, pitchDeg: 0,
    label: 'Starboard (window, right)',
  },
  port: {
    forward: 0, right: -2, up: 2,
    yawDeg: -90, pitchDeg: 0,
    label: 'Port (window, left)',
  },
};

let camTrackAcid: string | null = null;
let camTrackMode: CamMode = 'chase';

function updateTrackingCamera(): void {
  if (!camTrackAcid) return;
  const state = aircraftMgr.getAircraftState(
    camTrackAcid,
  );
  if (!state) {
    setCameraTracking(null, camTrackMode);
    return;
  }

  const preset = CAM_PRESETS[camTrackMode];
  const scale = aircraftMgr.altScale;
  const altM = state.alt * scale;
  const headingRad = CesiumMath.toRadians(state.trk);

  // Convert (forward, right) into (east, north) using
  // the aircraft's track as the forward axis.
  const sinH = Math.sin(headingRad);
  const cosH = Math.cos(headingRad);
  // Forward unit vector in ENU: (sin H, cos H).
  // Right unit vector (90° clockwise of forward): (cos H, -sin H).
  const east =
    preset.forward * sinH + preset.right * cosH;
  const north =
    preset.forward * cosH + preset.right * (-sinH);

  const aircraftPos = Cartesian3.fromDegrees(
    state.lon, state.lat, altM,
  );
  const enu = Transforms.eastNorthUpToFixedFrame(
    aircraftPos,
  );
  const localOffset = new Cartesian3(east, north, preset.up);
  const camPos = new Cartesian3();
  Matrix4.multiplyByPoint(enu, localOffset, camPos);

  const camHeadingRad =
    headingRad + CesiumMath.toRadians(preset.yawDeg);

  viewer.camera.setView({
    destination: camPos,
    orientation: new HeadingPitchRoll(
      camHeadingRad,
      CesiumMath.toRadians(preset.pitchDeg),
      0,
    ),
  });
}

/** Set or clear the tracking camera and notify UI. */
function setCameraTracking(
  acid: string | null,
  mode: CamMode,
): void {
  camTrackAcid = acid;
  camTrackMode = mode;
  document.dispatchEvent(
    new CustomEvent('camera-state', {
      detail: { acid, mode },
      bubbles: true,
      composed: true,
    }),
  );
}

// Update follow camera every render frame.
viewer.scene.preRender.addEventListener(
  updateTrackingCamera,
);

document.addEventListener(
  'cam-view',
  ((e: CustomEvent) => {
    const acid = e.detail.acid;
    const mode: CamMode = e.detail.mode || 'chase';
    if (camTrackAcid === acid && camTrackMode === mode) {
      setCameraTracking(null, mode);
      cmdConsole.echo(
        `${mode} view: off (${acid})`,
      );
    } else {
      setCameraTracking(acid, mode);
      cmdConsole.echo(
        `${mode} view: ${acid}`,
      );
    }
  }) as EventListener,
);

// Toolbar CAMERAS tab mirrors tracking state.
document.addEventListener(
  'camera-state',
  ((e: CustomEvent) => {
    toolbar.setCameraState(e.detail.acid, e.detail.mode);
  }) as EventListener,
);

// ── Wind points → barb rendering ────────────────────
let windPickActive = false;

document.addEventListener(
  'wind-points-updated',
  ((e: CustomEvent) => {
    // Render only *user-defined* wind points as barbs.
    // METAR-origin points are imported from the METAR
    // layer as surface winds — they populate the
    // interpolated Field for realism but would crowd
    // the map as barbs (dozens of stations).  Users
    // still see each METAR's wind on the station dot
    // and in the METAR detail panel.
    const all = (e.detail.points || []) as any[];
    const userOnly = all.filter(
      (p: any) => !(
        typeof p.origin === 'string'
        && p.origin.startsWith('metar')
      ),
    );
    const points = userOnly.map((p: any) => ({
      lat: p.lat,
      lon: p.lon,
      altitude_ft: p.altitude_ft,
      direction_deg: p.direction_deg,
      speed_kt: (() => {
        switch (p.units) {
          case 'si': return p.speed / 0.514444;
          case 'imperial': return p.speed / 1.15078;
          default: return p.speed;
        }
      })(),
    }));
    windBarbMgr.update(points);
  }) as EventListener,
);

document.addEventListener(
  'wind-pick-toggle',
  ((e: CustomEvent) => {
    windPickActive = e.detail.active;
    // If user canceled pick mode, no-op; if they
    // activated it, close any open panels so a new
    // click opens the wind editor instead.
    if (windPickActive) {
      windPanel.hide();
    }
  }) as EventListener,
);

// User picked a point from the toolbar dropdown →
// open the detail panel for that point in view mode.
document.addEventListener(
  'wind-open-point',
  ((e: CustomEvent) => {
    selectAircraft(null);
    windPanel.showPoint(e.detail);
  }) as EventListener,
);

// Panel requested a refresh after a SAVE — reload the
// defined points so the barbs on the globe update.
document.addEventListener(
  'wind-refresh-needed',
  () => { toolbar.refreshWindInfo(); },
);

// DELETE from wind panel → call the API, then refresh.
document.addEventListener(
  'wind-delete',
  ((e: Event) => {
    const detail = (e as CustomEvent).detail;
    const body: any = {
      lat: detail.lat,
      lon: detail.lon,
    };
    if (detail.altitude_ft !== null) {
      body.altitude_ft = detail.altitude_ft;
    }
    fetch('/api/wind/points', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(() => {
      setTimeout(() => toolbar.refreshWindInfo(), 300);
    }).catch((err) => {
      alert(`Failed to delete wind point: ${err}`);
    });
  }) as EventListener,
);

// Refresh wind points on sim reset (IC / RESET).
document.addEventListener('sim-reset', () => {
  setTimeout(() => toolbar.refreshWindInfo(), 300);
});

// Initial fetch after page load.
setTimeout(() => toolbar.refreshWindInfo(), 500);

// ── Interpolated wind field ─────────────────────────
// Debounced camera-idle fetcher: after the user stops
// moving the camera, request a wind-field grid
// covering the current view and pass it to the field
// manager.
let windFieldAltFt = 35000;
let windFieldSpacingDeg = 1.0;
let windFieldTimer: number | null = null;

document.addEventListener(
  'wind-field-config',
  ((e: CustomEvent) => {
    windFieldAltFt = e.detail.altitude_ft;
    windFieldSpacingDeg = e.detail.spacing_deg;
    scheduleWindFieldFetch();
  }) as EventListener,
);

function currentViewBounds():
  { latS: number; lonW: number; latN: number; lonE: number }
  | null {
  const rect = viewer.camera.computeViewRectangle();
  if (!rect) return null;
  return {
    latS: CesiumMath.toDegrees(rect.south),
    lonW: CesiumMath.toDegrees(rect.west),
    latN: CesiumMath.toDegrees(rect.north),
    lonE: CesiumMath.toDegrees(rect.east),
  };
}

async function fetchWindField(): Promise<void> {
  if (!windFieldMgr.visible) return;
  const b = currentViewBounds();
  if (!b) return;
  // Guard against rectangles that wrap the antimeridian
  // or cover the whole globe with weird ordering.
  if (b.lonW >= b.lonE || b.latS >= b.latN) return;
  // Clamp to reasonable bounds.
  const latS = Math.max(b.latS, -85);
  const latN = Math.min(b.latN, 85);
  const lonW = Math.max(b.lonW, -180);
  const lonE = Math.min(b.lonE, 180);

  // Auto-widen spacing if the view is huge so we don't
  // hit the backend's 10k-cell cap.
  const span = Math.max(latN - latS, lonE - lonW);
  let spacing = windFieldSpacingDeg;
  while (
    Math.ceil((latN - latS) / spacing + 1)
    * Math.ceil((lonE - lonW) / spacing + 1)
    > 9000
  ) {
    spacing *= 2;
  }

  const url = `/api/wind/grid`
    + `?bounds=${latS},${lonW},${latN},${lonE}`
    + `&altitude_ft=${windFieldAltFt}`
    + `&spacing_deg=${spacing}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    windFieldMgr.update(
      (data.cells || []).map((c: any) => ({
        lat: c.lat,
        lon: c.lon,
        direction_deg: c.direction_deg,
        speed_kt: c.speed_kt,
      })),
      windFieldAltFt,
    );
  } catch {
    // Non-fatal; try again on next camera idle.
  }
}

function scheduleWindFieldFetch(): void {
  if (windFieldTimer !== null) {
    clearTimeout(windFieldTimer);
  }
  windFieldTimer = window.setTimeout(
    () => { windFieldTimer = null; fetchWindField(); },
    350,
  );
}

// Re-fetch whenever the camera stops moving.
viewer.camera.moveEnd.addEventListener(
  scheduleWindFieldFetch,
);

// Re-fetch when defined points change, since that
// changes the interpolated field too.
document.addEventListener('wind-points-updated', () => {
  scheduleWindFieldFetch();
});

// ── METAR fetcher ───────────────────────────────────
let metarTimer: number | null = null;

async function fetchMetars(): Promise<void> {
  if (!metarMgr.visible) return;
  const b = currentViewBounds();
  if (!b) return;
  if (b.lonW >= b.lonE || b.latS >= b.latN) return;
  const latS = Math.max(b.latS, -85);
  const latN = Math.min(b.latN, 85);
  const lonW = Math.max(b.lonW, -180);
  const lonE = Math.min(b.lonE, 180);
  const { getUnits } = await import('./services/units');
  const url = `/api/weather/metars`
    + `?bounds=${latS},${lonW},${latN},${lonE}`
    + `&units=${getUnits()}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    const list = data.metars || [];
    metarMgr.update(list);
    weatherPanel.setMetars(list);
    // If auto-import is on, push surface winds into
    // the sim's wind field.
    if (metarWindImportActive) {
      await syncMetarWindsToField(list);
    }
  } catch {
    // Non-fatal.
  }
}

// ── PIREP fetcher (bbox-driven, same pattern) ──────
let pirepTimer: number | null = null;

async function fetchPireps(): Promise<void> {
  if (!pirepMgr.anyVisible()) return;
  const b = currentViewBounds();
  if (!b) return;
  if (b.lonW >= b.lonE || b.latS >= b.latN) return;
  const latS = Math.max(b.latS, -85);
  const latN = Math.min(b.latN, 85);
  const lonW = Math.max(b.lonW, -180);
  const lonE = Math.min(b.lonE, 180);
  const url = `/api/weather/pireps`
    + `?bounds=${latS},${lonW},${latN},${lonE}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    pirepMgr.update(data.items || []);
  } catch {
    // Non-fatal.
  }
}

function schedulePirepFetch(): void {
  if (pirepTimer !== null) clearTimeout(pirepTimer);
  pirepTimer = window.setTimeout(
    () => { pirepTimer = null; fetchPireps(); },
    400,
  );
}

// ── Replay controller (must be before live traffic) ───
import { replayController } from './services/replay';

replayController.onTrails((trails) => {
  replayMgr.setFullTrails(trails);
});

replayController.onData((data: any) => {
  replayMgr.update(data.items || []);
  replayMgr.updateConflicts(
    data.confpairs || [],
    data.lospairs || [],
  );
  replayMgr.updateAdvisories(data.advisories || {});
  formationMgr.update(data.items || []);
  if (conflictsPanel) {
    conflictsPanel.update_conflicts(
      data.confpairs || [],
      data.lospairs || [],
      data.conf_tcpa || [],
      data.conf_dcpa || [],
    );
  }
  statusBar.updateConflicts(
    data.nconf_cur || 0,
    data.nconf_cur || 0,
    data.nlos_cur || 0,
    data.nlos_cur || 0,
  );
});

function _epochToSimTime(epoch: number): string {
  const d = new Date(epoch * 1000);
  const day = d.getUTCDate();
  const mon = d.getUTCMonth() + 1;
  const yr = d.getUTCFullYear();
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');
  return `TIME ${day} ${mon} ${yr} ${hh}:${mm}:${ss}`;
}

let _lastReplayPlaying = false;
let _lastReplaySpeed = 1;
let _lastReplayEpochSync = 0;

replayController.onChange((state) => {
  if (state.active) {
    if (!replayMgr.visible) {
      replayMgr.setVisible(true);
      layerPanel.setLayerState('replay-traffic', true);
    }

    // Sync sim clock on significant time jumps (>30s).
    const drift = Math.abs(state.currentEpoch - _lastReplayEpochSync);
    if (drift > 30 || _lastReplayEpochSync === 0) {
      ws.sendCommand(_epochToSimTime(state.currentEpoch));
      _lastReplayEpochSync = state.currentEpoch;
    }

    // Sync play/pause.
    if (state.playing && !_lastReplayPlaying) {
      ws.sendCommand('OP');
      ws.sendCommand(`DTMULT ${state.speed}`);
    } else if (!state.playing && _lastReplayPlaying) {
      ws.sendCommand('HOLD');
    }
    _lastReplayPlaying = state.playing;

    // Sync speed.
    if (state.speed !== _lastReplaySpeed) {
      replayMgr.setLerpSpeed(state.speed);
      if (state.playing) {
        ws.sendCommand(`DTMULT ${state.speed}`);
      }
    }
    _lastReplaySpeed = state.speed;

  } else {
    replayMgr.update([]);
    replayMgr.clearTrails();
    if (_lastReplayPlaying) {
      ws.sendCommand('HOLD');
      _lastReplayPlaying = false;
    }
    _lastReplayEpochSync = 0;
  }
});

// ── Live ADS-B traffic (OpenSky) ────────────────────
let liveTimer: number | null = null;

async function fetchLiveTraffic(): Promise<void> {
  if (!observedMgr.visible) return;
  const b = currentViewBounds();
  if (!b) return;
  if (b.lonW >= b.lonE || b.latS >= b.latN) return;
  const latS = Math.max(b.latS, -85);
  const latN = Math.min(b.latN, 85);
  const lonW = Math.max(b.lonW, -180);
  const lonE = Math.min(b.lonE, 180);
  const url = `/api/surveillance/live`
    + `?bounds=${latS},${lonW},${latN},${lonE}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    observedMgr.update(data.items || []);
    observedMgr.updateConflicts(
      data.confpairs || [],
      data.lospairs || [],
    );
    observedMgr.updateAdvisories(data.advisories || {});
    formationMgr.update(data.items || []);
    if (conflictsPanel) {
      conflictsPanel.update_conflicts(
        data.confpairs || [],
        data.lospairs || [],
        data.conf_tcpa || [],
        data.conf_dcpa || [],
      );
    }
    statusBar.updateConflicts(
      data.nconf_cur || 0,
      data.nconf_cur || 0,
      data.nlos_cur || 0,
      data.nlos_cur || 0,
    );
    cmdConsole.echo(
      `[LIVE] ${data.items?.length ?? 0} aircraft`,
    );
  } catch {
    // Non-fatal.
  }
}

function scheduleLiveFetch(): void {
  if (liveTimer !== null) clearTimeout(liveTimer);
  liveTimer = window.setTimeout(
    () => { liveTimer = null; fetchLiveTraffic(); },
    500,
  );
}

// When the user picks a new resolution method in the
// conflicts panel, refresh both live and replay data
// so the new advisories show immediately.
document.addEventListener('formations-updated', ((e: CustomEvent) => {
  formationMgr.setFormations(e.detail.formations || []);
}) as EventListener);

document.addEventListener('reso-method-changed', () => {
  if (observedMgr.visible) fetchLiveTraffic();
  // Force a replay refresh by re-seeking to current time
  if (replayController.state.active) {
    replayController.seek(replayController.state.currentEpoch);
  }
});

// Refresh every 15 seconds while visible.
setInterval(() => {
  if (observedMgr.visible) fetchLiveTraffic();
}, 15_000);

// ── METAR-station reference layer ──────────────────
// Marks airports that report METARs with a green
// outline ring on their dot.  Independent of the
// METAR-data layer; this is a static reference
// overlay that's always on (cheap; cached for a day
// server-side).
let stationsTimer: number | null = null;

async function fetchStations(): Promise<void> {
  const b = currentViewBounds();
  if (!b) return;
  if (b.lonW >= b.lonE || b.latS >= b.latN) return;
  const latS = Math.max(b.latS, -85);
  const latN = Math.min(b.latN, 85);
  const lonW = Math.max(b.lonW, -180);
  const lonE = Math.min(b.lonE, 180);
  const url = `/api/weather/stations`
    + `?bounds=${latS},${lonW},${latN},${lonE}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    const icaos = (data.items || [])
      .filter((s: any) =>
        (s.site_types || []).includes('METAR'),
      )
      .map((s: any) => s.icao);
    navMgr.setMetarStations(icaos);
  } catch {
    // Non-fatal — badges just don't appear.
  }
}

function scheduleStationsFetch(): void {
  if (stationsTimer !== null) clearTimeout(stationsTimer);
  stationsTimer = window.setTimeout(
    () => { stationsTimer = null; fetchStations(); },
    600,
  );
}

// Refresh every 2 minutes while visible (matches
// backend TTL).
setInterval(() => {
  if (pirepMgr.anyVisible()) fetchPireps();
}, 120_000);


// ── METAR → wind field auto-import ──────────────────
let metarWindImportActive = false;

async function syncMetarWindsToField(
  metars: any[],
): Promise<void> {
  const observations = metars
    .filter((m) => typeof m.wdir_deg === 'number'
      && typeof m.wspd_kt === 'number')
    .map((m) => ({
      icao: m.icao,
      lat: m.lat,
      lon: m.lon,
      wdir_deg: m.wdir_deg,
      wspd_kt: m.wspd_kt,
    }));
  try {
    await fetch('/api/wind/import-metars', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ metars: observations }),
    });
    // Refresh the wind-points view so the shadow list
    // comes back and (if visible) the interpolated
    // Field updates.
    setTimeout(() => toolbar.refreshWindInfo(), 200);
    setTimeout(() => scheduleWindFieldFetch(), 300);
  } catch {
    // Non-fatal.
  }
}

document.addEventListener(
  'metar-wind-import-toggle',
  ((e: CustomEvent) => {
    metarWindImportActive = !!e.detail.active;
    if (metarWindImportActive) {
      // Immediate import with the current METAR list.
      if (metarMgr.visible) {
        fetchMetars();
      } else {
        // User turned auto-import on but METARs layer
        // is off — prompt them in console, but also
        // just wait for the next refresh.
        cmdConsole.echo(
          'Auto-import enabled, but METARs layer is '
          + 'off.  Enable WX → METAR stations to '
          + 'populate the wind field.',
        );
      }
    } else {
      // Turned off — clear all METAR-origin points.
      fetch('/api/wind/metar-winds', {
        method: 'DELETE',
      }).then(() => {
        setTimeout(
          () => toolbar.refreshWindInfo(), 200,
        );
        setTimeout(
          () => scheduleWindFieldFetch(), 300,
        );
      }).catch(() => { /* non-fatal */ });
    }
  }) as EventListener,
);

function scheduleMetarFetch(): void {
  if (metarTimer !== null) {
    clearTimeout(metarTimer);
  }
  metarTimer = window.setTimeout(
    () => { metarTimer = null; fetchMetars(); },
    400,
  );
}

viewer.camera.moveEnd.addEventListener(
  scheduleMetarFetch,
);
viewer.camera.moveEnd.addEventListener(
  schedulePirepFetch,
);
viewer.camera.moveEnd.addEventListener(
  scheduleStationsFetch,
);
viewer.camera.moveEnd.addEventListener(
  scheduleLiveFetch,
);
// Initial station fetch so badges appear at startup
// without waiting for the first camera move.
scheduleStationsFetch();

// Re-fetch METARs when unit system changes so decoded
// text reflects the new units.
document.addEventListener('units-changed', () => {
  if (metarMgr.visible) fetchMetars();
});

// Refresh METARs every 3 minutes while the layer is on
// (independent of camera moves — weather updates on
// its own cadence).
setInterval(() => {
  if (metarMgr.visible) fetchMetars();
}, 180_000);

// ── SIGMET / AIRMET / G-AIRMET / CWA / ISIGMET ──────
// Pulls all hazard-polygon feeds in parallel, merges
// into one list the SIGMET manager + panel consume.
// CWAs and ISIGMETs ship with ``rings`` (nested
// multi-polygon); we flatten the first ring into
// the ``coords`` shape SigmetAdvisory expects.  CWAs
// in particular are single-polygon in practice.
function _ringsToCoords(item: any): any {
  if (item.coords) return item;  // already flat
  const rings = item.rings || [];
  if (!rings.length) return { ...item, coords: [] };
  return { ...item, coords: rings[0] };
}

async function fetchAllAdvisories(): Promise<void> {
  if (!sigmetMgr.anyVisible()) return;
  try {
    const [rs, rg, rc, ri, rt] = await Promise.all([
      fetch('/api/weather/airsigmets'),
      fetch('/api/weather/gairmets'),
      fetch('/api/weather/cwas'),
      fetch('/api/weather/isigmets'),
      fetch('/api/weather/tcf'),
    ]);
    const airsigmet = rs.ok
      ? (await rs.json()).items || []
      : [];
    const gairmet = rg.ok
      ? (await rg.json()).items || []
      : [];
    const cwa = rc.ok
      ? ((await rc.json()).items || [])
        .map(_ringsToCoords)
      : [];
    const isigmet = ri.ok
      ? ((await ri.json()).items || [])
        .map(_ringsToCoords)
      : [];
    const tcf = rt.ok
      ? ((await rt.json()).items || [])
        .map(_ringsToCoords)
      : [];
    const combined = [
      ...airsigmet, ...gairmet, ...cwa, ...isigmet,
      ...tcf,
    ];
    sigmetMgr.update(combined);
    weatherPanel.setAdvisories(combined);
  } catch {
    // Non-fatal.
  }
}
// Retain old name for backward compat where referenced.
const fetchAirSigmets = fetchAllAdvisories;

// Refresh every 5 min (upstream feeds update hourly).
setInterval(() => {
  if (sigmetMgr.anyVisible()) fetchAllAdvisories();
}, 300_000);

// ── Airspace (TFRs + SUAs + Class) fetcher ──────────
// Fetches the active datasets in parallel and merges
// them in the AirspaceManager.  TFR/SUA are backend-
// cached and small enough to fetch globally.  Class
// airspace is ~6000 shelves (mostly Class E), so we
// bbox-filter server-side using the current view.
let airspaceFetchTimer: number | null = null;

async function fetchAllAirspace(): Promise<void> {
  if (!airspaceMgr.anyVisible()) return;
  try {
    // Build Class airspace URL with view bbox.  Without
    // bounds the Class E response is ~440 MB; with
    // bounds it's tens of features for a typical view.
    // FAA data is USA-only, so a view over Europe /
    // ocean will legitimately return 0 features.
    let classUrl: string | null = null;
    if (airspaceMgr.anyClassVisible()) {
      const b = currentViewBounds();
      const cls = airspaceMgr.visibleClassCodes();
      if (b && cls) {
        const bounds =
          `${b.latS},${b.lonW},${b.latN},${b.lonE}`;
        classUrl =
          `/api/airspace/classes?classes=${cls}`
          + `&bounds=${bounds}`;
      }
    }
    const [rt, rs, rc] = await Promise.all([
      airspaceMgr.anyTfrVisible()
        ? fetch('/api/airspace/tfrs')
        : Promise.resolve(null as Response | null),
      airspaceMgr.anySuaVisible()
        ? fetch(
          '/api/airspace/suas?classes=P,R,W,A,M',
        )
        : Promise.resolve(null as Response | null),
      classUrl
        ? fetch(classUrl)
        : Promise.resolve(null as Response | null),
    ]);
    const tfrs = rt && rt.ok
      ? (await rt.json()).items || []
      : [];
    const suas = rs && rs.ok
      ? (await rs.json()).items || []
      : [];
    const classes = rc && rc.ok
      ? (await rc.json()).items || []
      : [];
    // Surface counts so the user can diagnose an
    // empty view (e.g., camera over Europe).  Only
    // echo on class-airspace requests since that's
    // the bbox-sensitive one.
    if (classUrl) {
      cmdConsole.echo(
        `[airspace] classes=${airspaceMgr.visibleClassCodes()} `
        + `view=${classes.length} features`,
      );
    }
    airspaceMgr.update([...tfrs, ...suas, ...classes]);
  } catch {
    // Non-fatal.
  }
}

function _onAirspaceToggle(): void {
  // Debounce bursts of toggles (all-on / all-off
  // clicks) so we fetch once after the user settles.
  if (airspaceFetchTimer !== null) {
    clearTimeout(airspaceFetchTimer);
  }
  airspaceFetchTimer = window.setTimeout(() => {
    airspaceFetchTimer = null;
    if (airspaceMgr.anyVisible()) {
      fetchAllAirspace();
    } else {
      airspaceMgr.update([]);
    }
  }, 150);
}

// Refresh active airspace every 5 min for TFRs.
setInterval(() => {
  if (airspaceMgr.anyVisible()) fetchAllAirspace();
}, 300_000);

// Class airspace is bbox-filtered server-side; re-fetch
// when the camera stops moving so pan/zoom updates the
// rendered set.  TFR/SUA are global — harmless to
// re-fetch (backend-cached), so we just refetch all.
viewer.camera.moveEnd.addEventListener(() => {
  if (airspaceMgr.anyClassVisible()) _onAirspaceToggle();
});

// Clicking a list row in the weather panel — fly to
// that station so the user can visually locate it.
document.addEventListener(
  'weather-select-station',
  ((e: CustomEvent) => {
    const { lat, lon } = e.detail;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(
        lon, lat, 100000,
      ),
      duration: 0.8,
    });
  }) as EventListener,
);

// WX tab's OPEN PANEL button.
document.addEventListener(
  'open-weather-panel',
  () => {
    selectAircraft(null);
    windPanel.hide();
    weatherPanel.showList();
  },
);

// ── Cesium click handler ────────────────────────────
// Supports normal mode (select aircraft) and drawing
// mode (capture lat/lon for area tool).
let drawPointCb:
  ((lat: number, lon: number) => void) | null = null;
let drawDoneCb: (() => void) | null = null;

function globeLatLon(
  screenPos: any,
): { lat: number; lon: number } | null {
  const ray = viewer.camera.getPickRay(screenPos);
  if (!ray) return null;
  const cart = viewer.scene.globe.pick(
    ray, viewer.scene,
  );
  if (!cart) return null;
  const carto = Cartographic.fromCartesian(cart);
  return {
    lat: CesiumMath.toDegrees(carto.latitude),
    lon: CesiumMath.toDegrees(carto.longitude),
  };
}

const handler = new ScreenSpaceEventHandler(
  viewer.scene.canvas,
);
handler.setInputAction(
  (click: any) => {
    if (drawPointCb) {
      const ll = globeLatLon(click.position);
      if (ll) drawPointCb(ll.lat, ll.lon);
      return;
    }
    if (windPickActive) {
      const ll = globeLatLon(click.position);
      if (ll) {
        selectAircraft(null);
        windPanel.showPointForCreate(ll.lat, ll.lon);
      }
      windPickActive = false;
      toolbar.clearPickMode();
      return;
    }
    const picked = viewer.scene.pick(click.position);
    if (defined(picked) && picked.id?.name) {
      const name = picked.id.name as string;
      if (name.startsWith('windpin-')) {
        const wp = windBarbMgr.findPointByEntityId(name);
        if (wp) {
          selectAircraft(null);
          weatherPanel.hide();
          windPanel.showPoint(wp);
          return;
        }
      }
      if (name.startsWith('metar-')) {
        const obs = metarMgr.findByEntityId(name);
        if (obs) {
          selectAircraft(null);
          windPanel.hide();
          weatherPanel.showStation(obs);
          return;
        }
      }
      if (name.startsWith('sigmet-')) {
        const adv = sigmetMgr.findByEntityId(name);
        if (adv) {
          selectAircraft(null);
          airspaceMgr.setSelected(null);
          sigmetMgr.setSelected(adv.id);
          windPanel.hide();
          weatherPanel.showAdvisory(adv);
          return;
        }
      }
      if (name.startsWith('apt-')) {
        const icao = name.slice('apt-'.length);
        selectAircraft(null);
        airspaceMgr.setSelected(null);
        sigmetMgr.setSelected(null);
        windPanel.hide();
        weatherPanel.hide();
        // Pass the airport position along so the
        // panel can fetch a TAF in a tight bbox
        // around the field.
        const apt = navMgr.findAirport(icao);
        airportPanel.open(
          icao,
          apt ? { lat: apt.lat, lon: apt.lon } : undefined,
        );
        // Re-sync check state for procs already visible.
        for (const id of procedureMgr.shownIds()) {
          airportPanel.markActive(id);
        }
        cmdConsole.echo(`[APT] ${icao}`);
        return;
      }
      if (name.startsWith('airspace-')) {
        const feat = airspaceMgr.findByEntityId(name);
        if (feat) {
          selectAircraft(null);
          sigmetMgr.setSelected(null);
          airspaceMgr.setSelected(feat.id);
          let label: string;
          let tag: string;
          if (feat.type === 'TFR') {
            tag = 'TFR';
            label = feat.title || feat.notam_key || 'TFR';
          } else if (feat.type === 'CLASS') {
            const cls = feat.airspace_class || '?';
            tag = `CLASS ${cls}`;
            const alt =
              `${Math.round(feat.bottom_ft)}–`
              + `${Math.round(feat.top_ft)} ft`;
            label = `${feat.name || feat.ident || ''} ${alt}`;
          } else {
            tag = 'SUA';
            label = `${feat.sua_class_label || ''} `
              + `${feat.name || feat.sua_id || 'SUA'}`;
          }
          cmdConsole.echo(
            `[${tag}] ${label.trim()}`
            + (feat.state ? ` (${feat.state})` : ''),
          );
          return;
        }
      }
      // Live aircraft — toggle trail.
      if (name.startsWith('live-')) {
        const icao = name.replace('live-', '');
        const nowOn = observedMgr.toggleTrailForAircraft(icao);
        const info = observedMgr.getAircraftInfo(icao);
        const cs = info?.callsign || icao;
        cmdConsole.echo(
          `[LIVE] ${cs} ${info?.typecode || ''} ${info?.registration || ''} — trail ${nowOn ? 'ON' : 'OFF'}`,
        );
        return;
      }
      // Replay aircraft — toggle trail.
      if (name.startsWith('replay-')) {
        const icao = name.replace('replay-', '');
        const nowOn = replayMgr.toggleTrailForAircraft(icao);
        const info = replayMgr.getAircraftInfo(icao);
        const cs = info?.callsign || icao;
        cmdConsole.echo(
          `[REPLAY] ${cs} ${info?.typecode || ''} ${info?.registration || ''} — trail ${nowOn ? 'ON' : 'OFF'}`,
        );
        return;
      }
      // Sim aircraft or other clickable entities.
      windPanel.hide();
      weatherPanel.hide();
      airportPanel.hide();
      airspaceMgr.setSelected(null);
      sigmetMgr.setSelected(null);
      selectAircraft(name);
    } else {
      windPanel.hide();
      weatherPanel.hide();
      airportPanel.hide();
      airspaceMgr.setSelected(null);
      sigmetMgr.setSelected(null);
      selectAircraft(null);
    }
  },
  ScreenSpaceEventType.LEFT_CLICK,
);
handler.setInputAction(
  (click: any) => {
    if (drawDoneCb) {
      drawDoneCb();
    }
  },
  ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
);

// Wire area tool drawing callbacks.
areaTool.setDrawCallbacks(
  (pointCb, doneCb) => {
    drawPointCb = pointCb;
    drawDoneCb = doneCb;
  },
  () => {
    drawPointCb = null;
    drawDoneCb = null;
  },
);

// Keep the weather panel's in-panel toggles reflecting
// the current map-layer state.
/**
 * Visibility controller for the weather time scrubber.
 *
 * Disabled for now — radar + satellite always show
 * "current / latest" imagery via the
 * ``WeatherImageryManager`` defaults.  The scrubber
 * component and its event wiring remain in the codebase
 * so we can re-enable scrubbing by flipping this flag
 * back to the original visibility-tracking logic.
 *
 * To re-enable, restore:
 *   const anyImagery = wxImageryMgr.radarVisible()
 *     || wxImageryMgr.satelliteVisible();
 *   wxTimeStrip.hidden = !anyImagery;
 */
function _syncWxTimeStripVisibility(): void {
  // Scrubber intentionally hidden.
  wxTimeStrip.hidden = true;
}

// When the user scrubs the time strip, propagate the
// new timestamp to the imagery manager (which rebuilds
// the layers with the right URL).
document.addEventListener(
  'weather-time-change',
  ((e: CustomEvent) => {
    wxImageryMgr.setTime(e.detail.time);
  }) as EventListener,
);

function _syncWeatherToggles(): void {
  weatherPanel.setToggleStates(
    toolbar.showMetars,
    toolbar.showSigmets,
    false,               // text-AIRMET toggle retired
    toolbar.showGairmets,
  );
}

// ── Lat/lon graticule ───────────────────────────────
let _graticuleLayer: ImageryLayer | null = null;

function _toggleGraticule(on: boolean): void {
  if (on && !_graticuleLayer) {
    const provider = new GridImageryProvider({});
    _graticuleLayer = viewer.imageryLayers.addImageryProvider(provider);
    _graticuleLayer.alpha = 0.35;
  } else if (!on && _graticuleLayer) {
    viewer.imageryLayers.remove(_graticuleLayer);
    _graticuleLayer = null;
  }
}

// ── Layer opacity events ────────────────────────────
document.addEventListener(
  'layer-opacity',
  ((e: CustomEvent) => {
    const { layer, opacity: val } = e.detail;
    opacity.set(layer, val);
  }) as EventListener,
);

// ── Layer toggle events ─────────────────────────────
document.addEventListener(
  'toggle-layer',
  ((e: CustomEvent) => {
    const { layer, visible } = e.detail;
    layerPanel.setLayerState(layer, visible);
    switch (layer) {
      case 'trails':
        trailMgr.setVisible(visible);
        observedMgr.setTrailsVisible(visible);
        replayMgr.setTrailsVisible(visible);
        // Tell BlueSky sim to start/stop trails.
        ws.sendCommand(visible ? 'TRAIL ON' : 'TRAIL OFF');
        if (!visible) {
          trailMgr.clear();
          observedMgr.clearTrails();
          replayMgr.clearTrails();
        }
        break;
      case 'trails-display':
        trailMgr.setVisible(visible);
        observedMgr.setTrailsVisible(visible);
        replayMgr.setTrailsVisible(visible);
        if (!visible) {
          trailMgr.clear();
          observedMgr.clearTrails();
          replayMgr.clearTrails();
        }
        break;
      case 'routes':
        routeMgr.setVisible(visible);
        break;
      case 'labels':
        aircraftMgr.setLabelsVisible(visible);
        break;
      case 'leaders':
        aircraftMgr.setLeadersVisible(visible);
        observedMgr.setLeadersVisible(visible);
        replayMgr.setLeadersVisible(visible);
        break;
      case 'advisories':
        observedMgr.setAdvisoriesVisible(visible);
        replayMgr.setAdvisoriesVisible(visible);
        break;
      case 'formations': {
        formationMgr.setVisible(visible);
        const fp = document.querySelector('formations-panel') as any;
        if (fp) fp.hidden = !visible;
        if (visible) {
          fetch('/api/formations').then(r => r.json())
            .then(d => formationMgr.setFormations(d.formations || []))
            .catch(() => {});
        }
        break;
      }
      case 'pz':
        aircraftMgr.setPzVisible(visible);
        observedMgr.setPzVisible(visible);
        replayMgr.setPzVisible(visible);
        break;
      case 'wind-barbs':
        windBarbMgr.setVisible(visible);
        break;
      case 'wind-field':
        windFieldMgr.setVisible(visible);
        if (visible) {
          scheduleWindFieldFetch();
        }
        break;
      case 'metars':
        metarMgr.setVisible(visible);
        weatherPanel.setEnabled(visible);
        toolbar.showMetars = visible;
        _syncWeatherToggles();
        if (visible) {
          scheduleMetarFetch();
        } else {
          weatherPanel.setMetars([]);
        }
        break;
      case 'pireps':
        pirepMgr.setVisible(visible);
        toolbar.showPireps = visible;
        if (visible) {
          schedulePirepFetch();
        } else {
          pirepMgr.update([]);
        }
        break;
      case 'live-traffic':
        observedMgr.setVisible(visible);
        toolbar.showLiveTraffic = visible;
        if (visible) {
          scheduleLiveFetch();
        } else {
          observedMgr.update([]);
        }
        break;
      case 'replay-traffic':
        replayMgr.setVisible(visible);
        if (!visible) {
          replayMgr.update([]);
          replayMgr.clearTrails();
        }
        break;
      case 'interpolation':
        observedMgr.setInterpolation(visible);
        toolbar.showInterpolation = visible;
        break;
      case 'sigmets':
        sigmetMgr.setVisibleFor('SIGMET', visible);
        toolbar.showSigmets = visible;
        weatherPanel.setAdvisoriesEnabled(
          sigmetMgr.anyVisible(),
        );
        _syncWeatherToggles();
        if (sigmetMgr.anyVisible()) {
          fetchAirSigmets();
        } else {
          weatherPanel.setAdvisories([]);
        }
        break;
      case 'gairmets':
        sigmetMgr.setVisibleFor('G-AIRMET', visible);
        toolbar.showGairmets = visible;
        weatherPanel.setAdvisoriesEnabled(
          sigmetMgr.anyVisible(),
        );
        _syncWeatherToggles();
        if (sigmetMgr.anyVisible()) {
          fetchAllAdvisories();
        } else {
          weatherPanel.setAdvisories([]);
        }
        break;
      case 'radar':
        wxImageryMgr.setRadarVisible(visible);
        toolbar.showRadar = visible;
        _syncWxTimeStripVisibility();
        break;
      case 'satellite':
        wxImageryMgr.setSatelliteVisible(visible);
        toolbar.showSatellite = visible;
        _syncWxTimeStripVisibility();
        break;
      // Named weather tile overlays (NWS + IEM).
      case 'wx-mrms':
      case 'wx-goes-vis':
      case 'wx-spc-outlook':
      case 'wx-wwa':
      case 'wx-ndfd-temp':
      case 'wx-smoke': {
        const wxId = layer.slice(3) as any;
        void wxImageryMgr.setTileVisible(wxId, visible);
        break;
      }
      case 'tfrs':
        airspaceMgr.setVisibleFor('TFR', visible);
        toolbar.showTfrs = visible;
        _onAirspaceToggle();
        break;
      case 'sua-p':
        airspaceMgr.setVisibleFor('SUA_P', visible);
        toolbar.showSuaP = visible;
        _onAirspaceToggle();
        break;
      case 'sua-r':
        airspaceMgr.setVisibleFor('SUA_R', visible);
        toolbar.showSuaR = visible;
        _onAirspaceToggle();
        break;
      case 'sua-w':
        airspaceMgr.setVisibleFor('SUA_W', visible);
        toolbar.showSuaW = visible;
        _onAirspaceToggle();
        break;
      case 'sua-a':
        airspaceMgr.setVisibleFor('SUA_A', visible);
        toolbar.showSuaA = visible;
        _onAirspaceToggle();
        break;
      case 'sua-m':
        airspaceMgr.setVisibleFor('SUA_M', visible);
        toolbar.showSuaM = visible;
        _onAirspaceToggle();
        break;
      case 'class-b':
        airspaceMgr.setVisibleFor('CLASS_B', visible);
        toolbar.showClassB = visible;
        _onAirspaceToggle();
        break;
      case 'class-c':
        airspaceMgr.setVisibleFor('CLASS_C', visible);
        toolbar.showClassC = visible;
        _onAirspaceToggle();
        break;
      case 'class-d':
        airspaceMgr.setVisibleFor('CLASS_D', visible);
        toolbar.showClassD = visible;
        _onAirspaceToggle();
        break;
      case 'class-e2':
        airspaceMgr.setVisibleFor('CLASS_E2', visible);
        toolbar.showClassE2 = visible;
        _onAirspaceToggle();
        break;
      case 'class-e3':
        airspaceMgr.setVisibleFor('CLASS_E3', visible);
        toolbar.showClassE3 = visible;
        _onAirspaceToggle();
        break;
      case 'class-e4':
        airspaceMgr.setVisibleFor('CLASS_E4', visible);
        toolbar.showClassE4 = visible;
        _onAirspaceToggle();
        break;
      case 'class-e5':
        airspaceMgr.setVisibleFor('CLASS_E5', visible);
        toolbar.showClassE5 = visible;
        _onAirspaceToggle();
        break;
      case 'class-e6':
        airspaceMgr.setVisibleFor('CLASS_E6', visible);
        toolbar.showClassE6 = visible;
        _onAirspaceToggle();
        break;
      case 'class-e-other':
        airspaceMgr.setVisibleFor('CLASS_E_OTHER', visible);
        toolbar.showClassEOther = visible;
        _onAirspaceToggle();
        break;
      case 'chart-sectional':
        void chartMgr.setVisible('sectional', visible);
        toolbar.showChartSectional = visible;
        break;
      case 'chart-tac':
        void chartMgr.setVisible('tac', visible);
        toolbar.showChartTac = visible;
        break;
      case 'chart-ifr-low':
        void chartMgr.setVisible('ifr-low', visible);
        toolbar.showChartIfrLow = visible;
        break;
      case 'chart-ifr-high':
        void chartMgr.setVisible('ifr-high', visible);
        toolbar.showChartIfrHigh = visible;
        break;
      case 'airports':
        navMgr.setAirportsVisible(visible);
        break;
      case 'waypoints':
        navMgr.setWaypointsVisible(visible);
        break;
      case 'conflicts':
        if (conflictsPanel) {
          conflictsPanel.hidden = !visible;
          if (visible) conflictsPanel.expanded = true;
        }
        break;
      case 'graticule':
        _toggleGraticule(visible);
        break;
    }
  }) as EventListener,
);

// ── Toolbar tab → show/hide area tool ───────────────
document.addEventListener(
  'tab-changed',
  ((e: CustomEvent) => {
    areaTool.hidden = e.detail.tab !== 'areas';
  }) as EventListener,
);

// ── Scenario loader ─────────────────────────────────
toolbar.loadScenarios();
document.addEventListener(
  'load-scenario',
  ((e: CustomEvent) => {
    const fn = e.detail.filename;
    sendCommand(`IC ${fn}`);
  }) as EventListener,
);

// ── 2D / 3D view toggle ─────────────────────────────
document.addEventListener(
  'toggle-view',
  ((e: CustomEvent) => {
    if (e.detail.is3D) {
      viewer.scene.mode = SceneMode.SCENE3D;
    } else {
      viewer.scene.mode = SceneMode.SCENE2D;
    }
  }) as EventListener,
);

// ── Altitude exaggeration ───────────────────────────
document.addEventListener(
  'alt-scale',
  ((e: CustomEvent) => {
    const scale = e.detail.scale;
    aircraftMgr.setAltScale(scale);
    routeMgr.setAltScale(scale);
    trailMgr.setAltScale(scale);
    areaMgr.setAltScale(scale);
    windBarbMgr.setAltScale(scale);
    windFieldMgr.setAltScale(scale);
    sigmetMgr.setAltScale(scale);
    airspaceMgr.setAltScale(scale);
    procedureMgr.setAltScale(scale);
    pirepMgr.setAltScale(scale);
    observedMgr.setAltScale(scale);
    replayMgr.setAltScale(scale);
    scheduleWindFieldFetch();
  }) as EventListener,
);

// Set default to 10x so altitudes are visible.
aircraftMgr.setAltScale(2);
routeMgr.setAltScale(2);
trailMgr.setAltScale(2);
areaMgr.setAltScale(2);
windBarbMgr.setAltScale(2);
windFieldMgr.setAltScale(2);
sigmetMgr.setAltScale(2);
airspaceMgr.setAltScale(2);
procedureMgr.setAltScale(2);
pirepMgr.setAltScale(2);
observedMgr.setAltScale(2);
replayMgr.setAltScale(2);

// ── Layer-opacity routing ──────────────────────────
// The opacity service is the single source of
// truth; managers subscribe via this dispatcher.
// Routes per-key changes to the right manager.
function _applyOpacity(key: string, alpha: number): void {
  switch (key) {
    case 'TFR':
    case 'SUA_P':
    case 'SUA_R':
    case 'SUA_W':
    case 'SUA_A':
    case 'SUA_M':
    case 'CLASS_B':
    case 'CLASS_C':
    case 'CLASS_D':
    case 'CLASS_E2':
    case 'CLASS_E3':
    case 'CLASS_E4':
    case 'CLASS_E5':
    case 'CLASS_E6':
    case 'CLASS_E_OTHER':
      airspaceMgr.setOpacityFor(key as any, alpha);
      break;
    case 'SIGMET':
    case 'AIRMET':
    case 'G-AIRMET':
      sigmetMgr.setOpacityFor(key as any, alpha);
      break;
    case 'PROCEDURE':
      procedureMgr.setOpacity(alpha);
      break;
    case 'PIREP':
      pirepMgr.setOpacity(alpha);
      break;
    case 'CHART_SECTIONAL':
      chartMgr.setOpacity('sectional', alpha);
      break;
    case 'CHART_TAC':
      chartMgr.setOpacity('tac', alpha);
      break;
    case 'CHART_IFR_LOW':
      chartMgr.setOpacity('ifr-low', alpha);
      break;
    case 'CHART_IFR_HIGH':
      chartMgr.setOpacity('ifr-high', alpha);
      break;
  }
}
opacity.onChange(_applyOpacity);
// Apply persisted values on boot so the user's
// last preferences are honoured.
for (const [k, v] of Object.entries(opacity.all())) {
  _applyOpacity(k, v);
}

// ── Toolbar opacity-panel toggle ────────────────────
document.addEventListener(
  'open-opacity-panel',
  (() => {
    opacityPanel.hidden = false;
  }) as EventListener,
);

// ── UI Mode application ──────────────────────────────
// Apply saved mode on startup, then listen for changes.

/** Turn all layer toggles off, then turn on only the
 *  ones in the preset.  Dispatches toggle-layer events
 *  so every manager picks up the change. */
function applyMode(id: ModeId): void {
  const preset = MODE_PRESETS[id];
  if (!preset) return;
  saveMode(id);
  toolbar.currentMode = id;

  // Collect all known layer IDs from the toolbar
  // state and turn everything off first.
  const allLayers = [
    'trails', 'routes', 'labels', 'leaders', 'pz',
    'airports', 'waypoints', 'wind-barbs', 'wind-field',
    'metars', 'pireps', 'sigmets', 'gairmets',
    'radar', 'satellite',
    'wx-mrms', 'wx-goes-vis', 'wx-spc-outlook',
    'wx-wwa', 'wx-ndfd-temp', 'wx-smoke',
    'tfrs', 'sua-p', 'sua-r', 'sua-w', 'sua-a', 'sua-m',
    'class-b', 'class-c', 'class-d',
    'class-e2', 'class-e3', 'class-e4',
    'class-e5', 'class-e6', 'class-e-other',
    'chart-sectional', 'chart-tac',
    'chart-ifr-low', 'chart-ifr-high',
  ];
  const onSet = new Set(preset.layersOn);
  for (const layer of allLayers) {
    const on = onSet.has(layer);
    document.dispatchEvent(new CustomEvent(
      'toggle-layer',
      { detail: { layer, visible: on } },
    ));
  }

  // Set active tab.
  toolbar.activeTab = preset.defaultTab as any;

  // Traffic list visibility.
  const trafficList = document.querySelector(
    'bluesky-traffic-list',
  ) as HTMLElement | null;
  if (trafficList) {
    trafficList.hidden = !preset.trafficListVisible;
  }

  // Console expansion.
  if (!preset.consoleExpanded) {
    // Minimize the console to one line.
    cmdConsole.style.maxHeight = '32px';
  } else {
    cmdConsole.style.maxHeight = '';
  }
}

// Apply on startup.
const initialMode = getSavedMode();
toolbar.currentMode = initialMode;
// Defer to next tick so all managers are initialized.
setTimeout(() => applyMode(initialMode), 100);

// Listen for mode changes from the toolbar dropdown.
document.addEventListener(
  'mode-change',
  ((e: Event) => {
    const ce = e as CustomEvent<{ mode: string }>;
    applyMode(ce.detail.mode as ModeId);
  }) as EventListener,
);

// ── Start ───────────────────────────────────────────
ws.connect();
cmdConsole.focus();

// ── Imagery / Terrain / Ion token wiring ────────────
function refreshLayerOptions(): void {
  const ionOk = isIonEnabled();
  toolbar.setImageryOptions(
    ALL_IMAGERY.map((o) => ({
      id: o.id,
      label: o.label,
      disabled: o.needsIon && !ionOk,
    })),
    'cartodb-dark',
  );
  toolbar.setTerrainOptions(
    ALL_TERRAIN.map((o) => ({
      id: o.id,
      label: o.label,
      disabled: o.needsIon && !ionOk,
    })),
    ionOk ? 'world-terrain' : 'flat',
  );
  toolbar.setIonTokenStatus(ionOk);

  layerPanel.imageryOptions = ALL_IMAGERY.map((o) => ({
    id: o.id, label: o.label,
    disabled: o.needsIon && !ionOk,
  }));
  layerPanel.currentImagery = 'cartodb-dark';
  layerPanel.terrainOptions = ALL_TERRAIN.map((o) => ({
    id: o.id, label: o.label,
    disabled: o.needsIon && !ionOk,
  }));
  layerPanel.currentTerrain = ionOk ? 'world-terrain' : 'flat';
  layerPanel.ionTokenSet = ionOk;

  if (ionOk) {
    const wt = ALL_TERRAIN.find(o => o.id === 'world-terrain');
    if (wt) setTerrain(viewer, wt).catch(() => {});
  }
}
refreshLayerOptions();

document.addEventListener(
  'imagery-change',
  ((e: CustomEvent) => {
    const opt = ALL_IMAGERY.find(
      (o) => o.id === e.detail.id,
    );
    if (!opt) return;
    setImagery(viewer, opt).then(() => {
      // Basemap switch calls imageryLayers.removeAll() —
      // re-attach any weather imagery the user had on.
      wxImageryMgr.reapply();
    }).catch((err) => {
      alert(`Failed to load imagery: ${err}`);
    });
  }) as EventListener,
);

// Refresh radar/satellite tiles every 5 minutes so the
// displayed imagery stays fresh — but only when the
// user is in LIVE mode.  If they've scrubbed to a
// historical frame, don't snap them back to current.
setInterval(() => {
  if (wxImageryMgr.getTime() === null) {
    wxImageryMgr.refresh();
    // Re-derive the "LIVE" anchor timestamp so the
    // readout stays meaningful as time advances.
    wxTimeStrip.jumpLive();
  }
}, 300_000);

document.addEventListener(
  'terrain-change',
  ((e: CustomEvent) => {
    const opt = ALL_TERRAIN.find(
      (o) => o.id === e.detail.id,
    );
    if (!opt) return;
    setTerrain(viewer, opt).catch((err) => {
      alert(`Failed to load terrain: ${err}`);
    });
  }) as EventListener,
);

document.addEventListener(
  'ion-token-set',
  ((e: CustomEvent) => {
    setIonToken(e.detail.token);
    refreshLayerOptions();
  }) as EventListener,
);

// Check for Cesium Ion token and upgrade if available.
applyIonConfig(viewer).then(() => refreshLayerOptions());

// ── Backend state sync ──────────────────────────────
// Poll /api/state every 2 seconds to keep toolbar
// buttons in sync with actual backend state — so
// commands issued via console, scenario file, or
// another client are reflected in the UI.
async function pollBackendState(): Promise<void> {
  try {
    const res = await fetch('/api/state');
    if (!res.ok) return;
    const s = await res.json();
    toolbar.syncBackendState({
      trails: !!s.trails_active,
      area: !!s.area_active,
      asasMethod: s.asas_method,
      asasMethods: s.asas_methods,
      resoMethod: s.reso_method,
      resoMethods: s.reso_methods,
      resoPluginsAvailable: s.reso_plugins_available,
    });
  } catch {
    // Non-fatal.
  }
}
setInterval(pollBackendState, 2000);
pollBackendState();

console.log('BlueSky ATM Simulator initialized');
