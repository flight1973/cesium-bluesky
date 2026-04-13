/**
 * Main entry point — wires Cesium viewer, WebSocket, and
 * all BlueSky UI components together.
 */
import {
  Cartographic,
  Ellipsoid,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  SceneMode,
  HeadingPitchRange,
  Math as CesiumMath,
  defined,
} from 'cesium';
import { createViewer, applyIonConfig } from './cesium/viewer';
import { AircraftManager } from './cesium/entities/aircraft';
import { TrailManager } from './cesium/entities/trails';
import { RouteManager } from './cesium/entities/routes';
import { NavdataManager } from './cesium/entities/navdata';
import { AreaManager } from './cesium/entities/areas';
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
import './ui/camera-controls';

import type { BlueSkyToolbar } from './ui/toolbar';
import type { BlueSkyStatusBar } from './ui/status-bar';
import type { BlueSkyTrafficList } from './ui/traffic-list';
import type { BlueSkyConsole } from './ui/console';
import type { AircraftPanel } from './ui/aircraft-panel';
import type { FmsPanel } from './ui/fms-panel';
import type { AreaTool } from './ui/area-tool';
import type { CameraControls } from './ui/camera-controls';

// ── Initialize Cesium viewer ────────────────────────
const viewer = createViewer('cesium-container');
const aircraftMgr = new AircraftManager(viewer);
const trailMgr = new TrailManager(viewer);
const routeMgr = new RouteManager(viewer);
const navMgr = new NavdataManager(viewer);
const areaMgr = new AreaManager(viewer);
areaMgr.startPolling(2000);

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
const camCtrl = document.querySelector(
  'camera-controls',
) as CameraControls;
camCtrl.setViewer(viewer);

// ── Wire ACDATA → entities + traffic list ───────────
ws.on('ACDATA', (data: AcData) => {
  aircraftMgr.update(data);
  trafficList.updateFromAcData(data);
  trailMgr.updateAltLookup(data);
  statusBar.updateConflicts(
    data.nconf_cur,
    data.nconf_tot,
    data.nlos_cur,
    data.nlos_tot,
  );
});

// ── Wire SIMINFO → status bar + toolbar ─────────────
ws.on('SIMINFO', (data: SimInfo) => {
  statusBar.updateFromSimInfo(data);
  toolbar.updateState(data.state_name, data.dtmult);
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
  ws.sendCommand(cmd);
  cmdConsole.echo(cmd);

  // Clear frontend state on RESET or IC commands.
  const upper = cmd.trim().toUpperCase();
  if (
    upper === 'RESET'
    || upper.startsWith('IC ')
  ) {
    clearSimState();
  }
}
cmdConsole.setCommandHandler(sendCommand);
acPanel.setCommandHandler(sendCommand);
fmsPanel.setCommandHandler(sendCommand);
areaTool.setCommandHandler(sendCommand);
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
            CesiumMath.toRadians(-45),
            200000,
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

// ── FMS panel open event ────────────────────────────
document.addEventListener(
  'open-fms',
  ((e: CustomEvent) => {
    fmsPanel.open(e.detail.acid);
  }) as EventListener,
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
    const picked = viewer.scene.pick(click.position);
    if (defined(picked) && picked.id?.name) {
      selectAircraft(picked.id.name);
    } else {
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

// ── Layer toggle events ─────────────────────────────
document.addEventListener(
  'toggle-layer',
  ((e: CustomEvent) => {
    const { layer, visible } = e.detail;
    switch (layer) {
      case 'trails':
        trailMgr.setVisible(visible);
        // Tell BlueSky sim to start/stop trails.
        ws.sendCommand(visible ? 'TRAIL ON' : 'TRAIL OFF');
        if (!visible) trailMgr.clear();
        break;
      case 'trails-display':
        // Backend-initiated state change — just update
        // display, don't re-send TRAIL command.
        trailMgr.setVisible(visible);
        if (!visible) trailMgr.clear();
        break;
      case 'routes':
        routeMgr.setVisible(visible);
        break;
      case 'labels':
        aircraftMgr.setLabelsVisible(visible);
        break;
      case 'leaders':
        aircraftMgr.setLeadersVisible(visible);
        break;
      case 'pz':
        aircraftMgr.setPzVisible(visible);
        break;
      case 'airports':
        navMgr.setAirportsVisible(visible);
        break;
      case 'waypoints':
        navMgr.setWaypointsVisible(visible);
        break;
    }
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
  }) as EventListener,
);

// Set default to 10x so altitudes are visible.
aircraftMgr.setAltScale(10);
routeMgr.setAltScale(10);
trailMgr.setAltScale(10);

// ── Start ───────────────────────────────────────────
ws.connect();
cmdConsole.focus();

// Check for Cesium Ion token and upgrade if available.
applyIonConfig(viewer);

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
    });
  } catch {
    // Non-fatal.
  }
}
setInterval(pollBackendState, 2000);
pollBackendState();

console.log('BlueSky ATM Simulator initialized');
