/** REST API client for simulation control and queries. */

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// Simulation control
export const simOp = () => request('/sim/op', { method: 'POST' });
export const simHold = () => request('/sim/hold', { method: 'POST' });
export const simReset = () => request('/sim/reset', { method: 'POST' });
export const simFf = (seconds: number) =>
  request('/sim/ff', { method: 'POST', body: JSON.stringify({ seconds }) });
export const simDtmult = (multiplier: number) =>
  request('/sim/dtmult', { method: 'POST', body: JSON.stringify({ multiplier }) });
export const simInfo = () => request<any>('/sim/info');

// Commands
export const executeCommand = (command: string) =>
  request('/commands', { method: 'POST', body: JSON.stringify({ command }) });
export const listCommands = () => request<any[]>('/commands/list');

// Scenarios
export const listScenarios = () => request<any[]>('/scenarios');
export const loadScenario = (filename: string) =>
  request('/scenarios/load', { method: 'POST', body: JSON.stringify({ filename }) });

// Aircraft
export const listAircraft = () => request<any[]>('/aircraft');
export const getAircraft = (acid: string) => request<any>(`/aircraft/${acid}`);
export const getRoute = (acid: string) =>
  request<any>(`/aircraft/${acid}/route`);
export const getAircraftDetail = (acid: string) =>
  request<any>(`/aircraft/${acid}/detail`);
