/** TypeScript types mirroring the FastAPI Pydantic models and WS protocol. */

export interface AcData {
  simt: number;
  id: string[];
  lat: number[];
  lon: number[];
  alt: number[];   // meters
  tas: number[];   // m/s
  cas: number[];   // m/s
  gs: number[];    // m/s
  trk: number[];   // degrees
  vs: number[];    // m/s
  inconf: boolean[];
  tcpamax?: number[];
  rpz?: number[];
  nconf_cur: number;
  nconf_tot: number;
  nlos_cur: number;
  nlos_tot: number;
}

export interface SimInfo {
  simt: number;
  simdt: number;
  utc: string;
  dtmult: number;
  ntraf: number;
  state: number;
  state_name: string;
  scenname: string;
}

export interface TrailData {
  traillat0: number[];
  traillon0: number[];
  traillat1: number[];
  traillon1: number[];
}

export interface RouteData {
  acid: string;
  iactwp: number;
  aclat: number;
  aclon: number;
  wplat: number[];
  wplon: number[];
  wpalt: number[];
  wpspd: number[];
  wpname: string[];
}

export interface WsMessage {
  topic: string;
  data: AcData | SimInfo | TrailData | RouteData;
}

export interface WsClientMessage {
  action: 'subscribe' | 'unsubscribe' | 'command';
  topics?: string[];
  command?: string;
}

// Unit conversion constants
export const FT = 0.3048;         // feet to meters
export const KTS = 0.514444;      // knots to m/s
export const NM = 1852;           // nautical miles to meters
