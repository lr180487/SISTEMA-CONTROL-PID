/* =====================================================================
   api.js — Capa de comunicación REST + WebSocket con el backend FastAPI
   Todas las rutas son relativas: funcionan tanto en localhost como en el
   proxy de previsualización (/api/... y /ws).
   ===================================================================== */
(function (global) {
  "use strict";

  const BASE = ""; // rutas relativas

  async function request(path, options = {}) {
    const res = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ? JSON.stringify(body.detail) : detail;
      } catch (_) { /* respuesta sin cuerpo JSON */ }
      throw new Error(`${res.status} · ${detail}`);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
  }

  const API = {
    /* --- contrato / sincronización --- */
    getMeta: () => request("/api/meta"),
    getHealth: () => request("/api/health"),
    getConfig: () => request("/api/config"),
    patchConfig: (payload) => request("/api/config", { method: "PATCH", body: JSON.stringify(payload) }),
    ackAlarms: (cellId = null) =>
      request("/api/alarms/ack", { method: "POST", body: JSON.stringify({ cell_id: cellId }) }),

    /* --- proceso --- */
    getState: () => request("/api/state"),
    updateCell: (cellId, payload) =>
      request(`/api/cells/${cellId}`, { method: "POST", body: JSON.stringify(payload) }),
    setFeed: (cfg) => request("/api/feed", { method: "POST", body: JSON.stringify(cfg) }),
    disturbFeed: (delta) =>
      request("/api/feed/disturbance", { method: "POST", body: JSON.stringify({ delta_lpm: delta }) }),
    systemAction: (action) =>
      request("/api/system/action", { method: "POST", body: JSON.stringify({ action }) }),
    getAlarms: () => request("/api/alarms"),
    getHistorian: (limit = 40) => request(`/api/historian/recent?limit=${limit}`),
    clearHistorian: () => request("/api/historian", { method: "DELETE" }),
    getPlcStatus: () => request("/api/plc/status"),
    setPlcConfig: (cfg) => request("/api/plc/config", { method: "POST", body: JSON.stringify(cfg) }),
    connectPlc: (cfg) => request("/api/plc/connect", { method: "POST", body: JSON.stringify(cfg) }),
    disconnectPlc: () => request("/api/plc/disconnect", { method: "POST" }),
    getScl: () => request("/api/plc/scl"),

    /* --- OPC UA (Ethernet / PROFINET :4840) --- */
    getOpcStatus: () => request("/api/opcua/status"),
    setOpcConfig: (cfg) => request("/api/opcua/config", { method: "POST", body: JSON.stringify(cfg) }),
    connectOpc: (cfg) => request("/api/opcua/connect", { method: "POST", body: JSON.stringify(cfg) }),
    disconnectOpc: () => request("/api/opcua/disconnect", { method: "POST" }),
    getOpcTags: () => request("/api/opcua/tags"),
    browseOpc: () => request("/api/opcua/browse"),
    writeOpcTag: (tag, value) =>
      request("/api/opcua/write", { method: "POST", body: JSON.stringify({ tag, value }) }),
    startOpcTestServer: (port = 4840) =>
      request("/api/opcua/test-server/start", { method: "POST", body: JSON.stringify({ port }) }),
    stopOpcTestServer: () => request("/api/opcua/test-server/stop", { method: "POST" }),
    getOpcTestServer: () => request("/api/opcua/test-server/status"),
  };

  /* ------------------- WebSocket con reconexión ------------------- */
  function createStream({ onTelemetry, onStatus, path = "/ws", retryMs = 2000 }) {
    let ws = null;
    let retryTimer = null;
    let closedByUser = false;

    function url() {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${location.host}${path}`;
    }

    function emitStatus(state, text) {
      if (typeof onStatus === "function") onStatus(state, text);
    }

    function connect() {
      emitStatus("connecting", "Conectando al WebSocket…");
      try {
        ws = new WebSocket(url());
      } catch (err) {
        scheduleRetry();
        return;
      }

      ws.onopen = () => {
        emitStatus("open", "WebSocket en línea · flujo 2 Hz");
        try { ws.send("SCADA_DASHBOARD_CLIENT"); } catch (_) {}
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (onTelemetry) onTelemetry(data);
        } catch (err) { /* mensaje no JSON: ignorar */ }
      };
      ws.onerror = () => emitStatus("error", "Error de WebSocket · reintentando");
      ws.onclose = () => {
        emitStatus("closed", "WebSocket desconectado · reintentando");
        if (!closedByUser) scheduleRetry();
      };
    }

    function scheduleRetry() {
      clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, retryMs);
    }

    connect();

    return {
      close() {
        closedByUser = true;
        clearTimeout(retryTimer);
        if (ws) ws.close();
      },
      get socket() { return ws; },
    };
  }

  /* ------------------- utilidades de contrato ------------------- */
  const CONTRACT = global.CONTRACT || {};

  /** Ajusta un valor numérico a los rangos validados por Pydantic. */
  function clampToRange(field, value) {
    const r = (CONTRACT.ranges || {})[field];
    const v = Number(value);
    if (!r || Number.isNaN(v)) return v;
    return Math.min(r[1], Math.max(r[0], v));
  }

  /** Verifica que una clave exista en el modelo declarado por el backend. */
  function hasField(model, field) {
    const fields = (CONTRACT.models || {})[model];
    return Array.isArray(fields) ? fields.includes(field) : true;
  }

  global.SCADA = { API, createStream, CONTRACT, clampToRange, hasField };
})(window);
