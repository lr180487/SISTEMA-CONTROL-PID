/* =====================================================================
   app.js — Lógica del dashboard SCADA (modo claro, 5 s loader, 2 Hz)
   Funcionalidades 1..12 del requerimiento.
   ===================================================================== */
(function () {
  "use strict";

  const { API, createStream, CONTRACT, clampToRange } = window.SCADA;
  const CHARTS = window.CHARTS;

  const CELL_META = {
    C1: { label: "C-1", name: "Celda Rougher C-1", sub: "Alimentación · B-1", color: "#0284c7" },
    C2: { label: "C-2", name: "Celda Scavenger C-2", sub: "Intermedia · B-2", color: "#0d9488" },
    C3: { label: "C-3", name: "Celda Cleaner/Tail C-3", sub: "Descarga final · B-3", color: "#7c3aed" },
  };
  const CELL_IDS = ["C1", "C2", "C3"];
  const HZ = 2;                 // telemetría a 2 Hz (500 ms)
  let MAX_PORT = 350;           // RPM máximas bomba (hidratado desde /api/config)
  const LEVEL_MAX = 450;        // altura geométrica celda [mm]

  let charts = null;
  let stream = null;
  let windowSec = 120;
  let lastTelemetry = null;
  let lastRxAt = 0;
  let cardsBuilt = false;
  let chartsDirty = false;

  const history = [];
  const toastHost = document.getElementById("toastHost");

  /* ============================ utilidades ============================ */
  const $ = (id) => document.getElementById(id);
  const fmt = (v, d = 1) =>
    v === null || v === undefined || Number.isNaN(v) ? "--" : Number(v).toFixed(d);

  function toast(msg, kind = "") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = msg;
    toastHost.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  const ALARM_TXT = {
    NORMAL: "Normal",
    HIGH: "Alarma H (alta)",
    LOW: "Alarma L (baja)",
    HH_CRITICAL: "HH crítico",
    LL_CRITICAL: "LL crítico",
  };
  function alarmClass(s) {
    if (s === "NORMAL") return "badge-normal";
    if (s === "HIGH") return "badge-high";
    if (s === "LOW") return "badge-low";
    return "badge-critical";
  }

  /* ==================== 1) CONSTRUCCIÓN DE TARJETAS ==================== */
  function buildCards() {
    const grid = $("cellGrid");
    grid.innerHTML = "";

    CELL_IDS.forEach((cid) => {
      const m = CELL_META[cid];
      const card = document.createElement("article");
      card.className = "cell-card";
      card.id = `card-${cid}`;
      card.innerHTML = `
        <div class="cell-top">
          <div class="cell-id">
            <div class="cell-badge" style="background:${m.color}">${m.label}</div>
            <div>
              <div class="cell-name">${m.name}</div>
              <div class="cell-tag">${m.sub}</div>
            </div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <span class="badge ${alarmClass("NORMAL")}" data-alarm>Normal</span>
            <span class="badge badge-ff-on" data-ff>FF ON</span>
          </div>
        </div>
        <div class="cell-body">
          <div class="level-visual">
            <div class="tank" data-tank>
              <div class="tank-lo" data-tank-lo></div>
              <div class="tank-hi" data-tank-hi></div>
              <div class="tank-sp" data-tank-sp></div>
              <div class="tank-fill" data-fill></div>
            </div>
            <div class="level-read">
              <div>
                <div class="pv-line">
                  <span class="pv-value mono" data-pv>---.-</span>
                  <span class="pv-unit">mm</span>
                  <span class="pv-delta mono" data-delta>SP ---.-</span>
                </div>
                <div style="font-size:11px;color:#64748b;margin-top:3px">
                  Error <b class="mono" data-err>--</b> mm · IAE <b class="mono" data-iae>--</b>
                </div>
              </div>
              <div class="kv">
                <div><span>Q<sub>in</sub></span><strong class="mono" data-qin>--</strong></div>
                <div><span>Q<sub>out</sub></span><strong class="mono" data-qout>--</strong></div>
                <div><span>Q<sub>conc</sub></span><strong class="mono" data-qconc>--</strong></div>
                <div><span>Espuma</span><strong class="mono" data-froth>--</strong></div>
              </div>
              <div>
                <div style="display:flex;justify-content:space-between;font-size:10.5px;font-weight:700;color:#64748b;margin-bottom:3px">
                  <span>BOMBA PERISTÁLTICA</span>
                  <span class="mono" data-rpm>-- RPM</span>
                </div>
                <div class="rpm-bar"><i data-rpmbar style="width:0%;background:${m.color}"></i></div>
                <div style="display:flex;justify-content:space-between;font-size:10.5px;color:#64748b;margin-top:4px">
                  <span>FF <b class="mono" data-rpmff>--</b></span>
                  <span>PI <b class="mono" data-rpmpi>--</b></span>
                </div>
              </div>
            </div>
          </div>

          <div class="mode-toggle" data-modegroup>
            <button data-mode="MANUAL">MANUAL</button>
            <button data-mode="AUTO">AUTO</button>
          </div>

          <div class="ctrl-grid">
            <label class="field"><span>SP [mm]</span><input type="number" step="5" data-in="sp" /></label>
            <label class="field"><span>Kp [RPM/mm]</span><input type="number" step="0.1" data-in="kp" /></label>
            <label class="field"><span>Ki [RPM/(mm·s)]</span><input type="number" step="0.05" data-in="ki" /></label>
            <label class="field"><span>Kff [–]</span><input type="number" step="0.05" data-in="kff" /></label>
            <label class="field"><span>RPM manual</span><input type="number" step="5" data-in="manual_rpm" /></label>
            <label class="field"><span>Nivel AH/AB</span>
              <div style="display:flex;gap:4px">
                <input type="number" step="5" data-in="alarm_high" title="Umbral alarma alta" />
                <input type="number" step="5" data-in="alarm_low" title="Umbral alarma baja" />
              </div>
            </label>
          </div>

          <div class="cell-actions">
            <button class="btn btn-primary" data-apply>Guardar cambios</button>
            <button class="btn btn-light" data-toggle-ff>FF on/off</button>
          </div>
        </div>`;
      grid.appendChild(card);
    });

    /* Delegación de eventos por tarjeta */
    CELL_IDS.forEach((cid) => {
      const card = $(`card-${cid}`);

      card.querySelectorAll("[data-mode]").forEach((btn) => {
        btn.addEventListener("click", () => patchCell(cid, { mode: btn.dataset.mode }));
      });

      card.querySelector("[data-toggle-ff]").addEventListener("click", () => {
        const cell = lastTelemetry && lastTelemetry.cells[cid];
        patchCell(cid, { ff_enabled: !(cell ? cell.ff_enabled : true) });
      });

      card.querySelector("[data-apply]").addEventListener("click", () => {
        const payload = {};
        const invalid = [];
        card.querySelectorAll("[data-in]").forEach((inp) => {
          if (inp.value === "") return;
          const field = inp.dataset.in;
          const raw = Number(inp.value);
          const val = clampToRange(field, raw);
          if (val !== raw) invalid.push(`${field} → ${val}`);
          payload[field] = val;
        });
        if (invalid.length) toast(`Valores fuera de rango ajustados: ${invalid.join(", ")}`, "err");
        patchCell(cid, payload, "Configuración aplicada");
      });
    });

    cardsBuilt = true;
  }

  /* ============ 1.b) HIDRATACIÓN DESDE /api/config (sync) ============ */
  function applyServerConfig(cfg) {
    /* Alimentación */
    if (cfg.feed) {
      $("feedBase").value = cfg.feed.base_flow_lpm;
      $("feedProfile").value = cfg.feed.profile;
      $("feedNoise").value = cfg.feed.noise_std;
      $("feedAir").value = cfg.feed.air_flow_lpm;
    }
    /* PLC */
    if (cfg.plc) {
      $("plcIp").value = cfg.plc.ip;
      $("plcRack").value = cfg.plc.rack;
      $("plcSlot").value = cfg.plc.slot;
      $("plcDb").value = cfg.plc.db_number;
      $("plcMode").value = cfg.plc.mode;
      $("plcPoll").value = cfg.plc.poll_ms;
    }
    /* OPC UA */
    if (cfg.opcua) {
      $("opcEndpoint").value = cfg.opcua.endpoint;
      $("opcSecurity").value = cfg.opcua.security_policy;
      $("opcNs").value = cfg.opcua.namespace_index;
      $("opcPoll").value = cfg.opcua.poll_ms;
      $("opcTimeout").value = cfg.opcua.timeout_s;
      $("opcUser").value = cfg.opcua.username || "";
    }
    /* Celdas: SP, ganancias, umbrales y RPM manual */
    Object.entries(cfg.cells || {}).forEach(([cid, c]) => {
      const card = document.getElementById(`card-${cid}`);
      if (!card) return;
      card.querySelectorAll("[data-in]").forEach((inp) => {
        const v = c[inp.dataset.in];
        if (v === undefined || v === null) return;
        if (document.activeElement !== inp) inp.value = String(Number(Number(v).toFixed(3)));
      });
    });
    /* Límites de entrada tomados del contrato del backend */
    Object.entries((CONTRACT.ranges || {})).forEach(([field, [lo, hi]]) => {
      document.querySelectorAll(`[data-in="${field}"]`).forEach((inp) => {
        inp.min = lo; inp.max = hi;
      });
    });
    if (cfg.calibration) {
      MAX_PORT = cfg.calibration.rpm_max;
      $("footNote").innerHTML = `Modelo: 3 celdas 300×300×450 mm en serie · A<sub>eff</sub> = 0.078 L/mm · calibración α = ${cfg.calibration.alpha} L/(min·RPM) → ${cfg.calibration.max_flow_lpm} L/min máx`;
    }
  }

  function showSync(state, html) {
    const n = $("syncNotice");
    n.className = `sync-notice ${state}`;
    n.innerHTML = html;
    if (state === "ok") setTimeout(() => n.classList.add("hidden"), 6000);
  }

  async function syncContract() {
    try {
      const meta = await API.getMeta();
      const local = CONTRACT.schema_version || "—";
      $("footVersion").textContent = `esquema ${meta.schema_version} · app ${meta.app_version}`;

      if (meta.schema_version !== local) {
        showSync(
          "warn",
          `⚠ Esquema desincronizado: backend <code>${meta.schema_version}</code> vs frontend <code>${local}</code>. ` +
          `Ejecute <code>python3 tools/sync_contract.py</code> y recargue la página.`
        );
      } else {
        showSync("ok", `✔ Backend y frontend sincronizados (esquema <code>${local}</code>) · lazo a ${meta.simulation_hz} Hz`);
      }

      const cfg = await API.getConfig();
      applyServerConfig(cfg);
      return true;
    } catch (err) {
      showSync("err", `✖ Sin conexión con el backend (${err.message}). Operando en modo degradado con el último estado conocido.`);
      return false;
    }
  }

  /* ==================== 2) ACTUALIZACIÓN EN VIVO ==================== */
  function updateCards(tel) {
    CELL_IDS.forEach((cid) => {
      const card = $(`card-${cid}`);
      if (!card) return;
      const c = tel.cells[cid];
      const m = CELL_META[cid];

      const high = c.alarm_high;
      const low = c.alarm_low;
      const pct = (v) => Math.max(0, Math.min(100, (v / LEVEL_MAX) * 100));

      card.classList.toggle("is-alarm", c.alarm_status !== "NORMAL");

      const fill = card.querySelector("[data-fill]");
      fill.style.height = `${pct(c.pv)}%`;
      fill.style.background =
        c.alarm_status === "NORMAL"
          ? `linear-gradient(180deg, ${m.color}bb, ${m.color})`
          : c.alarm_status.includes("LOW")
          ? "linear-gradient(180deg,#fbbf24aa,#f59e0b)"
          : "linear-gradient(180deg,#f87171aa,#dc2626)";

      card.querySelector("[data-tank-sp]").style.bottom = `${pct(c.sp)}%`;
      card.querySelector("[data-tank-hi]").style.bottom = `${pct(high)}%`;
      card.querySelector("[data-tank-lo]").style.bottom = `${pct(low)}%`;

      card.querySelector("[data-pv]").textContent = fmt(c.pv, 1);
      card.querySelector("[data-delta]").textContent = `SP ${fmt(c.sp, 1)}`;
      card.querySelector("[data-err]").textContent = fmt(c.error, 1);
      card.querySelector("[data-iae]").textContent = fmt(c.iae, 0);
      card.querySelector("[data-qin]").textContent = `${fmt(c.q_in_lpm, 2)} L/min`;
      card.querySelector("[data-qout]").textContent = `${fmt(c.q_out_lpm, 2)} L/min`;
      card.querySelector("[data-qconc]").textContent = `${fmt(c.q_conc_lpm, 2)} L/min`;
      card.querySelector("[data-froth]").textContent = `${fmt(c.froth_depth_mm, 0)} mm`;
      card.querySelector("[data-rpm]").textContent = `${fmt(c.rpm, 0)} / ${MAX_PORT} RPM`;
      card.querySelector("[data-rpmbar]").style.width = `${Math.min(100, (c.rpm / MAX_PORT) * 100)}%`;
      card.querySelector("[data-rpmff]").textContent = fmt(c.rpm_ff, 0);
      card.querySelector("[data-rpmpi]").textContent = fmt(c.rpm_pi, 0);

      const alarmBadge = card.querySelector("[data-alarm]");
      alarmBadge.className = `badge ${alarmClass(c.alarm_status)}`;
      alarmBadge.textContent = ALARM_TXT[c.alarm_status] || c.alarm_status;

      const ffBadge = card.querySelector("[data-ff]");
      ffBadge.className = `badge ${c.ff_enabled ? "badge-ff-on" : "badge-ff-off"}`;
      ffBadge.textContent = c.ff_enabled ? "FF ON" : "FF OFF";

      card.querySelectorAll("[data-mode]").forEach((btn) => {
        btn.classList.remove("on-auto", "on-manual");
        if (btn.dataset.mode === c.mode) {
          btn.classList.add(c.mode === "AUTO" ? "on-auto" : "on-manual");
        }
      });

      /* Sincroniza entradas (incluida RPM manual) sin pisar lo que se escribe */
      card.querySelectorAll("[data-in]").forEach((inp) => {
        if (document.activeElement === inp) return;
        const val = c[inp.dataset.in];
        if (val === undefined || val === null) return;
        const next = String(Number(Number(val).toFixed(3)));
        if (inp.value !== next) inp.value = next;
      });
    });

    /* Cabecera */
    $("pillSim").innerHTML = tel.simulation_running
      ? '<i class="dot dot-ok"></i><span>Proceso activo</span>'
      : '<i class="dot dot-amber"></i><span>Proceso pausado</span>';

    $("pillPlc").innerHTML = tel.plc_connected
      ? `<i class="dot dot-ok"></i><span>PLC ${tel.plc_ip} en línea</span>`
      : `<i class="dot dot-gray"></i><span>${tel.plc_mode === "PLC_S7_1200" ? "PLC sin conexión" : "PLC: simulación"}</span>`;

    $("pillClock").textContent = tel.timestamp.split(" ")[1] || "--:--:--";

    /* Lecturas de simulación de caudal */
    $("roFeed").textContent = `${fmt(tel.q_feed_lpm, 2)} L/min`;
    $("roFeedSp").textContent = `${fmt(tel.q_feed_set_lpm, 2)} L/min`;
    $("roProfile").textContent = tel.feed_profile;
    const s = Math.floor(tel.elapsed_sec);
    $("roElapsed").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    $("tickHint").textContent = `t = ${fmt(tel.elapsed_sec, 0)} s · muestra cada 500 ms · última ${tel.timestamp.split(" ")[1]}`;

    updateOpcPill(tel);
    renderAlarms(tel.active_alarms || []);
  }

  /* ==================== 3) TENDENCIAS (Chart.js) ==================== */
  function resetCharts() {
    history.length = 0;
    if (!charts) return;
    Object.values(charts).forEach((ch) => {
      if (!ch) return;
      ch.data.labels = [];
      ch.data.datasets.forEach((ds) => (ds.data = []));
      ch.update("none");
    });
  }

  function pushTelemetry(tel) {
    history.push({
      t: tel.elapsed_sec,
      label: tel.timestamp.split(" ")[1],
      q: tel.q_feed_lpm,
      qsp: tel.q_feed_set_lpm,
      c: tel.cells,
    });
    if (history.length > 650) history.shift();
    chartsDirty = true;
  }

  function redrawCharts() {
    if (!charts || !history.length) return;
    const maxPoints = windowSec * HZ;
    const slice = history.slice(-maxPoints);
    const labels = slice.map((h) => h.label);
    const series = (fn) => slice.map(fn);

    const set = (chart, arrays) => {
      if (!chart) return;
      chart.data.labels = labels;
      arrays.forEach((arr, i) => {
        if (chart.data.datasets[i]) chart.data.datasets[i].data = arr;
      });
      chart.update("none");
    };

    set(charts.levels, [
      series((h) => h.c.C1.pv),
      series((h) => h.c.C1.sp),
      series((h) => h.c.C2.pv),
      series((h) => h.c.C2.sp),
      series((h) => h.c.C3.pv),
      series((h) => h.c.C3.sp),
    ]);
    set(charts.rpm, [
      series((h) => h.c.C1.rpm),
      series((h) => h.c.C2.rpm),
      series((h) => h.c.C3.rpm),
    ]);
    set(charts.feed, [series((h) => h.q), series((h) => h.qsp)]);
    set(charts.ff, [
      series((h) => h.c.C1.rpm_ff),
      series((h) => h.c.C1.rpm_pi),
      series((h) => h.c.C2.rpm_ff),
      series((h) => h.c.C2.rpm_pi),
    ]);
    set(charts.error, [
      series((h) => h.c.C1.error),
      series((h) => h.c.C2.error),
      series((h) => h.c.C3.error),
    ]);
    chartsDirty = false;
  }

  /* ==================== 4) ALARMAS (feature 9) ==================== */
  function renderAlarms(active) {
    const kpi = $("alarmSummary");
    const unacked = active.filter((a) => !a.acked).length;
    $("ackHint").textContent = `${unacked} sin reconocer`;
    $("btnAckAlarms").disabled = active.length === 0;
    const counts = { HIGH: 0, LOW: 0, CRITICAL: 0 };
    active.forEach((a) => {
      if (a.severity === "CRITICAL") counts.CRITICAL += 1;
      else if (a.type === "HIGH") counts.HIGH += 1;
      else if (a.type === "LOW") counts.LOW += 1;
    });
    kpi.innerHTML = `
      <div class="alarm-kpi"><span>Activas</span><strong style="color:${active.length ? "#dc2626" : "#16a34a"}">${active.length}</strong></div>
      <div class="alarm-kpi"><span>Alta (H)</span><strong>${counts.HIGH}</strong></div>
      <div class="alarm-kpi"><span>Baja (L)</span><strong>${counts.LOW}</strong></div>
      <div class="alarm-kpi"><span>Críticas</span><strong style="color:${counts.CRITICAL ? "#b91c1c" : "#0f172a"}">${counts.CRITICAL}</strong></div>`;

    const list = $("alarmList");
    if (!active.length) {
      list.innerHTML = '<p class="empty">Sin alarmas activas. Todos los niveles dentro de banda.</p>';
      return;
    }
    list.innerHTML = active
      .map(
        (a) => `
      <div class="alarm-row ${a.severity.toLowerCase()}${a.acked ? " acked" : ""}">
        <span class="a-cell" style="color:${CELL_META[a.cell_id] ? CELL_META[a.cell_id].color : "#dc2626"}">${a.cell_id}</span>
        <span class="a-msg">${a.message}</span>
        ${a.acked ? '<span class="a-ack">ACK</span>' : ""}
        <span class="a-time mono">${a.timestamp}</span>
      </div>`
      )
      .join("");
  }

  /* ==================== 5) ACCIONES SOBRE CELDAS ==================== */
  async function patchCell(cid, payload, okMsg) {
    try {
      const res = await API.updateCell(cid, payload);
      if (res && res.telemetry) {
        lastTelemetry = res.telemetry;
        updateCards(res.telemetry);
      }
      if (okMsg) toast(`${cid}: ${okMsg}`, "ok");
    } catch (err) {
      toast(`Error en ${cid}: ${err.message}`, "err");
    }
  }

  async function systemAction(action) {
    try {
      const res = await API.systemAction(action);
      toast(`Acción ejecutada: ${action}`, "ok");
      if (res && res.telemetry) {
        lastTelemetry = res.telemetry;
        updateCards(res.telemetry);
      }
      if (action === "RESET") {
        resetCharts();
        loadHistorian();
      }
      if (action.startsWith("ALL_")) syncContract();
    } catch (err) {
      toast(`Error: ${err.message}`, "err");
    }
  }

  /* ==================== 6) CAUDALES / HISTÓRICO / PLC ==================== */
  function feedPayload() {
    return {
      base_flow_lpm: Number($("feedBase").value),
      profile: $("feedProfile").value,
      noise_std: Number($("feedNoise").value),
      air_flow_lpm: Number($("feedAir").value),
    };
  }

  function plcPayload() {
    return {
      ip: $("plcIp").value.trim(),
      rack: Number($("plcRack").value),
      slot: Number($("plcSlot").value),
      db_number: Number($("plcDb").value),
      mode: $("plcMode").value,
      poll_ms: Number($("plcPoll").value),
    };
  }

  async function loadHistorian() {
    try {
      const data = await API.getHistorian(40);
      $("histCount").textContent = `${data.total_records} registros en SQLite`;
      const body = $("histTable").querySelector("tbody");
      if (!data.rows || !data.rows.length) {
        body.innerHTML = '<tr><td colspan="9" class="empty">El histórico está vacío. Reanude el proceso para registrar datos.</td></tr>';
        return;
      }
      /* Columnas: t [s], Q_feed, C-1 (SP/PV/RPM), C-2 (PV/RPM), C-3 (PV/RPM) */
      const cell = (v) => `<td>${typeof v === "number" ? Number(v.toFixed(2)) : v ?? "--"}</td>`;
      body.innerHTML = data.rows
        .map(
          (r) =>
            `<tr>${cell(r.elapsed_sec)}${cell(r.q_feed_lpm)}${cell(r.c1_sp)}${cell(r.c1_pv)}` +
            `${cell(r.c1_rpm)}${cell(r.c2_pv)}${cell(r.c2_rpm)}${cell(r.c3_pv)}${cell(r.c3_rpm)}</tr>`
        )
        .join("");
    } catch (err) {
      toast(`Histórico: ${err.message}`, "err");
    }
  }

  function exportCsv() {
    const a = document.createElement("a");
    a.href = "/api/historian/export.csv";
    a.download = "flotation_PI_FF_historian.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast("Exportación CSV solicitada", "ok");
  }

  async function loadPlcStatus() {
    try {
      const st = await API.getPlcStatus();
      const txt = st.connected
        ? `Estado: CONECTADO a ${st.ip} (DB${st.db_number}) · ping ${st.last_ping_ms ?? "--"} ms`
        : `Estado: ${st.mode === "PLC_S7_1200" ? "sin conexión física" : "modo SIMULACIÓN (gemelo hidráulico)"} · ${st.last_error || ""}`;
      $("plcStatusLine").textContent = txt;
      $("plcIp").value = st.ip;
      $("plcRack").value = st.rack;
      $("plcSlot").value = st.slot;
      $("plcDb").value = st.db_number;
      $("plcMode").value = st.mode;
      $("plcPoll").value = st.poll_ms;

      const tbody = $("tagMapTable").querySelector("tbody");
      if (tbody && !tbody.children.length) {
        tbody.innerHTML = (st.tag_map || [])
          .map((t) => `<tr><td>${t.offset}</td><td><b>${t.tag}</b></td><td>${t.type}</td><td>${t.rw}</td><td>${t.desc}</td></tr>`)
          .join("");
      }
    } catch (err) {
      $("plcStatusLine").textContent = `Estado: error de consulta (${err.message})`;
    }
  }

  async function showScl() {
    $("sclModal").classList.remove("hidden");
    try {
      const code = await API.getScl();
      $("sclCode").textContent = code;
    } catch (err) {
      $("sclCode").textContent = `// Error al cargar SCL: ${err.message}`;
    }
  }


  /* ==================== 12-bis) OPC UA (Ethernet :4840) ==================== */
  function opcPayload() {
    return {
      endpoint: $("opcEndpoint").value.trim(),
      security_policy: $("opcSecurity").value,
      username: $("opcUser").value.trim(),
      password: $("opcPass").value,
      namespace_index: Number($("opcNs").value),
      poll_ms: Number($("opcPoll").value),
      timeout_s: Number($("opcTimeout").value),
      active: true,
    };
  }

  function fmtValue(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "TRUE" : "FALSE";
    if (typeof v === "number") return Number(v.toFixed(2));
    return v;
  }

  function renderOpcTags(tags, connected) {
    const tbody = $("opcTagTable").querySelector("tbody");
    if (!tags || !tags.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">Conecte la sesión OPC UA para leer los nodos del PLC</td></tr>';
      return;
    }
    tbody.innerHTML = tags
      .map(
        (t) => `<tr>
          <td><b>${t.tag}</b></td>
          <td>${t.node_id}</td>
          <td>${t.type}</td>
          <td>${t.rw}</td>
          <td class="nv">${connected ? fmtValue(t.value) : "—"}</td>
        </tr>`
      )
      .join("");
  }

  function applyOpcStatus(st) {
    const ok = !!st.connected;
    $("opcStateBadge").className = `badge ${ok ? "badge-normal" : "badge-ff-off"}`;
    $("opcStateBadge").textContent = ok ? "OPC UA conectado" : "OPC UA desconectado";

    $("opcEndpoint").value = st.endpoint;
    $("opcSecurity").value = st.security_policy;
    $("opcNs").value = st.namespace_index;
    $("opcPoll").value = st.poll_ms;
    $("opcTimeout").value = st.timeout_s ?? 4;

    $("opcNodes").textContent = `${st.nodes_ok}/${st.nodes_total}`;
    $("opcLat").textContent = st.latency_ms === null || st.latency_ms === undefined ? "—" : `${st.latency_ms} ms`;
    $("opcPollAt").textContent = st.last_poll_at || "—";
    $("opcLatency").textContent = st.latency_ms === null || st.latency_ms === undefined ? "— ms" : `${st.latency_ms} ms`;
    $("opcSource").textContent = lastTelemetry ? lastTelemetry.plc_mode : "—";
    $("opcSourceBadge").textContent = `fuente: ${lastTelemetry ? lastTelemetry.plc_mode : "—"}`;

    $("opcStatusLine").textContent = ok
      ? `Estado: sesión activa con ${st.endpoint} · ${st.nodes_ok}/${st.nodes_total} nodos leídos · último ciclo ${st.last_poll_at || "—"}`
      : `Estado: sin sesión · ${st.last_error || "—"}`;

    renderOpcTags(st.tag_map, ok);
  }

  async function refreshOpcTestButton() {
    try {
      const st = await API.getOpcTestServer();
      $("btnOpcTest").textContent = st.running ? "Detener servidor de prueba" : "Servidor de prueba :4840";
      $("btnOpcTest").classList.toggle("btn-warn", !!st.running);
    } catch (_) { /* sin backend: se deja la etiqueta por defecto */ }
  }

  async function loadOpcStatus() {
    try {
      applyOpcStatus(await API.getOpcStatus());
    } catch (err) {
      $("opcStatusLine").textContent = `Estado: error de consulta (${err.message})`;
    }
  }

  /* Píldora de cabecera: se actualiza con cada trama de telemetría */
  function updateOpcPill(tel) {
    const pill = $("pillOpc");
    if (!tel.comm) return;
    const c = tel.comm;
    if (c.opcua_connected) {
      pill.innerHTML = `<i class="dot dot-ok"></i><span>OPC UA :4840 · ${c.opcua_nodes_ok}/${c.opcua_nodes_total} nodos</span>`;
    } else if (c.active_source === "OPC_UA") {
      pill.innerHTML = '<i class="dot dot-amber"></i><span>OPC UA sin sesión</span>';
    } else {
      pill.innerHTML = '<i class="dot dot-gray"></i><span>OPC UA: inactivo</span>';
    }
    $("opcSource").textContent = c.active_source;
    $("opcSourceBadge").textContent = `fuente: ${c.active_source}`;
  }

  /* ==================== 7) LOADER DE 5 SEGUNDOS ==================== */
  function runLoader() {
    const STEPS = [
      { p: 18, t: "Cargando gemelo hidráulico de 3 celdas…" },
      { p: 42, t: "Inicializando lazos PI + Feedforward por celda…" },
      { p: 68, t: "Abriendo histórico SQLite y canal WebSocket…" },
      { p: 88, t: "Verificando estado del PLC Siemens S7-1200…" },
      { p: 100, t: "Dashboard listo." },
    ];
    const bar = $("bootBar");
    const pctTxt = $("bootPct");
    const statusTxt = $("bootStatus");
    const TOTAL = 5000;
    const start = performance.now();
    let stepIdx = 0;

    function frame(now) {
      const p = Math.min(1, (now - start) / TOTAL);
      const pct = Math.round(p * 100);
      bar.style.width = `${pct}%`;
      pctTxt.textContent = pct;
      while (stepIdx < STEPS.length && pct >= STEPS[stepIdx].p) {
        statusTxt.textContent = STEPS[stepIdx].t;
        stepIdx += 1;
      }
      if (p < 1) {
        requestAnimationFrame(frame);
      } else {
        $("bootLoader").classList.add("done");
        $("app").classList.remove("hidden");
        setTimeout(() => {
          if (chartsDirty) redrawCharts();
        }, 120);
      }
    }
    requestAnimationFrame(frame);
  }

  /* ==================== 8) ARRANQUE ==================== */
  function bindEvents() {
    document.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => systemAction(btn.dataset.action));
    });

    document.querySelectorAll("[data-dist]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const delta = Number(btn.dataset.dist);
        try {
          const res = await API.disturbFeed(delta);
          toast(`Perturbación escalón aplicada: ${delta > 0 ? "+" : ""}${delta} L/min → Q_feed = ${res.base_flow_lpm} L/min`, "ok");
          $("feedBase").value = res.base_flow_lpm;
        } catch (err) {
          toast(`Error de perturbación: ${err.message}`, "err");
        }
      });
    });

    $("btnApplyFeed").addEventListener("click", async () => {
      try {
        await API.setFeed(feedPayload());
        toast("Configuración de caudales aplicada", "ok");
      } catch (err) {
        toast(`Error: ${err.message}`, "err");
      }
    });

    $("btnPlcConnect").addEventListener("click", async () => {
      try {
        const st = await API.connectPlc(plcPayload());
        toast(st.connected ? `PLC conectado (${st.ip})` : `Sin conexión: ${st.last_error}`, st.connected ? "ok" : "err");
        loadPlcStatus();
      } catch (err) {
        toast(`PLC: ${err.message}`, "err");
      }
    });

    $("btnPlcDisconnect").addEventListener("click", async () => {
      try {
        await API.disconnectPlc();
        toast("PLC desconectado", "ok");
        loadPlcStatus();
      } catch (err) {
        toast(`PLC: ${err.message}`, "err");
      }
    });

    $("plcMode").addEventListener("change", async () => {
      try {
        await API.setPlcConfig(plcPayload());
        loadPlcStatus();
      } catch (err) {
        toast(`PLC: ${err.message}`, "err");
      }
    });

    /* --- OPC UA --- */
    $("btnOpcConnect").addEventListener("click", async () => {
      const cfg = opcPayload();
      toast("Abriendo sesión OPC UA…");
      try {
        const st = await API.connectOpc(cfg);
        applyOpcStatus(st);
        toast(st.connected ? `OPC UA conectado · ${st.nodes_ok}/${st.nodes_total} nodos` : `Sin conexión: ${st.last_error}`,
              st.connected ? "ok" : "err");
      } catch (err) {
        toast(`OPC UA: ${err.message}`, "err");
      }
    });

    $("btnOpcDisconnect").addEventListener("click", async () => {
      try {
        applyOpcStatus(await API.disconnectOpc());
        toast("Sesión OPC UA cerrada", "ok");
      } catch (err) {
        toast(`OPC UA: ${err.message}`, "err");
      }
    });

    $("btnOpcBrowse").addEventListener("click", async () => {
      try {
        const res = await API.browseOpc();
        if (!res.connected) {
          toast(`Exploración no disponible: ${res.detail || "sin sesión"}`, "err");
          return;
        }
        toast(`Nodos encontrados en el PLC: ${res.nodes.length}`, "ok");
        const tbody = $("opcTagTable").querySelector("tbody");
        tbody.innerHTML = res.nodes
          .map((n) => `<tr><td><b>${n.name}</b></td><td>${n.node_id}</td><td>${n.type}</td><td>—</td><td class="nv">${fmtValue(n.value)}</td></tr>`)
          .join("");
      } catch (err) {
        toast(`Exploración: ${err.message}`, "err");
      }
    });

    $("btnOpcTest").addEventListener("click", async () => {
      const btn = $("btnOpcTest");
      btn.disabled = true;
      try {
        const st = await API.getOpcTestServer();
        if (st.running) {
          await API.stopOpcTestServer();
          toast("Servidor OPC UA de prueba detenido", "ok");
        } else {
          const res = await API.startOpcTestServer(4840);
          $("opcEndpoint").value = "opc.tcp://127.0.0.1:4840";
          if (res.namespace_index !== undefined) $("opcNs").value = res.namespace_index;
          toast(`Servidor de prueba activo en :4840 (${res.variables} variables). Pulse “Conectar OPC UA”.`, "ok");
        }
      } catch (err) {
        toast(`Servidor de prueba: ${err.message}`, "err");
      } finally {
        btn.disabled = false;
        refreshOpcTestButton();
      }
    });

    $("btnShowScl").addEventListener("click", showScl);
    $("btnCloseScl").addEventListener("click", () => $("sclModal").classList.add("hidden"));
    $("btnCopyScl").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("sclCode").textContent);
        toast("Código SCL copiado", "ok");
      } catch (err) {
        toast("No se pudo copiar (permisos del navegador)", "err");
      }
    });

    $("btnAckAlarms").addEventListener("click", async () => {
      try {
        const res = await API.ackAlarms(null);
        toast(`Alarmas reconocidas: ${res.acknowledged}`, "ok");
        if (res.telemetry) {
          lastTelemetry = res.telemetry;
          updateCards(res.telemetry);
        }
      } catch (err) {
        toast(`ACK: ${err.message}`, "err");
      }
    });

    $("btnRefreshHist").addEventListener("click", loadHistorian);
    $("btnExportCsv").addEventListener("click", exportCsv);
    $("btnClearHist").addEventListener("click", async () => {
      if (!confirm("¿Borrar todos los registros del histórico SQLite?")) return;
      try {
        await API.clearHistorian();
        toast("Histórico borrado", "ok");
        loadHistorian();
      } catch (err) {
        toast(`Error: ${err.message}`, "err");
      }
    });

    $("windowTabs").addEventListener("click", (ev) => {
      const btn = ev.target.closest(".tab");
      if (!btn) return;
      windowSec = Number(btn.dataset.window);
      document.querySelectorAll("#windowTabs .tab").forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      redrawCharts();
    });

    /* Refrescos periódicos de histórico y estado del PLC */
    setInterval(() => { if (chartsDirty) redrawCharts(); }, 2000);
    setInterval(loadHistorian, 15000);
    setInterval(loadPlcStatus, 10000);
    setInterval(loadOpcStatus, 5000);
    setInterval(refreshOpcTestButton, 8000);
  }

  function startStream() {
    stream = createStream({
      path: CONTRACT.ws_path || "/ws",
      onTelemetry: (tel) => {
        lastTelemetry = tel;
        lastRxAt = Date.now();
        if (!cardsBuilt) buildCards();
        updateCards(tel);
        pushTelemetry(tel);
      },
      onStatus: (state, text) => {
        const pill = $("pillWs");
        const cls = state === "open" ? "dot-ok" : state === "error" ? "dot-alarm" : "dot-amber";
        pill.innerHTML = `<i class="dot ${cls}"></i><span>${text}</span>`;
      },
    });
  }

  /* Respaldo: si el WebSocket no entrega datos, refresca por REST */
  function startPollingFallback() {
    setInterval(async () => {
      const gap = lastTelemetry ? Date.now() - lastRxAt : 99999;
      if (gap < 2500) return; // WebSocket saludable
      try {
        const tel = await API.getState();
        lastTelemetry = tel;
        lastRxAt = Date.now();
        if (!cardsBuilt) buildCards();
        updateCards(tel);
        pushTelemetry(tel);
        const pill = $("pillWs");
        pill.innerHTML = '<i class="dot dot-amber"></i><span>REST (respaldo) · sin WebSocket</span>';
      } catch (_) { /* backend caído: se mantiene el último estado */ }
    }, 3000);
  }

  async function init() {
    charts = CHARTS.build();
    buildCards();
    bindEvents();
    runLoader();
    await syncContract();       // hidratación y verificación de esquema ANTES de operar
    startStream();
    startPollingFallback();
    loadHistorian();
    loadPlcStatus();
    loadOpcStatus();
    refreshOpcTestButton();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
