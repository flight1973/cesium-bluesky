/** WebSocket client with topic-based event dispatching and auto-reconnect. */
import type { WsMessage, WsClientMessage, AcData, SimInfo, TrailData } from '../types';

type TopicHandler = (data: any) => void;

export class SimWebSocket {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<TopicHandler>>();
  private reconnectDelay = 1000;
  private maxReconnectDelay = 10000;
  private shouldConnect = false;

  constructor(private url: string) {}

  connect(): void {
    this.shouldConnect = true;
    this._connect();
  }

  disconnect(): void {
    this.shouldConnect = false;
    this.ws?.close();
    this.ws = null;
  }

  /** Subscribe to a topic and register a handler. */
  on(topic: string, handler: TopicHandler): void {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, new Set());
    }
    this.handlers.get(topic)!.add(handler);
  }

  /** Remove a handler for a topic. */
  off(topic: string, handler: TopicHandler): void {
    this.handlers.get(topic)?.delete(handler);
  }

  /** Send a command to the simulation via WebSocket. */
  sendCommand(command: string): void {
    this._send({ action: 'command', command });
  }

  /** Update topic subscriptions on the server. */
  subscribe(topics: string[]): void {
    this._send({ action: 'subscribe', topics });
  }

  private _send(msg: WsClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private _connect(): void {
    if (!this.shouldConnect) return;

    this.ws = new WebSocket(this.url);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.reconnectDelay = 1000;
      // Subscribe to all topics on connect
      this.subscribe([
        'ACDATA', 'SIMINFO', 'TRAILS', 'CMDLOG',
      ]);
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        // Messages come as binary (orjson bytes)
        const msg: WsMessage = typeof event.data === 'string'
          ? JSON.parse(event.data)
          : JSON.parse(new TextDecoder().decode(event.data));

        const handlers = this.handlers.get(msg.topic);
        if (handlers) {
          for (const handler of handlers) {
            handler(msg.data);
          }
        }
      } catch (e) {
        console.warn('[WS] Parse error:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('[WS] Disconnected');
      if (this.shouldConnect) {
        setTimeout(() => this._connect(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
      }
    };

    this.ws.onerror = (err) => {
      console.error('[WS] Error:', err);
    };
  }
}
