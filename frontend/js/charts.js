/* =====================================================================
   charts.js — Configuración de los gráficos dinámicos con Chart.js 4
   Un único punto de configuración de estilos para mantener el modo claro.
   ===================================================================== */
(function (global) {
  "use strict";

  const COLORS = {
    C1: "#0284c7",
    C2: "#0d9488",
    C3: "#7c3aed",
    feed: "#0f172a",
    grid: "rgba(148,163,184,.28)",
    tick: "#64748b",
  };

  if (!global.Chart) {
    console.error("Chart.js no disponible");
    return;
  }

  Chart.defaults.font.family = "Inter, system-ui, Segoe UI, Roboto, sans-serif";
  Chart.defaults.font.size = 10.5;
  Chart.defaults.color = COLORS.tick;
  Chart.defaults.animation = { duration: 260 };
  Chart.defaults.maintainAspectRatio = false;

  const baseScales = (yTitle, opts = {}) => ({
    x: {
      grid: { color: COLORS.grid, drawTicks: false },
      border: { color: "#e2e8f0" },
      ticks: { maxTicksLimit: 8, color: COLORS.tick },
    },
    y: {
      grid: { color: COLORS.grid, drawTicks: false },
      border: { color: "#e2e8f0" },
      ticks: { maxTicksLimit: 6, color: COLORS.tick },
      title: { display: true, text: yTitle, color: COLORS.tick, font: { size: 10, weight: "700" } },
      ...opts,
    },
  });

  const basePlugins = {
    legend: { display: false },
    tooltip: {
      backgroundColor: "rgba(15,23,42,.92)",
      titleFont: { size: 11, weight: "700" },
      bodyFont: { size: 11 },
      padding: 9,
      cornerRadius: 8,
      displayColors: true,
      boxWidth: 8,
      boxHeight: 8,
    },
  };

  const lineDataset = (label, color, extra = {}) => ({
    label,
    data: [],
    borderColor: color,
    backgroundColor: "transparent",
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.25,
    spanGaps: true,
    ...extra,
  });

  const dashDataset = (label, color) =>
    lineDataset(label, color, { borderDash: [5, 4], borderWidth: 1.6 });

  function make(canvasId, datasets, yTitle, yOpts = {}) {
    const el = document.getElementById(canvasId);
    if (!el) return null;
    return new Chart(el.getContext("2d"), {
      type: "line",
      data: { labels: [], datasets },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        plugins: basePlugins,
        scales: baseScales(yTitle, yOpts),
      },
    });
  }

  function buildCharts() {
    const charts = {};

    /* 1) Nivel SP vs PV (6 series) */
    charts.levels = make(
      "chartLevels",
      [
        lineDataset("C-1 PV", COLORS.C1),
        dashDataset("C-1 SP", COLORS.C1),
        lineDataset("C-2 PV", COLORS.C2),
        dashDataset("C-2 SP", COLORS.C2),
        lineDataset("C-3 PV", COLORS.C3),
        dashDataset("C-3 SP", COLORS.C3),
      ],
      "Nivel [mm]"
    );

    /* 2) RPM de bombas */
    charts.rpm = make(
      "chartRpm",
      [
        lineDataset("B-1 (C-1)", COLORS.C1),
        lineDataset("B-2 (C-2)", COLORS.C2),
        lineDataset("B-3 (C-3)", COLORS.C3),
      ],
      "RPM",
      { min: 0, suggestedMax: 220 }
    );

    /* 3) Caudal de alimentación */
    charts.feed = make(
      "chartFeed",
      [
        lineDataset("Q_feed medido", COLORS.feed, { borderWidth: 2.2, fill: true,
          backgroundColor: "rgba(15,23,42,.05)" }),
        dashDataset("Q_feed consigna", "#94a3b8"),
      ],
      "Q [L/min]"
    );

    /* 4) Reparto PI vs Feedforward */
    charts.ff = make(
      "chartFf",
      [
        lineDataset("FF · C-1", "#38bdf8"),
        lineDataset("PI · C-1", "#a855f7"),
        lineDataset("FF · C-2", "#2dd4bf"),
        lineDataset("PI · C-2", "#fb923c"),
      ],
      "RPM",
      { min: 0 }
    );

    /* 5) Error de control */
    charts.error = make(
      "chartError",
      [
        lineDataset("e C-1", COLORS.C1),
        lineDataset("e C-2", COLORS.C2),
        lineDataset("e C-3", COLORS.C3),
      ],
      "e [mm]"
    );

    Object.values(charts).forEach((c) => c && c.update("none"));
    return charts;
  }

  /* ------------------- utilidades de streaming ------------------- */
  function push(chart, label, values) {
    if (!chart) return;
    chart.data.labels.push(label);
    values.forEach((v, i) => {
      if (chart.data.datasets[i]) chart.data.datasets[i].data.push(v);
    });
  }

  function trim(chart, maxPoints) {
    if (!chart) return;
    const extra = chart.data.labels.length - maxPoints;
    if (extra <= 0) return;
    chart.data.labels.splice(0, extra);
    chart.data.datasets.forEach((ds) => ds.data.splice(0, extra));
  }

  global.CHARTS = { build: buildCharts, push, trim, COLORS };
})(window);
