export interface ReplaySession {
  label: string;
  date: string;
  bbox: string;
  hours: string;
  row_count: number;
}

export interface ReplayState {
  active: boolean;
  playing: boolean;
  session: ReplaySession | null;
  currentEpoch: number;
  minEpoch: number;
  maxEpoch: number;
  speed: number;
}

type Listener = (state: ReplayState) => void;
type DataListener = (data: any) => void;
type TrailListener = (trails: Record<string, number[][]>) => void;

class ReplayController {
  private _state: ReplayState = {
    active: false,
    playing: false,
    session: null,
    currentEpoch: 0,
    minEpoch: 0,
    maxEpoch: 0,
    speed: 1,
  };

  private _listeners: Listener[] = [];
  private _dataListeners: DataListener[] = [];
  private _trailListeners: TrailListener[] = [];
  private _tickTimer: number | null = null;
  private _fetchTimer: number | null = null;
  private _trailTimer: number | null = null;
  private _lastRealTime = 0;
  private _lastTrailEpoch = 0;

  get state(): ReplayState {
    return { ...this._state };
  }

  onChange(fn: Listener): void {
    this._listeners.push(fn);
  }

  onData(fn: DataListener): void {
    this._dataListeners.push(fn);
  }

  onTrails(fn: TrailListener): void {
    this._trailListeners.push(fn);
  }

  private _notify(): void {
    const s = this.state;
    for (const fn of this._listeners) fn(s);
  }

  async loadSessions(): Promise<ReplaySession[]> {
    const res = await fetch('/api/surveillance/replay/sessions');
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions || [];
  }

  async start(label: string): Promise<void> {
    const res = await fetch(
      `/api/surveillance/replay/${label}/range`,
    );
    if (!res.ok) return;
    const range = await res.json();

    this._state = {
      active: true,
      playing: false,
      session: null,
      currentEpoch: range.min_t,
      minEpoch: range.min_t,
      maxEpoch: range.max_t,
      speed: 1,
    };

    const sessions = await this.loadSessions();
    this._state.session =
      sessions.find(s => s.label === label) || null;

    this._notify();
    await this._fetch();
  }

  stop(): void {
    this.pause();
    this._state.active = false;
    this._state.session = null;
    this._trailCache = {};
    this._trailCacheEnd = 0;
    this._lastTrailEpoch = 0;
    this._notify();
    for (const fn of this._dataListeners) fn({ items: [] });
  }

  play(): void {
    if (!this._state.active) return;
    this._state.playing = true;
    this._lastRealTime = Date.now();
    this._startTick();
    this._notify();
  }

  pause(): void {
    this._state.playing = false;
    if (this._tickTimer !== null) {
      clearInterval(this._tickTimer);
      this._tickTimer = null;
    }
    if (this._fetchTimer !== null) {
      clearTimeout(this._fetchTimer);
      this._fetchTimer = null;
    }
    this._notify();
  }

  seek(epoch: number): void {
    const prev = this._state.currentEpoch;
    this._state.currentEpoch = Math.max(
      this._state.minEpoch,
      Math.min(this._state.maxEpoch, epoch),
    );
    this._lastRealTime = Date.now();
    // Force full trail re-fetch so trails shorten/grow to match.
    this._trailCacheEnd = 0;
    this._lastTrailEpoch = 0;
    this._trailCache = {};
    this._notify();
    this._fetch();
  }

  setSpeed(speed: number): void {
    this._lastRealTime = Date.now();
    this._state.speed = speed;
    this._notify();
  }

  private _startTick(): void {
    if (this._tickTimer !== null) return;
    this._tickTimer = window.setInterval(() => {
      const now = Date.now();
      const dtReal = (now - this._lastRealTime) / 1000;
      this._lastRealTime = now;
      this._state.currentEpoch += dtReal * this._state.speed;

      if (this._state.currentEpoch >= this._state.maxEpoch) {
        this._state.currentEpoch = this._state.maxEpoch;
        this.pause();
      }
      this._notify();
    }, 200);

    this._scheduleFetch();
  }

  private _scheduleFetch(): void {
    if (this._fetchTimer !== null) return;
    this._fetchTimer = window.setTimeout(() => {
      this._fetchTimer = null;
      this._fetch();
      if (this._state.playing) this._scheduleFetch();
    }, 2000);
  }

  private _trailDebounce: number | null = null;

  private async _fetch(): Promise<void> {
    if (!this._state.active || !this._state.session) return;
    const label = this._state.session.label;
    const t = Math.round(this._state.currentEpoch);
    try {
      const tol = Math.max(10, Math.ceil(this._state.speed * 4));
      const res = await fetch(
        `/api/surveillance/replay/${label}?t=${t}&tolerance=${tol}`,
      );
      if (!res.ok) return;
      const data = await res.json();
      for (const fn of this._dataListeners) {
        fn(data);
      }
    } catch {
      // Non-fatal.
    }
    // Debounce trail fetch to avoid hammering during scrub.
    if (this._trailDebounce !== null) {
      clearTimeout(this._trailDebounce);
    }
    this._trailDebounce = window.setTimeout(() => {
      this._trailDebounce = null;
      this._fetchTrails();
    }, 500);
  }

  private _trailCache: Record<string, number[][]> = {};
  private _trailCacheEnd = 0;
  private _fullTrailPending = false;

  private async _fetchTrails(): Promise<void> {
    if (!this._state.active || !this._state.session) return;
    if (this._fullTrailPending) return;
    const t = Math.round(this._state.currentEpoch);
    if (Math.abs(t - this._lastTrailEpoch) < 5) return;

    const label = this._state.session.label;

    if (this._trailCacheEnd === 0 || t < this._trailCacheEnd) {
      this._fullTrailPending = true;
      try {
        const res = await fetch(
          `/api/surveillance/replay/${label}/trails?t=${t}&step=1`,
        );
        if (!res.ok) return;
        const data = await res.json();
        this._trailCache = data.trails || {};
        this._trailCacheEnd = t;
        this._lastTrailEpoch = t;
        for (const fn of this._trailListeners) fn(this._trailCache);
      } catch { /* non-fatal */ }
      this._fullTrailPending = false;
    } else {
      try {
        const res = await fetch(
          `/api/surveillance/replay/${label}/trails?t=${t}&t_start=${this._trailCacheEnd}&step=1`,
        );
        if (!res.ok) return;
        const data = await res.json();
        const delta: Record<string, number[][]> = data.trails || {};
        for (const [icao, pts] of Object.entries(delta)) {
          if (!this._trailCache[icao]) this._trailCache[icao] = [];
          this._trailCache[icao].push(...pts);
        }
        this._trailCacheEnd = t;
        this._lastTrailEpoch = t;
        for (const fn of this._trailListeners) fn(this._trailCache);
      } catch { /* non-fatal */ }
    }
  }
}

export const replayController = new ReplayController();
