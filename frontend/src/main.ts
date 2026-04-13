/**
 * Main entry point — wires Cesium viewer, WebSocket, and
 * all BlueSky UI components together.
 */
import {
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
import { SimWebSocket } from './services/websocket';
import type { AcData, SimInfo, TrailData } from './types';

// Import Lit components (self-registering).
import './ui/toolbar';
import './ui/status-bar';
import './ui/traffic-list';
import './ui/console';
import './ui/aircraft-panel';
import './ui/camera-controls';

import type { BlueSkyToolbar } from './ui/toolbar';
import type { BlueSkyStatusBar } from './ui/status-bar';
import type { BlueSkyTrafficList } from './ui/traffic-list';
import type { BlueSkyConsole } from './ui/console';
import type { AircraftPanel } from './ui/aircraft-panel';
import type { CameraControls } from './ui/camera-controls';

// ── Initialize Cesium viewer ────────────────────────
const viewer = createViewer('cesium-container');
const aircraftMgr = new AircraftManager(viewer);
const trailMgr = new TrailManager(viewer);
const routeMgr = new RouteManager(viewer);
const navMgr = new NavdataManager(viewer);

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
    trailMgr.clear();
    routeMgr.clear();
    acPanel.hide();
    aircraftMgr.select(null);
  }
}
cmdConsole.setCommandHandler(sendCommand);
acPanel.setCommandHandler(sendCommand);
cmdConsole.loadCommandBriefs();

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

// ── Cesium click handler → select aircraft ──────────
const handler = new ScreenSpaceEventHandler(
  viewer.scene.canvas,
);
handler.setInputAction(
  (click: any) => {
    const picked = viewer.scene.pick(click.position);
    if (defined(picked) && picked.id?.name) {
      selectAircraft(picked.id.name);
    } else {
      selectAircraft(null);
    }
  },
  ScreenSpaceEventType.LEFT_CLICK,
);

// ── Layer toggle events ─────────────────────────────
document.addEventListener(
  'toggle-layer',
  ((e: CustomEvent) => {
    const { layer, visible } = e.detail;
    switch (layer) {
      case 'trails':
        trailMgr.setVisible(visible);
        // Also tell BlueSky sim to start/stop trails.
        ws.sendCommand(visible ? 'TRAIL ON' : 'TRAIL OFF');
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

console.log('BlueSky ATM Simulator initialized');
