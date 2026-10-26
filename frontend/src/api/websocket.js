import { WS_BASE } from "../utils/constants";

export class LiveSocket {
  constructor({ onEvent, onAlert, onStatus, onConnection, onError }) {
    this.onEvent = onEvent;
    this.onAlert = onAlert;
    this.onStatus = onStatus;
    this.onConnection = onConnection;
    this.onError = onError;
    this.ws = null;
    this.shouldRun = false;
    this.retryMs = 1000;
    this.maxRetryMs = 10000;
    this.pingTimer = null;
    this.retryTimer = null;
  }

  connect() {
    this.shouldRun = true;
    this._open();
  }

  disconnect() {
    this.shouldRun = false;
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    const ws = this.ws;
    this.ws = null;
    if (ws && ws.readyState < WebSocket.CLOSING) {
      ws.close();
    }
    this.onConnection?.("Disconnected");
    this.onError?.(null);
  }

  _open() {
    if (!this.shouldRun) return;
    this.onConnection?.("Reconnecting");

    let ws;
    try {
      ws = new WebSocket(`${WS_BASE}/ws/events`);
    } catch (error) {
      this.onError?.(`Unable to open the live event stream: ${error.message || "connection failed"}`);
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      if (ws !== this.ws || !this.shouldRun) return;
      this.retryMs = 1000;
      this.onConnection?.("Connected");
      this.onError?.(null);
      if (this.pingTimer) clearInterval(this.pingTimer);
      this.pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send("ping");
          } catch {
            ws.close();
          }
        }
      }, 15000);
    };

    ws.onmessage = (msg) => {
      if (ws !== this.ws || !this.shouldRun) return;
      try {
        const payload = JSON.parse(msg.data);
        if (!payload || typeof payload !== "object" || typeof payload.type !== "string") {
          throw new Error("message is missing its type");
        }
        if (payload.type === "pong" || payload.type === "connected") return;
        if (payload.type === "event" && payload.data && typeof payload.data === "object") {
          this.onEvent?.(payload.data);
          return;
        }
        if (payload.type === "alert" && payload.data && typeof payload.data === "object") {
          this.onAlert?.(payload.data);
          return;
        }
        if (payload.type === "simulation_status" && payload.data && typeof payload.data === "object") {
          this.onStatus?.(payload.data);
          return;
        }
        if (payload.type === "stats_refresh") {
          this.onStatus?.({ refresh: true });
          return;
        }
        throw new Error(`unsupported or invalid message type "${payload.type}"`);
      } catch (error) {
        this.onError?.(`Live event stream message error: ${error.message || "invalid JSON"}`);
      }
    };

    ws.onclose = () => {
      if (ws !== this.ws) return;
      this.ws = null;
      if (this.pingTimer) clearInterval(this.pingTimer);
      if (!this.shouldRun) {
        this.onConnection?.("Disconnected");
        return;
      }
      this.onError?.("Live event stream disconnected; reconnecting.");
      this._scheduleReconnect();
    };

    ws.onerror = () => {
      if (ws !== this.ws) return;
      this.onError?.("Unable to communicate with the live event stream; reconnecting.");
      ws.close();
    };
  }

  _scheduleReconnect() {
    if (!this.shouldRun) return;
    this.onConnection?.("Reconnecting");
    if (this.retryTimer) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this._open();
      this.retryMs = Math.min(this.retryMs * 1.7, this.maxRetryMs);
    }, this.retryMs);
  }
}
