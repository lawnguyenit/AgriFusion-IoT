import { initializeApp } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-app.js";
import {
  getDatabase,
  get,
  onChildAdded,
  onValue,
  ref,
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-database.js";

await Promise.resolve(window.AgriFusionDashboardConfigReady);

const dashboardConfig = window.AgriFusionDashboardConfig || {};

const RANGE_PRESETS = [
  { id: "3h", label: "3 giờ", hours: 3 },
  { id: "6h", label: "6 giờ", hours: 6 },
  { id: "12h", label: "12 giờ", hours: 12 },
  { id: "24h", label: "24 giờ", hours: 24 },
  { id: "7d", label: "7 ngày", hours: 24 * 7 },
  { id: "30d", label: "30 ngày", hours: 24 * 30 },
  { id: "all", label: "Từ đầu đến nay", hours: null },
];

const HISTORY_GROUPS = ["air", "soil", "npk", "weather"];
const VIEW_DEBOUNCE_MS = 180;
const LIVE_GRACE_SECONDS = 20 * 60;
const SNAPSHOT_POINT_LIMIT = 10;
const MIN_PRESET_CONTEXT_POINTS = 6;
const BOOTSTRAP_TIMEOUT_MS = 3500;

const METRIC_DEFS = [
  {
    id: "air_temperature",
    label: "Nhiệt độ không khí",
    shortLabel: "Nhiệt độ KK",
    unit: "°C",
    color: "#d6a33b",
    historyKey: "air",
    metricKey: "temperature_c",
    axisId: "left",
  },
  {
    id: "air_humidity",
    label: "Độ ẩm không khí",
    shortLabel: "Độ ẩm KK",
    unit: "%",
    color: "#2f8f83",
    historyKey: "air",
    metricKey: "humidity_pct",
    axisId: "right",
  },
  {
    id: "soil_temperature",
    label: "Nhiệt độ đất",
    shortLabel: "Nhiệt độ đất",
    unit: "°C",
    color: "#cf7243",
    historyKey: "soil",
    metricKey: "temperature_c",
    axisId: "left",
  },
  {
    id: "soil_humidity",
    label: "Độ ẩm đất",
    shortLabel: "Độ ẩm đất",
    unit: "%",
    color: "#4d95bf",
    historyKey: "soil",
    metricKey: "humidity_pct",
    axisId: "right",
  },
  {
    id: "soil_ph",
    label: "pH đất",
    shortLabel: "pH đất",
    unit: "pH",
    color: "#7e9946",
    historyKey: "soil",
    metricKey: "ph",
    axisId: "left",
  },
  {
    id: "soil_ec",
    label: "EC đất",
    shortLabel: "EC đất",
    unit: "uS/cm",
    color: "#b35f70",
    historyKey: "soil",
    metricKey: "ec_us_cm",
    axisId: "right",
  },
  {
    id: "npk_n",
    label: "Nitơ",
    shortLabel: "N",
    unit: "ppm",
    color: "#719d4b",
    historyKey: "npk",
    metricKey: "n_ppm",
    axisId: "left",
  },
  {
    id: "npk_p",
    label: "Phốt pho",
    shortLabel: "P",
    unit: "ppm",
    color: "#e0aa39",
    historyKey: "npk",
    metricKey: "p_ppm",
    axisId: "left",
  },
  {
    id: "npk_k",
    label: "Kali",
    shortLabel: "K",
    unit: "ppm",
    color: "#d97b48",
    historyKey: "npk",
    metricKey: "k_ppm",
    axisId: "left",
  },
];

const GROUP_DEFS = [
  {
    id: "overview",
    label: "Tổng quan",
    description: "So sánh toàn bộ thông số để nhìn nhịp thay đổi chung của hệ thống.",
    metricIds: METRIC_DEFS.map((metric) => metric.id),
    mode: "overview",
    forceNormalized: true,
  },
  {
    id: "air",
    label: "Không khí",
    description: "Nhiệt độ và độ ẩm không khí trong cùng một khung nhìn.",
    metricIds: ["air_temperature", "air_humidity"],
    axes: {
      left: { label: "Nhiệt độ", unit: "°C" },
      right: { label: "Độ ẩm", unit: "%" },
    },
  },
  {
    id: "soil",
    label: "Đất",
    description: "Nhiệt độ đất và độ ẩm đất để theo dõi nền môi trường canh tác.",
    metricIds: ["soil_temperature", "soil_humidity"],
    axes: {
      left: { label: "Nhiệt độ", unit: "°C" },
      right: { label: "Độ ẩm", unit: "%" },
    },
  },
  {
    id: "chemistry",
    label: "pH & EC đất",
    description: "Các chỉ số hóa học đất cần được nhìn bằng trị số thật thay vì ép chung một thang đo.",
    metricIds: ["soil_ph", "soil_ec"],
    axes: {
      left: { label: "pH", unit: "pH" },
      right: { label: "EC", unit: "uS/cm" },
    },
  },
  {
    id: "npk",
    label: "NPK",
    description: "Ba thành phần dinh dưỡng chính dùng chung một đơn vị ppm.",
    metricIds: ["npk_n", "npk_p", "npk_k"],
    axes: {
      left: { label: "NPK", unit: "ppm" },
      right: null,
    },
  },
];

const PIPELINE_STATES = {
  live_syncing: {
    key: "live_syncing",
    label: "Live Syncing",
    tone: "live",
    detail: "Đang đồng bộ trực tiếp từ MQTT/WebSocket hoặc RTDB.",
  },
  awaiting_analysis: {
    key: "awaiting_analysis",
    label: "Awaiting Server Analysis",
    tone: "awaiting",
    detail: "Dữ liệu đã thu thập nhưng còn chờ server phân tích hoặc publish dự báo.",
  },
  historical_view: {
    key: "historical_view",
    label: "Historical View",
    tone: "historical",
    detail: "Bạn đang xem lát cắt lịch sử, không bám realtime tại thời điểm hiện tại.",
  },
  offline_error: {
    key: "offline_error",
    label: "Offline / Error",
    tone: "offline",
    detail: "Mất kết nối với node xử lý hoặc cơ sở dữ liệu thời gian thực.",
  },
  demo: {
    key: "demo",
    label: "Dữ liệu tạm thời",
    tone: "historical",
    detail: "Đang hiển thị dữ liệu mẫu nội bộ, chưa phải feed từ server.",
  },
};

const metricMap = Object.fromEntries(METRIC_DEFS.map((metric) => [metric.id, metric]));
const groupMap = Object.fromEntries(GROUP_DEFS.map((group) => [group.id, group]));

const state = {
  rangePresetId: dashboardConfig.defaultRange || "24h",
  rangeMode: "preset",
  customStart: "",
  customEnd: "",
  selectedGroupId: dashboardConfig.defaultGroup || "air",
  scaleMode: "absolute",
  sideView: "summary",
  mode: "demo",
  connected: false,
  connectionDetail: "Đang chờ dữ liệu đầu tiên.",
  data: createEmptyResult(),
  historyIndex: createHistoryMaps(),
  pendingHistory: createHistoryMaps(),
  renderQueued: false,
  historyFlushQueued: false,
  viewDebounceId: 0,
};

const demoResult = buildSampleResult();

boot();

function boot() {
  renderGroupSelector();
  bindScaleButtons();
  bindRangeButtons();
  bindDateRangeControls();
  bindSideViewButtons();
  syncRangeButtons();
  syncScaleButtons();
  syncGroupButtons();
  syncSideViewButtons();

  const mode = dashboardConfig.mode || "auto";
  const firebaseReady = hasFirebaseConfig(dashboardConfig.firebase);

  if (mode === "demo") {
    applySnapshot(
      demoResult,
      "demo",
      "Đang hiển thị dữ liệu mẫu trong lúc chờ nguồn chính."
    );
    return;
  }

  if (!firebaseReady) {
    applySnapshot(
      demoResult,
      "demo",
      "Chưa có cấu hình Firebase hợp lệ, hệ thống tạm dùng dữ liệu mẫu."
    );
    return;
  }

  connectFirebase().catch((error) => {
    console.error("Firebase init error", error);
    applySnapshot(
      demoResult,
      "demo",
      "Không kết nối được nguồn dữ liệu trực tiếp, hệ thống tạm dùng dữ liệu mẫu."
    );
  });
}

async function connectFirebase() {
  state.mode = "firebase";
  state.connectionDetail = "Đang kết nối tới nguồn dữ liệu trực tiếp.";
  scheduleRender();

  const app = initializeApp(dashboardConfig.firebase);
  const db = getDatabase(app);
  const resultPath = dashboardConfig.resultPath || "result";

  onValue(ref(db, ".info/connected"), (snapshot) => {
    state.connected = Boolean(snapshot.val());
    state.connectionDetail = state.connected
      ? "Kết nối ổn định, dashboard sẽ tự nhận bản ghi mới khi server publish."
      : "Mất kết nối tạm thời, hệ thống sẽ tự đồng bộ lại khi có mạng.";
    scheduleRender();
  });

  const snapshot = await Promise.race([
    get(ref(db, resultPath)),
    new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error("bootstrap-timeout")), BOOTSTRAP_TIMEOUT_MS);
    }),
  ]);
  if (!snapshot.exists()) {
    applySnapshot(
      demoResult,
      "demo",
      "Chưa tìm thấy dữ liệu đã publish từ server, đang hiển thị dữ liệu mẫu."
    );
    return;
  }

  applySnapshot(
    normalizeResultSnapshot(snapshot.val()),
    "firebase",
    "Đã nhận được dữ liệu trực tiếp từ hệ thống."
  );

  attachRealtimeListeners(db, resultPath);
}

function attachRealtimeListeners(db, resultPath) {
  onValue(ref(db, `${resultPath}/meta`), (snapshot) => {
    if (!snapshot.exists()) return;
    state.data.meta = {
      ...state.data.meta,
      ...normalizeMeta(snapshot.val()),
    };
    scheduleRender();
  });

  onValue(ref(db, `${resultPath}/latest`), (snapshot) => {
    if (!snapshot.exists()) return;
    state.data.latest = normalizeLatest(snapshot.val(), state.data.history);
    scheduleRender();
  });

  onValue(ref(db, `${resultPath}/pipeline`), (snapshot) => {
    state.data.pipeline = normalizePipeline(snapshot.val());
    scheduleRender();
  });

  onValue(ref(db, `${resultPath}/analysis`), (snapshot) => {
    state.data.analysis = normalizeAnalysis(snapshot.val());
    scheduleRender();
  });

  onValue(ref(db, `${resultPath}/recommendations`), (snapshot) => {
    state.data.analysis.recommendations = normalizeRecommendations(snapshot.val());
    scheduleRender();
  });

  onValue(ref(db, `${resultPath}/anomalies`), (snapshot) => {
    state.data.analysis.anomalies = normalizeAnomalies(snapshot.val());
    scheduleRender();
  });

  for (const group of HISTORY_GROUPS) {
    onChildAdded(ref(db, `${resultPath}/history/${group}`), (snapshot) => {
      if (!snapshot.key) return;
      queueHistoryRecord(group, snapshot.key, snapshot.val());
    });

    onChildAdded(ref(db, `${resultPath}/analysis/forecast/${group}`), (snapshot) => {
      if (!snapshot.key) return;
      queueForecastRecord(group, snapshot.key, snapshot.val());
    });
  }
}

function applySnapshot(snapshot, mode, detail) {
  state.mode = mode;
  state.connectionDetail = detail;
  state.data = normalizeResultSnapshot(snapshot);
  state.historyIndex = createHistoryMaps();
  state.pendingHistory = createHistoryMaps();

  for (const group of HISTORY_GROUPS) {
    for (const record of state.data.history[group]) {
      state.historyIndex[group].set(record.ts, record);
    }
  }

  if (mode !== "firebase") {
    state.connected = false;
  }

  scheduleRender();
}

function queueHistoryRecord(group, key, payload) {
  const record = normalizeHistoryRecord(payload, key);
  if (!record) return;
  state.pendingHistory[group].set(record.ts, record);
  flushPendingHistory();
}

function queueForecastRecord(group, key, payload) {
  const record = normalizeHistoryRecord(payload, key);
  if (!record) return;
  const index = state.data.analysis.forecast[group];
  const existingIndex = index.findIndex((item) => item.ts === record.ts);

  if (existingIndex >= 0) {
    index[existingIndex] = record;
  } else {
    index.push(record);
    index.sort((left, right) => left.ts - right.ts);
  }

  scheduleRender();
}

function flushPendingHistory() {
  if (state.historyFlushQueued) return;
  state.historyFlushQueued = true;

  window.requestAnimationFrame(() => {
    state.historyFlushQueued = false;

    for (const historyGroup of HISTORY_GROUPS) {
      for (const [ts, item] of state.pendingHistory[historyGroup].entries()) {
        state.historyIndex[historyGroup].set(ts, item);
      }

      state.pendingHistory[historyGroup].clear();
      state.data.history[historyGroup] = Array.from(
        state.historyIndex[historyGroup].values()
      ).sort((left, right) => left.ts - right.ts);
    }

    state.data.latest = normalizeLatest(state.data.latest, state.data.history);
    scheduleRender();
  });
}

function renderGroupSelector() {
  const selector = document.getElementById("groupSelector");
  if (!selector) return;

  selector.innerHTML = GROUP_DEFS.map((group) => `
    <button
      class="chip-btn ${group.id === state.selectedGroupId ? "is-active" : ""}"
      type="button"
      data-group-id="${escapeHtml(group.id)}"
    >
      ${escapeHtml(group.label)}
    </button>
  `).join("");

  selector.querySelectorAll("[data-group-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedGroupId = button.dataset.groupId || "air";
      syncGroupButtons();
      syncScaleButtons();
      queueViewportRender();
    });
  });
}

function bindScaleButtons() {
  document.querySelectorAll("[data-scale-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextMode = button.dataset.scaleMode || "absolute";
      if (nextMode === state.scaleMode) return;
      state.scaleMode = nextMode;
      syncScaleButtons();
      queueViewportRender();
    });
  });
}

function bindRangeButtons() {
  document.querySelectorAll("[data-range]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      state.rangePresetId = button.dataset.range || "24h";
      state.rangeMode = "preset";
      syncRangeButtons();
      queueViewportRender();
    });
  });
}

function bindDateRangeControls() {
  const startInput = document.getElementById("rangeStartInput");
  const endInput = document.getElementById("rangeEndInput");
  const applyButton = document.getElementById("applyDateRangeButton");
  const clearButton = document.getElementById("clearDateRangeButton");

  if (!startInput || !endInput || !applyButton || !clearButton) return;

  const syncDraft = () => {
    state.customStart = startInput.value;
    state.customEnd = endInput.value;
    syncDateRangeButtons();
  };

  startInput.addEventListener("change", syncDraft);
  endInput.addEventListener("change", syncDraft);

  applyButton.addEventListener("click", () => {
    if (!isCustomRangeValid()) return;
    state.rangeMode = "custom";
    queueViewportRender();
  });

  clearButton.addEventListener("click", () => {
    state.customStart = "";
    state.customEnd = "";
    startInput.value = "";
    endInput.value = "";
    state.rangeMode = "preset";
    syncDateRangeButtons();
    queueViewportRender();
  });
}

function bindSideViewButtons() {
  document.querySelectorAll("[data-side-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.sideView = button.dataset.sideView || "summary";
      syncSideViewButtons();
      queueViewportRender();
    });
  });
}

function queueViewportRender() {
  if (state.viewDebounceId) {
    window.clearTimeout(state.viewDebounceId);
  }

  state.viewDebounceId = window.setTimeout(() => {
    state.viewDebounceId = 0;
    scheduleRender();
  }, VIEW_DEBOUNCE_MS);
}

function syncRangeButtons() {
  document.querySelectorAll("[data-range]").forEach((button) => {
    const presetId = button.dataset.range || "";
    button.classList.toggle(
      "is-active",
      state.rangeMode === "preset" && presetId === state.rangePresetId
    );
  });
}

function syncGroupButtons() {
  document.querySelectorAll("[data-group-id]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      button.dataset.groupId === state.selectedGroupId
    );
  });
}

function syncScaleButtons() {
  const group = getSelectedGroup();
  const forcedNormalized = Boolean(group.forceNormalized);

  document.querySelectorAll("[data-scale-mode]").forEach((button) => {
    const buttonMode = button.dataset.scaleMode || "absolute";
    const isDisabled = forcedNormalized && buttonMode === "absolute";
    button.disabled = isDisabled;
    button.classList.toggle(
      "is-active",
      forcedNormalized ? buttonMode === "normalized" : buttonMode === state.scaleMode
    );
  });
}

function syncSideViewButtons() {
  document.querySelectorAll("[data-side-view]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      button.dataset.sideView === state.sideView
    );
  });
}

function syncDateRangeButtons() {
  const applyButton = document.getElementById("applyDateRangeButton");
  const clearButton = document.getElementById("clearDateRangeButton");
  if (!applyButton || !clearButton) return;

  applyButton.disabled = !isCustomRangeValid();
  clearButton.disabled = !state.customStart && !state.customEnd;
}

function scheduleRender() {
  if (state.renderQueued) return;
  state.renderQueued = true;

  window.requestAnimationFrame(() => {
    state.renderQueued = false;
    renderDashboard();
  });
}

function renderDashboard() {
  const globalBounds = getGlobalBounds();
  ensurePresetStillValid(globalBounds);
  syncPresetAvailability(globalBounds);
  syncDateInputs(globalBounds);
  syncDateRangeButtons();
  syncRangeButtons();
  syncScaleButtons();

  const historicalBounds = getHistoricalBounds();
  const chartModel = buildChartModel(historicalBounds);
  const pipelineState = derivePipelineState(historicalBounds, chartModel);

  renderPipelineState(pipelineState, historicalBounds);
  renderMainChart(chartModel);
  renderSummaryView(chartModel);
  renderSnapshotView(globalBounds);
  renderPredictionViewModern(chartModel);
  renderSideViews();
}

function buildChartModel(historicalBounds) {
  const group = getSelectedGroup();
  const resolvedScaleMode = group.forceNormalized ? "normalized" : state.scaleMode;
  const chartMode = state.sideView;
  const effectiveBounds = chartMode === "snapshot"
    ? getSnapshotBounds(historicalBounds, group)
    : historicalBounds;

  const baseSeries = group.metricIds
    .map((metricId) => buildSeries(metricMap[metricId], effectiveBounds, chartMode))
    .filter(Boolean);

  const activeSeries = baseSeries.filter(
    (series) => series.historyPoints.length || series.forecastPoints.length
  );

  const xBounds = getChartXBounds(activeSeries, effectiveBounds, chartMode);
  const anomalyCount = activeSeries.reduce((sum, series) => sum + series.anomalies.length, 0);
  const pointCount = Math.max(
    0,
    ...activeSeries.map((series) => series.historyPoints.length)
  );
  const hasForecast = activeSeries.some((series) => series.forecastPoints.length > 0);
  const forecastHorizonSec = getForecastHorizon(activeSeries, effectiveBounds.maxTs);

  const axisExtents = getAxisExtents(group, activeSeries, resolvedScaleMode);
  const renderedSeries = activeSeries.map((series) =>
    projectSeriesForChart(series, axisExtents, xBounds, resolvedScaleMode)
  );

  return {
    group,
    chartMode,
    scaleMode: resolvedScaleMode,
    requestedScaleMode: state.scaleMode,
    historicalBounds: effectiveBounds,
    xBounds,
    axisExtents,
    series: renderedSeries,
    pointCount,
    anomalyCount,
    hasForecast,
    forecastHorizonSec,
  };
}

function buildSeries(metric, bounds, chartMode) {
  if (!metric) return null;

  const historyPoints = getRecordsForMetric(metric, bounds)
    .map((record) => ({
      ts: record.ts,
      value: toNumber(record[metric.metricKey]),
    }))
    .filter((point) => point.value !== null);

  let forecastPoints = [];
  if (chartMode === "prediction") {
    forecastPoints = getForecastRecordsForMetric(metric)
      .map((record) => extractForecastPoint(record, metric))
      .filter((point) => point && point.ts >= (bounds.maxTs || 0) && point.value !== null);
  }

  const anomalies = getAnomaliesForMetric(metric, bounds, forecastPoints);
  const stats = summarizeSeries(metric, historyPoints, forecastPoints);

  return {
    metric,
    historyPoints: chartMode === "snapshot" ? historyPoints.slice(-SNAPSHOT_POINT_LIMIT) : historyPoints,
    forecastPoints,
    anomalies,
    stats,
  };
}

function summarizeSeries(metric, historyPoints, forecastPoints) {
  const values = historyPoints.map((point) => point.value).filter((value) => value !== null);

  if (!values.length) {
    return {
      current: null,
      min: null,
      max: null,
      avg: null,
      delta: null,
      trend: "unknown",
      nextForecast: forecastPoints[0]?.value ?? null,
      unit: metric.unit,
    };
  }

  const current = values[values.length - 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const delta = values.length > 1 ? current - values[0] : null;

  return {
    current,
    min,
    max,
    avg,
    delta,
    trend: detectTrend(delta),
    nextForecast: forecastPoints[0]?.value ?? null,
    unit: metric.unit,
  };
}

function getAxisExtents(group, seriesList, scaleMode) {
  if (scaleMode === "normalized") {
    return {
      left: { min: 0, max: 1, label: "Chuẩn hóa", unit: "0-1" },
      right: null,
    };
  }

  if (group.mode === "overview") {
    return {
      left: { min: 0, max: 1, label: "Chuẩn hóa", unit: "0-1" },
      right: null,
    };
  }

  const axisBuckets = { left: [], right: [] };

  for (const series of seriesList) {
    const bucket = axisBuckets[series.metric.axisId] || axisBuckets.left;
    bucket.push(...series.historyPoints.map((point) => point.value));
    bucket.push(...series.forecastPoints.map((point) => point.value));
    bucket.push(...series.forecastPoints.map((point) => point.lower).filter((value) => value !== null));
    bucket.push(...series.forecastPoints.map((point) => point.upper).filter((value) => value !== null));
  }

  return {
    left: buildExtent(axisBuckets.left, group.axes?.left),
    right: group.axes?.right ? buildExtent(axisBuckets.right, group.axes?.right) : null,
  };
}

function buildExtent(values, axisDef) {
  const filtered = values.filter((value) => value !== null);
  if (!filtered.length) {
    return {
      min: 0,
      max: 1,
      label: axisDef?.label || "",
      unit: axisDef?.unit || "",
    };
  }

  const min = Math.min(...filtered);
  const max = Math.max(...filtered);
  const padding = min === max ? Math.max(1, Math.abs(min) * 0.1 || 1) : (max - min) * 0.12;

  return {
    min: min - padding,
    max: max + padding,
    label: axisDef?.label || "",
    unit: axisDef?.unit || "",
  };
}

function projectSeriesForChart(series, axisExtents, xBounds, scaleMode) {
  const frame = createChartFrame();
  const allPoints = [...series.historyPoints, ...series.forecastPoints];
  const normalizeExtent = getExtent(allPoints.map((point) => point.value));

  const mapValue = (pointValue) => {
    if (pointValue === null) return null;
    if (scaleMode === "normalized") {
      return normalizeValue(pointValue, normalizeExtent);
    }

    const axisExtent = axisExtents[series.metric.axisId] || axisExtents.left;
    return pointValue;
  };

  const historyPoints = series.historyPoints
    .map((point) => ({
      ...point,
      plottedValue: mapValue(point.value),
    }))
    .filter((point) => point.plottedValue !== null);

  const forecastPoints = series.forecastPoints
    .map((point) => ({
      ...point,
      plottedValue: mapValue(point.value),
      lowerPlotted: point.lower !== null ? mapValue(point.lower) : null,
      upperPlotted: point.upper !== null ? mapValue(point.upper) : null,
    }))
    .filter((point) => point.plottedValue !== null);

  const anomalies = series.anomalies
    .map((item) => {
      const fallbackPoint = findNearestPoint(series, item.ts);
      const sourceValue = toNumber(item.value) ?? fallbackPoint?.value ?? null;
      const plottedValue = sourceValue !== null ? mapValue(sourceValue) : null;
      if (plottedValue === null) return null;
      return {
        ...item,
        value: sourceValue,
        plottedValue,
      };
    })
    .filter(Boolean);

  const axisExtent = scaleMode === "normalized"
    ? axisExtents.left
    : axisExtents[series.metric.axisId] || axisExtents.left;

  return {
    ...series,
    historyPoints,
    forecastPoints,
    anomalies,
    axisExtent,
    frame,
    historyPath: buildValuePath(historyPoints, axisExtent, frame, xBounds),
    forecastPath: buildValuePath(forecastPoints, axisExtent, frame, xBounds),
    confidenceBand: buildConfidenceBand(forecastPoints, axisExtent, frame, xBounds),
    lastHistoryPoint: buildLastPoint(historyPoints, axisExtent, frame, xBounds),
    lastForecastPoint: buildLastPoint(forecastPoints, axisExtent, frame, xBounds),
  };
}

function renderPipelineState(pipelineState, historicalBounds) {
  const latestTs = getLatestPublishTs(state.data);
  const card = document.getElementById("pipelineStatusCard");
  const label = document.getElementById("connectionLabel");
  const detail = document.getElementById("connectionDetail");
  const updatedText = document.getElementById("lastUpdatedText");
  const updatedSubtext = document.getElementById("lastUpdatedSubtext");

  if (card) {
    card.className = `status-card status-card--${pipelineState.tone}`;
  }

  setTextNode(label, pipelineState.label);
  setTextNode(detail, pipelineState.detail);
  setTextNode(updatedText, formatTimestamp(latestTs));
  setTextNode(
    updatedSubtext,
    latestTs
      ? `Khoảng đang xem: ${formatActiveRangeLabel(historicalBounds)}`
      : "Chưa có mốc thời gian để hiển thị."
  );
}

function renderMainChart(chartModel) {
  const chartTitle = document.getElementById("chartTitle");
  const chartMeta = document.getElementById("chartMeta");
  const mainChart = document.getElementById("mainChart");
  const mainAxis = document.getElementById("mainAxis");
  const mainLegend = document.getElementById("mainLegend");
  const yAxisLeft = document.getElementById("chartYAxisLeft");
  const yAxisRight = document.getElementById("chartYAxisRight");

  if (!chartTitle || !chartMeta || !mainChart || !mainAxis || !mainLegend || !yAxisLeft || !yAxisRight) {
    return;
  }

  chartTitle.textContent = chartModel.group.label;
  chartMeta.hidden = true;
  chartMeta.textContent = "";

  if (!chartModel.series.length || !chartModel.xBounds.minTs || !chartModel.xBounds.maxTs) {
    chartMeta.textContent = "Chưa có dữ liệu trong khoảng thời gian đang chọn.";
    mainChart.innerHTML = "";
    mainAxis.innerHTML = "";
    mainLegend.innerHTML = `<div class="empty-state">Không có chuỗi dữ liệu phù hợp với nhóm và khoảng thời gian đang chọn.</div>`;
    yAxisLeft.innerHTML = "";
    yAxisRight.innerHTML = "";
    return;
  }

  mainChart.innerHTML = buildChartSvg(chartModel);
  mainAxis.innerHTML = buildAxisLabels(chartModel.xBounds)
    .map((label) => `<span>${escapeHtml(label)}</span>`)
    .join("");

  renderYAxis(yAxisLeft, chartModel.axisExtents.left);
  renderYAxis(yAxisRight, chartModel.axisExtents.right);

  mainLegend.innerHTML = chartModel.series.map((series) => buildLegendCard(series, chartModel)).join("");
}

function renderYAxis(container, axisExtent) {
  if (!container) return;
  if (!axisExtent) {
    container.innerHTML = "";
    return;
  }

  const ticks = buildNumericTicks(axisExtent.min, axisExtent.max, 4);
  container.innerHTML = ticks.map((value, index) => `
    <div class="chart-y-axis__tick">
      <span class="chart-y-axis__value">${escapeHtml(formatAxisValue(value, axisExtent.unit))}</span>
      ${index === ticks.length - 1 && axisExtent.label
        ? `<span class="chart-y-axis__label">${escapeHtml(`${axisExtent.label} (${axisExtent.unit})`)}</span>`
        : ""}
    </div>
  `).join("");
}

function renderSummaryView(chartModel) {
  const group = chartModel.group;
  const groupSeries = chartModel.series;

  setTextNode(document.getElementById("focusTitle"), group.label);
  setTextNode(
    document.getElementById("focusValue"),
    `${groupSeries.length} đường dữ liệu`
  );

  const scaleSentence = chartModel.scaleMode === "normalized"
    ? "Biểu đồ đang ở chế độ chuẩn hóa xu hướng để so sánh hình dạng biến động."
    : "Biểu đồ đang ở chế độ giá trị tuyệt đối với trục Y đúng đơn vị kỹ thuật.";

  setTextNode(
    document.getElementById("focusDescription"),
    `${group.description} ${scaleSentence}`
  );

  const focusStats = document.getElementById("focusStats");
  if (!focusStats) return;

  if (!groupSeries.length) {
    focusStats.innerHTML = `
      <article class="focus-stat">
        <span class="focus-stat__label">Khoảng đang xem</span>
        <strong class="focus-stat__value">${escapeHtml(formatActiveRangeLabel(chartModel.historicalBounds))}</strong>
      </article>
      <article class="focus-stat">
        <span class="focus-stat__label">Số mẫu</span>
        <strong class="focus-stat__value">0</strong>
      </article>
    `;
  } else {
    focusStats.innerHTML = groupSeries.map((series) => `
      <article class="focus-stat">
        <span class="focus-stat__label">${escapeHtml(series.metric.shortLabel)}</span>
        <strong class="focus-stat__value">${escapeHtml(formatMetric(series.stats.current, series.metric.unit))}</strong>
      </article>
    `).join("") + `
      <article class="focus-stat">
        <span class="focus-stat__label">Khoảng đang xem</span>
        <strong class="focus-stat__value">${escapeHtml(formatActiveRangeLabel(chartModel.historicalBounds))}</strong>
      </article>
      <article class="focus-stat">
        <span class="focus-stat__label">Số mẫu</span>
        <strong class="focus-stat__value">${escapeHtml(String(chartModel.pointCount))}</strong>
      </article>
    `;
  }

  const recommendation = getRecommendationForCurrentGroup();
  setRecommendationContent(
    "summaryRecommendation",
    "recommendationLevelBadge",
    recommendation
  );
}

function renderSnapshotView(globalBounds) {
  const groups = GROUP_DEFS.filter((group) => group.id !== "overview");
  const snapshotGrid = document.getElementById("snapshotGrid");
  if (!snapshotGrid) return;

  const snapshotCards = groups.map((group) => {
    const metrics = group.metricIds
      .map((metricId) => metricMap[metricId])
      .filter(Boolean);

    const lines = metrics.map((metric) => {
      const stats = summarizeMetric(metric, getHistoricalBounds());
      return {
        label: metric.shortLabel,
        value: formatMetric(stats.current, metric.unit),
      };
    });

    const representative = metrics[0] ? summarizeMetric(metrics[0], getHistoricalBounds()) : null;

    return `
      <article class="snapshot-card" data-group-id="${escapeHtml(group.id)}">
        <div class="snapshot-card__head">
          <div>
            <span class="snapshot-card__label">${escapeHtml(group.label)}</span>
          </div>
          <span class="snapshot-card__trend is-${escapeHtml(representative?.trend || "unknown")}">${escapeHtml(describeTrendShort(representative?.trend || "unknown"))}</span>
        </div>
        <div class="snapshot-card__list">
          ${lines.map((line) => `
            <div class="snapshot-line">
              <span class="snapshot-line__name">${escapeHtml(line.label)}</span>
              <span class="snapshot-line__value">${escapeHtml(line.value)}</span>
            </div>
          `).join("")}
        </div>
      </article>
    `;
  }).join("");

  snapshotGrid.innerHTML = snapshotCards || `<div class="empty-state">Chưa có dữ liệu snapshot.</div>`;

  const snapshotCount = HISTORY_GROUPS.reduce(
    (sum, key) => sum + (state.data.history[key]?.length || 0),
    0
  );
  setTextNode(document.getElementById("snapshotCountText"), String(snapshotCount));
  setTextNode(
    document.getElementById("snapshotCountSubtext"),
    globalBounds.minTs && globalBounds.maxTs
      ? `${formatDateOnly(globalBounds.minTs)} → ${formatDateOnly(globalBounds.maxTs)}`
      : "Đang chờ dữ liệu."
  );
}

function renderPredictionView(chartModel) {
  const analysis = state.data.analysis;
  const diagnosis = analysis.diagnosis;
  const modelLabel = analysis.modelName || analysis.source || "Server AI";
  const diagnosisStatusText = diagnosis?.displayLabel
    || diagnosis?.label
    || (chartModel.hasForecast
      ? "ÄÃ£ cÃ³ chuá»—i dá»± bÃ¡o"
      : "Chá» káº¿t quáº£ dá»± bÃ¡o");
  const diagnosisDescription = diagnosis?.displayLabel
    ? `Server AI hiá»‡n Ä‘ang gáº¯n nhÃ£n '${diagnosis.displayLabel}' cho báº£n ghi má»›i nháº¥t.`
    : null;
  const statusLabel = chartModel.hasForecast
    ? "Đã có chuỗi dự báo"
    : "Chờ kết quả dự báo";

  setTextNode(document.getElementById("predictionTitle"), `Dự đoán ${chartModel.group.label.toLowerCase()}`);
  setTextNode(
    document.getElementById("predictionDescription"),
    chartModel.hasForecast
      ? "Biểu đồ chính đang hiển thị dữ liệu quá khứ bằng nét liền, chuỗi dự báo bằng nét đứt và vùng mờ độ tin cậy."
      : "Tab này sẽ mở rộng trục thời gian sang tương lai ngay khi server trả về chuỗi dự báo."
  );
  if (diagnosisDescription) {
    setTextNode(document.getElementById("predictionDescription"), diagnosisDescription);
  }
  setTextNode(document.getElementById("predictionStatusText"), diagnosisStatusText);
  setTextNode(
    document.getElementById("predictionRangeText"),
    chartModel.hasForecast ? formatForecastHorizon(chartModel.forecastHorizonSec) : "--"
  );
  setTextNode(document.getElementById("predictionAnomalyText"), String(chartModel.anomalyCount));
  setTextNode(document.getElementById("predictionModelText"), modelLabel);

  const recommendation = getRecommendationForCurrentGroup();
  setRecommendationContent(
    "predictionRecommendation",
    "predictionLevelBadge",
    recommendation
  );
}

const DIAGNOSIS_LABEL_ID_BY_KEY = {
  normal_context: 0,
  packet_loss_outage: 1,
  water_deficit: 2,
  moisture_or_intervention_context: 3,
};

const BINARY_DIAGNOSIS_PRESET_BY_LABEL = {
  normal: "binary_normal",
  abnormal: "binary_abnormal",
};

const DIAGNOSIS_UI_PRESETS = {
  [-1]: {
    title: "\u0110ang ch\u1edd ph\u00e2n t\u00edch",
    statusText: "\u0110ang ch\u1edd k\u1ebft qu\u1ea3",
    badgeText: "Ch\u1edd x\u1eed l\u00fd",
    tone: "neutral",
    description: "Server ch\u01b0a c\u00f3 \u0111\u1ee7 d\u1eef li\u1ec7u m\u1edbi \u0111\u1ec3 k\u1ebft lu\u1eadn tr\u1ea1ng th\u00e1i hi\u1ec7n t\u1ea1i.",
    summary: "Khi c\u00f3 b\u1ea3n ghi telemetry m\u1edbi, kh\u1ed1i n\u00e0y s\u1ebd t\u1ef1 \u0111\u1ed9ng n\u00e2ng c\u1ea5p th\u00e0nh th\u1ebb ch\u1ea9n \u0111o\u00e1n.",
    recommendation: "Ti\u1ebfp t\u1ee5c theo d\u00f5i, ho\u1eb7c ch\u1ea1y th\u00eam m\u1ed9t chu k\u1ef3 \u0111\u1ed3ng b\u1ed9 \u0111\u1ec3 nh\u1eadn b\u1ea3n ghi m\u1edbi.",
    recommendationLevel: "normal",
    recommendationBadge: "Theo d\u00f5i",
    horizonText: "--",
  },
  binary_normal: {
    title: "B\u00ecnh th\u01b0\u1eddng",
    statusText: "B\u00ecnh th\u01b0\u1eddng",
    badgeText: "\u1ed4n \u0111\u1ecbnh",
    tone: "good",
    description: "Runtime XGBoost \u0111ang xem b\u1ea3n ghi m\u1edbi nh\u1ea5t l\u00e0 nh\u00f3m b\u00ecnh th\u01b0\u1eddng.",
    summary: "Kh\u00f4ng c\u00f3 d\u1ea5u hi\u1ec7u b\u1ea5t th\u01b0\u1eddng n\u1ed5i b\u1eadt trong c\u1eeda s\u1ed5 d\u1eef li\u1ec7u hi\u1ec7n t\u1ea1i.",
    recommendation: "Ti\u1ebfp t\u1ee5c duy tr\u00ec chu k\u1ef3 theo d\u00f5i hi\u1ec7n t\u1ea1i v\u00e0 ch\u1edd b\u1ea3n ghi m\u1edbi.",
    recommendationLevel: "good",
    recommendationBadge: "Theo d\u00f5i",
    horizonText: "\u0110ang \u1ed5n \u0111\u1ecbnh",
  },
  binary_abnormal: {
    title: "B\u1ea5t th\u01b0\u1eddng c\u1ea7n ki\u1ec3m tra",
    statusText: "B\u1ea5t th\u01b0\u1eddng",
    badgeText: "C\u1ea3nh b\u00e1o",
    tone: "warning",
    description: "Runtime XGBoost \u0111ang g\u1eafn b\u1ea3n ghi m\u1edbi nh\u1ea5t v\u00e0o nh\u00f3m b\u1ea5t th\u01b0\u1eddng nh\u01b0ng kh\u00f4ng ph\u00e2n lo\u1ea1i chi ti\u1ebft theo t\u1eebng ng\u1eef c\u1ea3nh 4 l\u1edbp.",
    summary: "C\u1ea7n \u0111\u1ed1i chi\u1ebfu th\u00eam chart l\u1ecbch s\u1eed, anomaly rules v\u00e0 b\u1ed1i c\u1ea3nh v\u1eadn h\u00e0nh \u0111\u1ec3 x\u00e1c \u0111\u1ecbnh nguy\u00ean nh\u00e2n c\u1ee5 th\u1ec3.",
    recommendation: "Ki\u1ec3m tra telemetry g\u1ea7n nh\u1ea5t, c\u00e1c ch\u1ec9 s\u1ed1 \u0111\u1ea5t/kh\u00f4ng kh\u00ed v\u00e0 c\u00e1c anomaly do backend publish tr\u01b0\u1edbc khi k\u1ebft lu\u1eadn nguy\u00ean nh\u00e2n.",
    recommendationLevel: "warn",
    recommendationBadge: "L\u01b0u \u00fd",
    horizonText: "C\u1ea7n \u0111\u1ed1i chi\u1ebfu th\u00eam",
  },
  0: {
    title: "B\u00ecnh th\u01b0\u1eddng",
    statusText: "B\u00ecnh th\u01b0\u1eddng",
    badgeText: "\u1ed4n \u0111\u1ecbnh",
    tone: "good",
    description: "M\u00f4 h\u00ecnh FT-Transformer \u0111ang xem b\u1ea3n ghi m\u1edbi nh\u1ea5t l\u00e0 tr\u1ea1ng th\u00e1i v\u1eadn h\u00e0nh b\u00ecnh th\u01b0\u1eddng.",
    summary: "Kh\u00f4ng ph\u00e1t hi\u1ec7n d\u1ea5u hi\u1ec7u b\u1ea5t th\u01b0\u1eddng n\u1ed5i b\u1eadt trong c\u1eeda s\u1ed5 d\u1eef li\u1ec7u hi\u1ec7n t\u1ea1i.",
    recommendation: "Ti\u1ebfp t\u1ee5c duy tr\u00ec ch\u1ebf \u0111\u1ed9 v\u1eadn h\u00e0nh hi\u1ec7n t\u1ea1i v\u00e0 theo d\u00f5i chu k\u1ef3 k\u1ebf ti\u1ebfp.",
    recommendationLevel: "good",
    recommendationBadge: "Theo d\u00f5i",
    horizonText: "\u0110ang \u1ed5n \u0111\u1ecbnh",
  },
  1: {
    title: "Gi\u00e1n \u0111o\u1ea1n g\u00f3i tin",
    statusText: "Gi\u00e1n \u0111o\u1ea1n g\u00f3i tin",
    badgeText: "C\u1ea3nh b\u00e1o h\u1ec7 th\u1ed1ng",
    tone: "danger",
    description: "M\u00f4 h\u00ecnh ghi nh\u1eadn kho\u1ea3ng tr\u1ec5 b\u1ea5t th\u01b0\u1eddng gi\u1eefa c\u00e1c b\u1ea3n ghi telemetry g\u1ea7n nh\u1ea5t.",
    summary: "M\u1eabu hi\u1ec7n t\u1ea1i ph\u00f9 h\u1ee3p v\u1edbi ng\u1eef c\u1ea3nh m\u1ea5t g\u00f3i do outage, m\u1ea5t ngu\u1ed3n ho\u1eb7c gi\u00e1n \u0111o\u1ea1n upload.",
    recommendation: "Ki\u1ec3m tra kho\u1ea3ng gap telemetry, ngu\u1ed3n \u0111i\u1ec7n / solar v\u00e0 t\u00ednh li\u00ean t\u1ee5c upload tr\u01b0\u1edbc khi k\u1ebft lu\u1eadn l\u1ed7i c\u1ea3m bi\u1ebfn.",
    recommendationLevel: "danger",
    recommendationBadge: "Kh\u1ea9n",
    horizonText: "C\u1ea7n ki\u1ec3m tra ngay",
  },
  2: {
    title: "Thi\u1ebfu n\u01b0\u1edbc",
    statusText: "Thi\u1ebfu n\u01b0\u1edbc",
    badgeText: "C\u1ea3nh b\u00e1o t\u01b0\u1edbi",
    tone: "warning",
    description: "M\u00f4 h\u00ecnh \u0111ang g\u1eafn nh\u00e3n stress n\u01b0\u1edbc cho b\u1ea3n ghi m\u1edbi nh\u1ea5t.",
    summary: "\u0110\u1ed9 \u1ea9m \u0111\u1ea5t v\u00e0 ng\u1eef c\u1ea3nh m\u00f4i tr\u01b0\u1eddng hi\u1ec7n nghi\u00eang v\u1ec1 nguy c\u01a1 thi\u1ebfu n\u01b0\u1edbc t\u00edch l\u0169y.",
    recommendation: "R\u00e0 so\u00e1t l\u1ecbch t\u01b0\u1edbi, \u0111\u1ed9 \u1ea9m \u0111\u1ea5t v\u00e0 d\u1eef li\u1ec7u th\u1eddi ti\u1ebft tr\u01b0\u1edbc khi b\u1ed5 sung n\u01b0\u1edbc.",
    recommendationLevel: "warn",
    recommendationBadge: "L\u01b0u \u00fd",
    horizonText: "N\u00ean theo d\u00f5i s\u00e1t",
  },
  3: {
    title: "\u1ea8m cao / can thi\u1ec7p t\u01b0\u1edbi-b\u00f3n",
    statusText: "Ng\u1eef c\u1ea3nh \u1ea9m cao",
    badgeText: "B\u1ed1i c\u1ea3nh can thi\u1ec7p",
    tone: "info",
    description: "B\u1ea3n ghi m\u1edbi nh\u1ea5t mang d\u1ea5u hi\u1ec7u \u1ea9m cao ho\u1eb7c t\u00e1c \u0111\u1ed9ng t\u1eeb chu k\u1ef3 t\u01b0\u1edbi / b\u00f3n.",
    summary: "M\u00f4 h\u00ecnh kh\u00f4ng xem \u0111\u00e2y l\u00e0 l\u1ed7i h\u1ec7 th\u1ed1ng, m\u00e0 l\u00e0 ng\u1eef c\u1ea3nh v\u1eadn h\u00e0nh c\u1ea7n \u0111\u1ecdc c\u00f9ng tr\u1ea1ng th\u00e1i m\u00f4i tr\u01b0\u1eddng.",
    recommendation: "Ki\u1ec3m tra xem khu v\u1ef1c v\u1eeba c\u00f3 m\u01b0a, t\u01b0\u1edbi hay b\u00f3n dinh d\u01b0\u1ee1ng g\u1ea7n th\u1eddi \u0111i\u1ec3m l\u1ea5y m\u1eabu hay kh\u00f4ng.",
    recommendationLevel: "warn",
    recommendationBadge: "Di\u1ec5n gi\u1ea3i",
    horizonText: "\u0110ang c\u1ea7n \u0111\u1ed1i chi\u1ebfu ng\u1eef c\u1ea3nh",
  },
};

function renderPredictionViewModern(chartModel) {
  const analysis = state.data.analysis;
  const diagnosis = analysis.diagnosis;
  const modelLabel = analysis.modelName || analysis.source || "Server AI";
  const diagnosisUi = buildDiagnosisUiModel(diagnosis, chartModel);

  ensurePredictionHero();
  renderPredictionHero(diagnosisUi);

  setTextNode(document.getElementById("predictionTitle"), `D\u1ef1 \u0111o\u00e1n ${chartModel.group.label.toLowerCase()}`);
  setTextNode(document.getElementById("predictionDescription"), diagnosisUi.description);
  setTextNode(document.getElementById("predictionStatusText"), diagnosisUi.statusText);
  setTextNode(
    document.getElementById("predictionRangeText"),
    chartModel.hasForecast ? formatForecastHorizon(chartModel.forecastHorizonSec) : diagnosisUi.horizonText
  );
  setTextNode(document.getElementById("predictionAnomalyText"), String(chartModel.anomalyCount));
  setTextNode(document.getElementById("predictionModelText"), modelLabel);

  setRecommendationContent(
    "predictionRecommendation",
    "predictionLevelBadge",
    {
      text: diagnosisUi.recommendation,
      level: diagnosisUi.recommendationLevel,
      levelLabel: diagnosisUi.recommendationBadge,
      groupIds: [],
      metricIds: [],
    }
  );
}

function ensurePredictionHero() {
  const predictionView = document.getElementById("predictionView");
  const description = document.getElementById("predictionDescription");
  if (!predictionView || !description) return null;

  let hero = document.getElementById("predictionHero");
  if (hero) return hero;

  hero = document.createElement("section");
  hero.id = "predictionHero";
  hero.className = "prediction-hero";
  hero.dataset.tone = "neutral";
  hero.innerHTML = `
    <div class="prediction-hero__head">
      <span class="prediction-hero__badge" id="predictionSeverityBadge"></span>
      <span class="prediction-hero__confidence" id="predictionConfidenceText"></span>
    </div>
    <strong class="prediction-hero__title" id="predictionHeroTitle"></strong>
    <p class="prediction-hero__summary" id="predictionHeroSummary"></p>
    <div class="prediction-hero__meter" aria-hidden="true">
      <div class="prediction-hero__meter-fill" id="predictionConfidenceBar"></div>
    </div>
  `;
  predictionView.insertBefore(hero, description);
  return hero;
}

function renderPredictionHero(diagnosisUi) {
  const hero = document.getElementById("predictionHero");
  if (!hero) return;

  hero.dataset.tone = diagnosisUi.tone;
  setTextNode(document.getElementById("predictionSeverityBadge"), diagnosisUi.badgeText);
  setTextNode(document.getElementById("predictionConfidenceText"), diagnosisUi.confidenceText);
  setTextNode(document.getElementById("predictionHeroTitle"), diagnosisUi.title);
  setTextNode(document.getElementById("predictionHeroSummary"), diagnosisUi.summary);

  const meterFill = document.getElementById("predictionConfidenceBar");
  if (meterFill) {
    meterFill.style.width = diagnosisUi.confidenceWidth;
  }
}

function buildDiagnosisUiModel(diagnosis, chartModel) {
  const presetKey = resolveDiagnosisPresetKey(diagnosis);
  const preset = DIAGNOSIS_UI_PRESETS[presetKey] || DIAGNOSIS_UI_PRESETS[-1];
  const confidenceRatio = resolveDiagnosisConfidenceRatio(diagnosis, presetKey);
  const confidenceText = confidenceRatio === null
    ? "\u0110ang \u0111\u1ee3i x\u00e1c su\u1ea5t"
    : `\u0110\u1ed9 tin c\u1eady ${Math.round(confidenceRatio * 100)}%`;

  return {
    ...preset,
    confidenceWidth: confidenceRatio === null ? "8%" : `${Math.max(8, Math.round(confidenceRatio * 100))}%`,
    confidenceText,
    description: diagnosis
      ? preset.description
      : (chartModel.hasForecast
        ? "Bi\u1ec3u \u0111\u1ed3 ch\u00ednh \u0111ang hi\u1ec3n th\u1ecb d\u1eef li\u1ec7u qu\u00e1 kh\u1ee9 b\u1eb1ng n\u00e9t li\u1ec1n, chu\u1ed7i d\u1ef1 b\u00e1o b\u1eb1ng n\u00e9t \u0111\u1ee9t v\u00e0 v\u00f9ng m\u1edd \u0111\u1ed9 tin c\u1eady."
        : "Tab n\u00e0y s\u1ebd m\u1edf r\u1ed9ng tr\u1ee5c th\u1eddi gian sang t\u01b0\u01a1ng lai ngay khi server tr\u1ea3 v\u1ec1 chu\u1ed7i d\u1ef1 b\u00e1o."),
  };
}

function diagnosisUsesBinaryContract(diagnosis) {
  if (!diagnosis) return false;
  const modelFamily = String(diagnosis.model?.family || "").trim().toLowerCase();
  const labelScheme = String(diagnosis.model?.labelScheme || "").trim().toLowerCase();
  const label = String(diagnosis.label || "").trim().toLowerCase();

  return (
    labelScheme === "binary"
    || (modelFamily === "xgboost" && (label === "normal" || label === "abnormal"))
    || label === "normal"
    || label === "abnormal"
  );
}

function resolveDiagnosisPresetKey(diagnosis) {
  if (!diagnosis) return -1;
  if (diagnosisUsesBinaryContract(diagnosis)) {
    const label = String(diagnosis.label || "").trim().toLowerCase();
    return BINARY_DIAGNOSIS_PRESET_BY_LABEL[label] || -1;
  }
  if (Number.isFinite(diagnosis.labelId)) {
    return diagnosis.labelId;
  }
  return DIAGNOSIS_LABEL_ID_BY_KEY[diagnosis.label] ?? -1;
}

function resolveDiagnosisConfidenceRatio(diagnosis, presetKey) {
  if (!diagnosis) return null;
  const probabilityMap = diagnosis.probabilities && typeof diagnosis.probabilities === "object"
    ? diagnosis.probabilities
    : null;

  if (probabilityMap && diagnosis.label && Number.isFinite(toNumber(probabilityMap[diagnosis.label]))) {
    return Math.min(1, Math.max(0, toNumber(probabilityMap[diagnosis.label])));
  }

  const abnormalProbability = toNumber(diagnosis.abnormalProbability);
  if (!Number.isFinite(abnormalProbability)) return null;

  if (presetKey === 0 || presetKey === "binary_normal") {
    return Math.min(1, Math.max(0, 1 - abnormalProbability));
  }

  return Math.min(1, Math.max(0, abnormalProbability));
}

function renderSideViews() {
  const summaryView = document.getElementById("summaryView");
  const snapshotView = document.getElementById("snapshotView");
  const predictionView = document.getElementById("predictionView");

  if (!summaryView || !snapshotView || !predictionView) return;

  summaryView.classList.toggle("insight-view--hidden", state.sideView !== "summary");
  snapshotView.classList.toggle("insight-view--hidden", state.sideView !== "snapshot");
  predictionView.classList.toggle("insight-view--hidden", state.sideView !== "prediction");
}

function setRecommendationContent(contentId, badgeId, recommendation) {
  const content = document.getElementById(contentId);
  const badge = document.getElementById(badgeId);
  if (!content || !badge) return;

  if (!recommendation) {
    content.textContent = "Chưa có khuyến nghị phân tích từ server.";
    badge.textContent = "Theo dõi";
    badge.className = "recommendation-card__badge";
    return;
  }

  content.textContent = recommendation.text;
  badge.textContent = recommendation.levelLabel;
  badge.className = `recommendation-card__badge ${recommendation.levelClass}`;
}

function buildChartMeta(chartModel) {
  const metaLines = [];

  metaLines.push(`<strong>${escapeHtml(formatActiveRangeLabel(chartModel.historicalBounds))}</strong>`);

  if (state.rangeMode === "preset") {
    metaLines.push(escapeHtml(`Cửa sổ lùi: T-${formatPresetTrailingLabel()} → T`));
  } else {
    metaLines.push("Khoảng tĩnh đã khóa theo ngày bạn chọn.");
  }

  if (chartModel.group.forceNormalized) {
    metaLines.push("Nhóm tổng quan luôn dùng chuẩn hóa xu hướng vì khác đơn vị đo.");
  } else if (chartModel.scaleMode === "absolute") {
    metaLines.push("Đang hiển thị trị số thật với trục Y trái / phải theo đúng đơn vị.");
  } else {
    metaLines.push("Đang hiển thị chuẩn hóa xu hướng để so sánh hình dạng biến động.");
  }

  if (chartModel.hasForecast) {
    metaLines.push(escapeHtml(`Dự báo mở rộng tới ${formatForecastHorizon(chartModel.forecastHorizonSec)}.`));
  }

  metaLines.push(
    `${escapeHtml(formatTimestamp(chartModel.xBounds.minTs))} → ${escapeHtml(formatTimestamp(chartModel.xBounds.maxTs))}`
  );

  return metaLines.join("<br />");
}

function buildLegendCard(series, chartModel) {
  const forecastBadge = chartModel.sideView === "prediction" && series.forecastPoints.length
    ? `<span class="legend-chip__badge">forecast</span>`
    : `<span class="legend-chip__badge">history</span>`;

  return `
    <article class="legend-chip">
      <div class="legend-chip__title">
        <span class="legend-chip__dot" style="background:${series.metric.color}"></span>
        <span>${escapeHtml(series.metric.label)}</span>
      </div>
      <div class="legend-chip__meta-row">
        <div class="legend-chip__meta">${escapeHtml(describeTrend(series.stats.trend, series.stats.delta, series.metric.unit))}</div>
        ${forecastBadge}
      </div>
      <div class="legend-chip__value">${escapeHtml(formatMetric(series.stats.current, series.metric.unit))}</div>
      <div class="legend-chip__meta">
        ${escapeHtml(
          chartModel.chartMode === "prediction" && series.stats.nextForecast !== null
            ? `Bước dự báo gần nhất: ${formatMetric(series.stats.nextForecast, series.metric.unit)}`
            : `Min ${formatMetric(series.stats.min, series.metric.unit)} · Max ${formatMetric(series.stats.max, series.metric.unit)}`
        )}
      </div>
    </article>
  `;
}

function buildChartSvg(chartModel) {
  const frame = createChartFrame();
  const width = 920;
  const height = 360;

  const horizontalGrid = [0.2, 0.4, 0.6, 0.8].map((ratio) => {
    const y = frame.padding.top + frame.height * ratio;
    return `<line class="chart-grid-line" x1="${frame.padding.left}" y1="${y}" x2="${width - frame.padding.right}" y2="${y}"></line>`;
  });

  const verticalGrid = buildXAxisTicks(chartModel.xBounds, 5).slice(1, -1).map((item) => {
    const x = mapTsToX(item.ts, chartModel.xBounds, frame);
    return `<line class="chart-grid-line" x1="${x}" y1="${frame.padding.top}" x2="${x}" y2="${height - frame.padding.bottom}"></line>`;
  });

  const bands = chartModel.series.map((series) => {
    if (!series.confidenceBand) return "";
    return `<path class="chart-band" d="${series.confidenceBand}" fill="${toAlpha(series.metric.color, 0.16)}"></path>`;
  }).join("");

  const historicalPaths = chartModel.series.map((series) => `
    ${series.historyPath ? `<path class="chart-series ${chartModel.sideView === "snapshot" ? "chart-series--snapshot" : ""}" d="${series.historyPath}" stroke="${series.metric.color}"></path>` : ""}
    ${series.lastHistoryPoint ? `<circle class="chart-point" cx="${series.lastHistoryPoint.x}" cy="${series.lastHistoryPoint.y}" r="4.8" fill="${series.metric.color}"></circle>` : ""}
  `).join("");

  const forecastPaths = chartModel.series.map((series) => `
    ${series.forecastPath ? `<path class="chart-series chart-series--forecast" d="${series.forecastPath}" stroke="${series.metric.color}"></path>` : ""}
    ${series.lastForecastPoint ? `<circle class="chart-point chart-point--forecast" cx="${series.lastForecastPoint.x}" cy="${series.lastForecastPoint.y}" r="4.4" fill="${series.metric.color}"></circle>` : ""}
  `).join("");

  const anomalyMarkers = chartModel.series.flatMap((series) =>
    series.anomalies.map((anomaly) => {
      const x = mapTsToX(anomaly.ts, chartModel.xBounds, frame);
      const y = mapValueToY(anomaly.plottedValue, series.axisExtent, frame);
      return `
        <g>
          <circle class="chart-anomaly" cx="${x}" cy="${y}" r="6.5" fill="#c55a53"></circle>
          <text class="chart-anomaly-label" x="${x}" y="${y + 3}" text-anchor="middle">!</text>
        </g>
      `;
    })
  ).join("");

  return `
    <g>
      ${horizontalGrid.join("")}
      ${verticalGrid.join("")}
      <line class="chart-domain-line" x1="${frame.padding.left}" y1="${height - frame.padding.bottom}" x2="${width - frame.padding.right}" y2="${height - frame.padding.bottom}"></line>
      ${bands}
      ${historicalPaths}
      ${forecastPaths}
      ${anomalyMarkers}
    </g>
  `;
}

function buildValuePath(points, extent, frame, xBounds) {
  if (!points.length) return "";

  return points.map((point, index) => {
    const x = mapTsToX(point.ts, xBounds, frame);
    const y = mapValueToY(point.plottedValue, extent, frame);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");
}

function buildConfidenceBand(points, extent, frame, xBounds) {
  const valid = points.filter((point) => point.lowerPlotted !== null && point.upperPlotted !== null);
  if (valid.length < 2) return "";

  const upperPath = valid.map((point, index) => {
    const x = mapTsToX(point.ts, xBounds, frame);
    const y = mapValueToY(point.upperPlotted, extent, frame);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");

  const lowerPath = valid.slice().reverse().map((point) => {
    const x = mapTsToX(point.ts, xBounds, frame);
    const y = mapValueToY(point.lowerPlotted, extent, frame);
    return `L${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");

  return `${upperPath} ${lowerPath} Z`;
}

function buildLastPoint(points, extent, frame, xBounds) {
  if (!points.length) return null;
  const point = points[points.length - 1];
  return {
    x: mapTsToX(point.ts, xBounds, frame),
    y: mapValueToY(point.plottedValue, extent, frame),
  };
}

function buildAxisLabels(xBounds) {
  return buildXAxisTicks(xBounds, 5).map((item) => formatAxisTick(item.ts, xBounds.maxTs - xBounds.minTs));
}

function buildXAxisTicks(xBounds, count) {
  if (!xBounds.minTs || !xBounds.maxTs) return [];
  if (count <= 1) return [{ ts: xBounds.minTs }];

  return Array.from({ length: count }, (_, index) => ({
    ts: Math.round(xBounds.minTs + ((xBounds.maxTs - xBounds.minTs) * index) / (count - 1)),
  }));
}

function renderPredictionBadge(level) {
  if (level === "danger") return "is-danger";
  if (level === "warn") return "is-warn";
  return "is-good";
}

function derivePipelineState(historicalBounds, chartModel) {
  const explicitState = mapPipelineState(state.data.pipeline.state);
  if (explicitState) {
    return {
      ...explicitState,
      detail: state.data.pipeline.detail || explicitState.detail,
    };
  }

  if (state.mode !== "firebase") {
    return {
      ...PIPELINE_STATES.demo,
      detail: state.connectionDetail,
    };
  }

  if (!state.connected) {
    return {
      ...PIPELINE_STATES.offline_error,
      detail: state.connectionDetail,
    };
  }

  const latestTs = getLatestPublishTs(state.data);
  const analysisTs = state.data.analysis.lastAnalysisTs;
  const isHistorical = Boolean(
    historicalBounds.maxTs &&
    latestTs &&
    historicalBounds.maxTs < latestTs - LIVE_GRACE_SECONDS
  );

  if (isHistorical) {
    return PIPELINE_STATES.historical_view;
  }

  if (!chartModel.hasForecast && (analysisTs === null || (latestTs && analysisTs < latestTs))) {
    return PIPELINE_STATES.awaiting_analysis;
  }

  return PIPELINE_STATES.live_syncing;
}

function mapPipelineState(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return null;

  const aliases = {
    live: "live_syncing",
    syncing: "live_syncing",
    live_syncing: "live_syncing",
    awaiting: "awaiting_analysis",
    awaiting_analysis: "awaiting_analysis",
    waiting_analysis: "awaiting_analysis",
    historical: "historical_view",
    historical_view: "historical_view",
    offline: "offline_error",
    error: "offline_error",
    offline_error: "offline_error",
  };

  return PIPELINE_STATES[aliases[normalized]] || null;
}

function getRecommendationForCurrentGroup() {
  const group = getSelectedGroup();
  const matches = state.data.analysis.recommendations.filter((item) => {
    if (!item.groupIds.length) return true;
    return item.groupIds.includes(group.id) || group.metricIds.some((metricId) => item.metricIds.includes(metricId));
  });

  const recommendation = matches[0];
  if (!recommendation) return null;

  return {
    text: recommendation.text,
    levelLabel: recommendation.levelLabel,
    levelClass: renderPredictionBadge(recommendation.level),
  };
}

function getAnomaliesForMetric(metric, bounds, forecastPoints) {
  const minTs = bounds.minTs || 0;
  const maxTs = Math.max(
    bounds.maxTs || 0,
    forecastPoints.length ? forecastPoints[forecastPoints.length - 1].ts : 0
  );

  return state.data.analysis.anomalies.filter((item) => {
    const metricMatch = item.metricIds.includes(metric.id) || item.metricKeys.includes(metric.metricKey);
    const groupMatch = item.groupIds.includes(metric.historyKey);
    return (metricMatch || groupMatch) && item.ts >= minTs && item.ts <= maxTs;
  });
}

function getChartXBounds(seriesList, effectiveBounds, chartMode) {
  const historyMin = effectiveBounds.minTs;
  const historyMax = effectiveBounds.maxTs;
  const forecastMax = Math.max(
    historyMax || 0,
    ...seriesList.map((series) => series.forecastPoints[series.forecastPoints.length - 1]?.ts || 0)
  );

  return {
    minTs: historyMin,
    maxTs: chartMode === "prediction" ? forecastMax : historyMax,
  };
}

function getForecastHorizon(seriesList, historyMax) {
  if (!historyMax) return 0;
  const forecastMax = Math.max(
    0,
    ...seriesList.map((series) => series.forecastPoints[series.forecastPoints.length - 1]?.ts || 0)
  );
  return Math.max(0, forecastMax - historyMax);
}

function getSnapshotBounds(bounds) {
  if (!bounds.minTs || !bounds.maxTs) return bounds;
  const fallbackSpan = 3 * 3600;
  return {
    minTs: Math.max(bounds.minTs, bounds.maxTs - fallbackSpan),
    maxTs: bounds.maxTs,
  };
}

function getForecastRecordsForMetric(metric) {
  return state.data.analysis.forecast[metric.historyKey] || [];
}

function extractForecastPoint(record, metric) {
  if (!record || typeof record !== "object") return null;

  const rawMetricNode = record[metric.metricKey];
  const nestedNode = rawMetricNode && typeof rawMetricNode === "object" ? rawMetricNode : null;
  const value = toNumber(
    nestedNode?.value ??
      record.value ??
      record[metric.metricKey]
  );
  const lower = toNumber(
    nestedNode?.lower ??
      record[`${metric.metricKey}_lower`] ??
      record[`${metric.metricKey}Lower`] ??
      record.lower
  );
  const upper = toNumber(
    nestedNode?.upper ??
      record[`${metric.metricKey}_upper`] ??
      record[`${metric.metricKey}Upper`] ??
      record.upper
  );

  const ts = toNumber(record.ts);
  if (ts === null) return null;

  return {
    ts,
    value,
    lower,
    upper,
  };
}

function findNearestPoint(series, ts) {
  const pool = [...series.historyPoints, ...series.forecastPoints];
  if (!pool.length) return null;

  return pool.reduce((nearest, point) => {
    if (!nearest) return point;
    return Math.abs(point.ts - ts) < Math.abs(nearest.ts - ts) ? point : nearest;
  }, null);
}

function getHistoricalBounds() {
  const globalBounds = getGlobalBounds();
  if (!globalBounds.minTs || !globalBounds.maxTs) {
    return { minTs: null, maxTs: null };
  }

  if (state.rangeMode === "custom" && isCustomRangeValid()) {
    const customMin = dateStringToStartTs(state.customStart);
    const customMax = dateStringToEndTs(state.customEnd);
    return {
      minTs: Math.max(globalBounds.minTs, customMin),
      maxTs: Math.min(globalBounds.maxTs, customMax),
    };
  }

  const preset = RANGE_PRESETS.find((item) => item.id === state.rangePresetId) || RANGE_PRESETS[3];
  if (preset.hours === null) {
    return { ...globalBounds };
  }

  return {
    minTs: Math.max(globalBounds.minTs, globalBounds.maxTs - preset.hours * 3600),
    maxTs: globalBounds.maxTs,
  };
}

function getGlobalBounds() {
  const timestamps = HISTORY_GROUPS.flatMap((group) =>
    state.data.history[group].map((record) => record.ts)
  ).filter(Boolean);

  if (!timestamps.length) {
    return { minTs: null, maxTs: null };
  }

  return {
    minTs: Math.min(...timestamps),
    maxTs: Math.max(...timestamps),
  };
}

function ensurePresetStillValid(bounds) {
  if (state.rangeMode !== "preset") return;
  if (!bounds.minTs || !bounds.maxTs) return;
  if (isPresetAvailable(state.rangePresetId, bounds)) return;

  const fallback = RANGE_PRESETS.slice()
    .reverse()
    .find((preset) => isPresetAvailable(preset.id, bounds));

  state.rangePresetId = fallback?.id || "all";
}

function syncPresetAvailability(bounds) {
  document.querySelectorAll("[data-range]").forEach((button) => {
    const presetId = button.dataset.range || "";
    button.disabled = !isPresetAvailable(presetId, bounds);
  });
}

function isPresetAvailable(presetId, bounds = getGlobalBounds()) {
  const preset = RANGE_PRESETS.find((item) => item.id === presetId);
  if (!preset) return false;
  if (!bounds.minTs || !bounds.maxTs) return preset.hours === null;
  if (preset.hours === null) return true;

  const spanHours = (bounds.maxTs - bounds.minTs) / 3600;
  return spanHours >= preset.hours;
}

function syncDateInputs(bounds) {
  const startInput = document.getElementById("rangeStartInput");
  const endInput = document.getElementById("rangeEndInput");
  if (!startInput || !endInput) return;

  const minDate = bounds.minTs ? tsToDateInput(bounds.minTs) : "";
  const maxDate = bounds.maxTs ? tsToDateInput(bounds.maxTs) : "";

  startInput.min = minDate;
  startInput.max = maxDate;
  endInput.min = minDate;
  endInput.max = maxDate;

  if (state.customStart !== startInput.value) startInput.value = state.customStart;
  if (state.customEnd !== endInput.value) endInput.value = state.customEnd;
}

function isCustomRangeValid() {
  if (!state.customStart || !state.customEnd) return false;

  const startTs = dateStringToStartTs(state.customStart);
  const endTs = dateStringToEndTs(state.customEnd);
  if (startTs > endTs) return false;

  const bounds = getGlobalBounds();
  if (!bounds.minTs || !bounds.maxTs) return false;

  return startTs <= bounds.maxTs && endTs >= bounds.minTs;
}

function getSelectedGroup() {
  return groupMap[state.selectedGroupId] || GROUP_DEFS[1];
}

function getRecordsForMetric(metric, bounds) {
  const records = state.data.history[metric.historyKey] || [];
  if (!records.length) return [];
  if (!bounds.minTs || !bounds.maxTs) return records;
  const filtered = records.filter((record) => record.ts >= bounds.minTs && record.ts <= bounds.maxTs);
  if (
    state.rangeMode !== "preset"
    || state.rangePresetId === "all"
    || filtered.length >= MIN_PRESET_CONTEXT_POINTS
  ) {
    return filtered;
  }

  const needed = Math.max(0, MIN_PRESET_CONTEXT_POINTS - filtered.length);
  const previousContext = records.filter((record) => record.ts < bounds.minTs).slice(-needed);
  return [...previousContext, ...filtered];
}

function summarizeMetric(metric, bounds) {
  const records = getRecordsForMetric(metric, bounds);
  const values = records
    .map((record) => toNumber(record[metric.metricKey]))
    .filter((value) => value !== null);

  if (!values.length) {
    return {
      current: null,
      min: null,
      max: null,
      avg: null,
      delta: null,
      trend: "unknown",
    };
  }

  const current = values[values.length - 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const delta = values.length > 1 ? current - values[0] : null;

  return {
    current,
    min,
    max,
    avg,
    delta,
    trend: detectTrend(delta),
  };
}

function createChartFrame() {
  return {
    width: 920 - 88,
    height: 360 - 34,
    padding: { top: 16, right: 18, bottom: 18, left: 18 },
  };
}

function mapTsToX(ts, bounds, frame) {
  if (!bounds.minTs || !bounds.maxTs || bounds.minTs === bounds.maxTs) {
    return frame.padding.left + frame.width / 2;
  }

  return frame.padding.left + ((ts - bounds.minTs) / (bounds.maxTs - bounds.minTs)) * frame.width;
}

function mapValueToY(value, extent, frame) {
  const ratio = (value - extent.min) / (extent.max - extent.min || 1);
  return frame.padding.top + frame.height - ratio * frame.height;
}

function normalizeValue(value, extent) {
  if (extent.min === extent.max) return 0.5;
  return (value - extent.min) / (extent.max - extent.min);
}

function buildNumericTicks(min, max, count) {
  if (count <= 1) return [max];
  return Array.from({ length: count }, (_, index) => {
    const ratio = 1 - index / (count - 1);
    return min + (max - min) * ratio;
  });
}

function getExtent(values) {
  const filtered = values.filter((value) => value !== null);
  if (!filtered.length) return { min: 0, max: 1 };

  const min = Math.min(...filtered);
  const max = Math.max(...filtered);

  if (min === max) {
    return { min: min - 1, max: max + 1 };
  }

  return { min, max };
}

function normalizeResultSnapshot(raw) {
  const history = raw?.history || {};
  const analysisSource = raw?.analysis || raw?.prediction || {};

  const normalizedHistory = {
    air: normalizeHistoryCollection(history.air),
    soil: normalizeHistoryCollection(history.soil),
    npk: normalizeHistoryCollection(history.npk),
    weather: normalizeHistoryCollection(history.weather),
  };

  return {
    meta: normalizeMeta(raw?.meta),
    latest: normalizeLatest(raw?.latest, normalizedHistory),
    history: normalizedHistory,
    pipeline: normalizePipeline(raw?.pipeline || raw?.meta?.pipeline),
    analysis: normalizeAnalysis({
      ...analysisSource,
      anomalies: analysisSource?.anomalies || raw?.anomalies,
      recommendations: analysisSource?.recommendations || raw?.recommendations,
    }),
  };
}

function normalizeMeta(raw) {
  return {
    snapshotVersion: raw?.snapshotVersion || raw?.version || "",
    lastPublishedTs: toNumber(raw?.lastPublishedTs),
    source: raw?.source || "",
  };
}

function normalizeLatest(raw, history) {
  const latest = {
    air: normalizeLatestEntry(raw?.air),
    soil: normalizeLatestEntry(raw?.soil),
    npk: normalizeLatestEntry(raw?.npk),
    weather: normalizeLatestEntry(raw?.weather),
  };

  for (const group of HISTORY_GROUPS) {
    if (Object.keys(latest[group]).length) continue;
    const tail = history[group]?.[history[group].length - 1];
    latest[group] = tail ? { ...tail } : {};
  }

  return latest;
}

function normalizeLatestEntry(entry) {
  if (!entry || typeof entry !== "object") return {};

  const normalized = {};
  for (const [key, value] of Object.entries(entry)) {
    normalized[key] = typeof value === "number" ? value : toNumber(value) ?? value;
  }
  return normalized;
}

function normalizePipeline(raw) {
  return {
    state: raw?.state || raw?.status || "",
    detail: raw?.detail || raw?.message || "",
    lastSyncTs: toNumber(raw?.lastSyncTs || raw?.lastIngestTs),
    lastAnalysisTs: toNumber(raw?.lastAnalysisTs),
  };
}

function normalizeAnalysis(raw) {
  return {
    status: raw?.status || "",
    priority: raw?.priority || "",
    modelName: raw?.modelName || raw?.model || "",
    source: raw?.source || "",
    lastAnalysisTs: toNumber(raw?.lastAnalysisTs || raw?.analyzedAtTs),
    diagnosis: normalizeDiagnosis(raw?.diagnosis),
    forecast: {
      air: normalizeHistoryCollection(raw?.forecast?.air),
      soil: normalizeHistoryCollection(raw?.forecast?.soil),
      npk: normalizeHistoryCollection(raw?.forecast?.npk),
      weather: normalizeHistoryCollection(raw?.forecast?.weather),
    },
    anomalies: normalizeAnomalies(raw?.anomalies),
    recommendations: normalizeRecommendations(raw?.recommendations),
  };
}

function normalizeDiagnosis(raw) {
  if (!raw || typeof raw !== "object") return null;

  return {
    status: raw.status || "",
    label: raw.label || "",
    displayLabel: raw.displayLabel || raw.label || "",
    labelId: toNumber(raw.labelId),
    abnormalProbability: toNumber(raw.abnormalProbability),
    severity: raw.severity || "",
    ts: toNumber(raw.ts),
    probabilities: raw.probabilities && typeof raw.probabilities === "object" ? raw.probabilities : {},
    model: raw.model && typeof raw.model === "object" ? raw.model : null,
  };
}

function normalizeRecommendations(raw) {
  if (!raw) return [];
  const source = Array.isArray(raw) ? raw : Object.values(raw);

  return source
    .map((item) => {
      if (!item) return null;
      if (typeof item === "string") {
        return {
          text: item,
          level: "info",
          levelLabel: "Theo dõi",
          groupIds: [],
          metricIds: [],
        };
      }

      const level = normalizeRecommendationLevel(item.level || item.severity || item.priority);
      return {
        text: item.text || item.message || item.recommendation || "",
        level,
        levelLabel: level === "danger" ? "Cảnh báo" : level === "warn" ? "Lưu ý" : "Theo dõi",
        groupIds: normalizeStringArray(item.groups || item.groupIds || item.appliesTo),
        metricIds: normalizeStringArray(item.metrics || item.metricIds),
      };
    })
    .filter((item) => item && item.text);
}

function normalizeAnomalies(raw) {
  if (!raw) return [];
  const source = Array.isArray(raw) ? raw : Object.values(raw);

  return source
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const ts = toNumber(item.ts || item.timestamp);
      if (ts === null) return null;

      return {
        ts,
        value: toNumber(item.value),
        label: item.label || item.reason || item.type || "Anomaly",
        severity: item.severity || item.level || "warn",
        metricIds: normalizeStringArray(item.metricIds || item.metrics),
        metricKeys: normalizeStringArray(item.metricKeys || item.fields),
        groupIds: normalizeStringArray(item.groupIds || item.groups || item.appliesTo),
      };
    })
    .filter(Boolean);
}

function normalizeStringArray(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.map((item) => String(item)).filter(Boolean);
  return [String(raw)].filter(Boolean);
}

function normalizeRecommendationLevel(raw) {
  const normalized = String(raw || "").trim().toLowerCase();
  if (["critical", "danger", "high", "error"].includes(normalized)) return "danger";
  if (["warn", "warning", "medium"].includes(normalized)) return "warn";
  return "info";
}

function normalizeHistoryCollection(collection) {
  if (!collection) return [];

  if (Array.isArray(collection)) {
    return collection
      .map((record) => normalizeHistoryRecord(record, record?.ts))
      .filter(Boolean)
      .sort((left, right) => left.ts - right.ts);
  }

  if (typeof collection === "object") {
    return Object.entries(collection)
      .map(([key, value]) => normalizeHistoryRecord(value, key))
      .filter(Boolean)
      .sort((left, right) => left.ts - right.ts);
  }

  return [];
}

function normalizeHistoryRecord(record, fallbackTs) {
  if (!record || typeof record !== "object") return null;

  const ts = toNumber(record.ts) ?? toNumber(fallbackTs);
  if (ts === null) return null;

  const normalized = { ts };
  for (const [key, value] of Object.entries(record)) {
    if (key === "ts") continue;
    normalized[key] = typeof value === "number" ? value : toNumber(value) ?? value;
  }

  return normalized;
}

function createEmptyResult() {
  return {
    meta: normalizeMeta(null),
    latest: {
      air: {},
      soil: {},
      npk: {},
      weather: {},
    },
    history: {
      air: [],
      soil: [],
      npk: [],
      weather: [],
    },
    pipeline: normalizePipeline(null),
    analysis: normalizeAnalysis(null),
  };
}

function createHistoryMaps() {
  return {
    air: new Map(),
    soil: new Map(),
    npk: new Map(),
    weather: new Map(),
  };
}

function buildSampleResult() {
  const quarterStep = 15 * 60;
  const hourStep = 60 * 60;
  const latestTs = Math.floor(Date.now() / 1000 / quarterStep) * quarterStep;
  const startTs = latestTs - 72 * hourStep;
  const forecastEndTs = latestTs + 6 * hourStep;

  const air = [];
  const soil = [];
  const npk = [];
  const weather = [];
  const forecastAir = [];
  const forecastSoil = [];
  const forecastNpk = [];

  for (let ts = startTs, index = 0; ts <= latestTs; ts += quarterStep, index += 1) {
    const heatWave = Math.sin(index / 11) * 2.8 + Math.cos(index / 32) * 0.9;
    const humidityWave = 78 + Math.sin(index / 15) * 10 - Math.cos(index / 8) * 4;
    const soilHumidity = 63 + Math.sin(index / 21) * 6 - Math.max(0, Math.sin(index / 7)) * 2.5;
    const soilTemperature = 29.6 + Math.sin(index / 18) * 1.4 + Math.cos(index / 25) * 0.5;
    const ph = 6.55 + Math.sin(index / 27) * 0.35;
    const ec = 590 + Math.cos(index / 20) * 80 + Math.sin(index / 8) * 30;
    const nitrogen = 88 + Math.sin(index / 13) * 22 + Math.cos(index / 29) * 6;
    const phosphorus = 228 + Math.cos(index / 17) * 42 + Math.sin(index / 31) * 16;
    const potassium = 210 + Math.sin(index / 19) * 38 + Math.cos(index / 11) * 14;

    air.push({
      ts,
      temperature_c: roundNumber(29.1 + heatWave, 2),
      humidity_pct: roundNumber(clamp(humidityWave, 56, 99.99), 2),
    });

    soil.push({
      ts,
      temperature_c: roundNumber(soilTemperature, 2),
      humidity_pct: roundNumber(clamp(soilHumidity, 44, 82), 2),
      ph: roundNumber(clamp(ph, 5.4, 7.4), 2),
      ec_us_cm: roundNumber(clamp(ec, 360, 760), 1),
    });

    npk.push({
      ts,
      n_ppm: roundNumber(clamp(nitrogen, 42, 128), 1),
      p_ppm: roundNumber(clamp(phosphorus, 142, 334), 1),
      k_ppm: roundNumber(clamp(potassium, 138, 320), 1),
    });
  }

  for (let ts = startTs, index = 0; ts <= latestTs; ts += hourStep, index += 1) {
    const rainPulse =
      index % 17 === 0 ? 1.4 : index % 11 === 0 ? 0.5 : Math.max(0, Math.sin(index / 6) * 0.16);

    weather.push({
      ts,
      temperature_c: roundNumber(28.1 + Math.sin(index / 9) * 3.2, 2),
      humidity_pct: roundNumber(clamp(76 + Math.cos(index / 10) * 14, 45, 98), 2),
      rain_mm: roundNumber(rainPulse, 2),
      cloud_cover_pct: roundNumber(clamp(62 + Math.sin(index / 5) * 30, 4, 100), 1),
    });
  }

  const lastAir = air[air.length - 1];
  const lastSoil = soil[soil.length - 1];
  const lastNpk = npk[npk.length - 1];

  for (let ts = latestTs + quarterStep, step = 1; ts <= forecastEndTs; ts += quarterStep, step += 1) {
    const tempValue = roundNumber(lastAir.temperature_c + Math.sin(step / 3) * 0.7 - 0.12 * step, 2);
    const humidityValue = roundNumber(clamp(lastAir.humidity_pct - step * 1.2 + Math.cos(step / 2) * 2.1, 46, 95), 2);
    const soilTempValue = roundNumber(lastSoil.temperature_c - Math.sin(step / 4) * 0.5, 2);
    const soilHumidityValue = roundNumber(clamp(lastSoil.humidity_pct - step * 0.8, 34, 80), 2);
    const phValue = roundNumber(lastSoil.ph - step * 0.01, 2);
    const ecValue = roundNumber(lastSoil.ec_us_cm + step * 6.5, 1);
    const nValue = roundNumber(lastNpk.n_ppm - step * 1.5, 1);
    const pValue = roundNumber(lastNpk.p_ppm - step * 2.6, 1);
    const kValue = roundNumber(lastNpk.k_ppm + step * 1.1, 1);

    forecastAir.push({
      ts,
      temperature_c: tempValue,
      temperature_c_lower: roundNumber(tempValue - 0.5, 2),
      temperature_c_upper: roundNumber(tempValue + 0.5, 2),
      humidity_pct: humidityValue,
      humidity_pct_lower: roundNumber(humidityValue - 4, 2),
      humidity_pct_upper: roundNumber(humidityValue + 4, 2),
    });

    forecastSoil.push({
      ts,
      temperature_c: soilTempValue,
      temperature_c_lower: roundNumber(soilTempValue - 0.4, 2),
      temperature_c_upper: roundNumber(soilTempValue + 0.4, 2),
      humidity_pct: soilHumidityValue,
      humidity_pct_lower: roundNumber(soilHumidityValue - 3.2, 2),
      humidity_pct_upper: roundNumber(soilHumidityValue + 3.2, 2),
      ph: phValue,
      ph_lower: roundNumber(phValue - 0.05, 2),
      ph_upper: roundNumber(phValue + 0.05, 2),
      ec_us_cm: ecValue,
      ec_us_cm_lower: roundNumber(ecValue - 18, 1),
      ec_us_cm_upper: roundNumber(ecValue + 18, 1),
    });

    forecastNpk.push({
      ts,
      n_ppm: nValue,
      n_ppm_lower: roundNumber(nValue - 3, 1),
      n_ppm_upper: roundNumber(nValue + 3, 1),
      p_ppm: pValue,
      p_ppm_lower: roundNumber(pValue - 5, 1),
      p_ppm_upper: roundNumber(pValue + 5, 1),
      k_ppm: kValue,
      k_ppm_lower: roundNumber(kValue - 4, 1),
      k_ppm_upper: roundNumber(kValue + 4, 1),
    });
  }

  const anomalies = [
    {
      ts: latestTs - 2 * hourStep,
      label: "Độ ẩm đất giảm nhanh",
      severity: "warn",
      groups: ["soil"],
      metrics: ["soil_humidity"],
      value: soil[soil.length - 8]?.humidity_pct,
    },
    {
      ts: latestTs + 3 * hourStep,
      label: "Nguy cơ thiếu nước sáng mai",
      severity: "critical",
      groups: ["air", "soil"],
      metrics: ["air_humidity", "soil_humidity"],
    },
  ];

  return {
    meta: {
      snapshotVersion: new Date(latestTs * 1000).toISOString(),
      lastPublishedTs: latestTs,
      source: "demo-fallback",
    },
    pipeline: {
      state: "awaiting_analysis",
      detail: "Dữ liệu mẫu đang giả lập bước chờ server publish kết quả phân tích.",
      lastSyncTs: latestTs,
      lastAnalysisTs: latestTs - hourStep,
    },
    latest: {
      air: air[air.length - 1],
      soil: soil[soil.length - 1],
      npk: npk[npk.length - 1],
      weather: weather[weather.length - 1],
    },
    history: {
      air: objectFromHistory(air),
      soil: objectFromHistory(soil),
      npk: objectFromHistory(npk),
      weather: objectFromHistory(weather),
    },
    analysis: {
      modelName: "FT-Transformer demo",
      source: "server",
      status: "forecast_ready",
      priority: "warning",
      lastAnalysisTs: latestTs,
      diagnosis: {
        status: "ready",
        label: "moisture_or_intervention_context",
        displayLabel: "Am cao / can thiep tuoi-bon",
        abnormalProbability: 0.71,
        severity: "warning",
        ts: latestTs,
      },
      forecast: {
        air: objectFromHistory(forecastAir),
        soil: objectFromHistory(forecastSoil),
        npk: objectFromHistory(forecastNpk),
      },
      anomalies,
      recommendations: [
        {
          level: "warning",
          groups: ["soil"],
          text: "Cảnh báo: Độ ẩm đất tụt nhanh trong 2 giờ qua. Khuyến nghị: chuẩn bị tưới trước 05:00 nếu xu hướng dự báo giữ nguyên.",
        },
        {
          level: "info",
          groups: ["air"],
          text: "Nhiệt độ không khí sẽ giảm nhẹ về sáng, tiếp tục theo dõi cùng độ ẩm để tránh ngưng tụ.",
        },
      ],
    },
  };
}

function objectFromHistory(records) {
  return records.reduce((accumulator, record) => {
    accumulator[String(record.ts)] = record;
    return accumulator;
  }, {});
}

function getLatestPublishTs(result) {
  const fromMeta = toNumber(result.meta.lastPublishedTs);
  if (fromMeta !== null) return fromMeta;

  const candidates = HISTORY_GROUPS.map((group) => {
    const tail = result.history[group][result.history[group].length - 1];
    return tail?.ts || null;
  }).filter((value) => value !== null);

  return candidates.length ? Math.max(...candidates) : null;
}

function detectTrend(delta) {
  if (delta === null) return "unknown";
  if (Math.abs(delta) < 0.05) return "stable";
  return delta > 0 ? "rising" : "falling";
}

function describeTrend(trend, delta, unit) {
  if (trend === "unknown" || delta === null) return "Chưa đủ dữ liệu";
  if (trend === "stable") return `Ổn định (${formatSigned(delta, unit)})`;
  if (trend === "rising") return `Tăng (${formatSigned(delta, unit)})`;
  return `Giảm (${formatSigned(delta, unit)})`;
}

function describeTrendShort(trend) {
  if (trend === "rising") return "Đang tăng";
  if (trend === "falling") return "Đang giảm";
  if (trend === "stable") return "Ổn định";
  return "Chưa rõ";
}

function formatActiveRangeLabel(bounds) {
  if (state.rangeMode === "custom" && isCustomRangeValid()) {
    return `${formatDateOnly(bounds.minTs)} → ${formatDateOnly(bounds.maxTs)}`;
  }

  const preset = RANGE_PRESETS.find((item) => item.id === state.rangePresetId);
  return preset?.label || "24 giờ";
}

function formatPresetTrailingLabel() {
  const preset = RANGE_PRESETS.find((item) => item.id === state.rangePresetId);
  return preset?.label || "24 giờ";
}

function formatForecastHorizon(seconds) {
  if (!seconds) return "--";
  const hours = Math.round((seconds / 3600) * 10) / 10;
  return `+${hours} giờ`;
}

function hasFirebaseConfig(config) {
  if (!config) return false;
  const requiredKeys = ["apiKey", "authDomain", "databaseURL", "projectId", "appId"];

  return requiredKeys.every((key) => {
    const value = String(config[key] || "").trim();
    return value && !value.startsWith("YOUR_");
  });
}

function setTextNode(node, text) {
  if (node) node.textContent = text;
}

function formatMetric(value, unit) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  return `${roundNumber(value, digits)} ${unit}`.trim();
}

function formatAxisValue(value, unit) {
  if (unit === "0-1") return roundNumber(value, 2).toFixed(2);
  return formatMetric(value, unit);
}

function formatSigned(value, unit) {
  if (value === null || Number.isNaN(value)) return "--";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${roundNumber(value, 2)} ${unit}`.trim();
}

function formatTimestamp(ts) {
  if (!ts) return "--";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(ts * 1000));
}

function formatDateOnly(ts) {
  if (!ts) return "--";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
  }).format(new Date(ts * 1000));
}

function formatAxisTick(ts, spanSeconds) {
  if (!ts) return "--";

  if (spanSeconds <= 2 * 24 * 3600) {
    return new Intl.DateTimeFormat("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(ts * 1000));
  }

  if (spanSeconds <= 45 * 24 * 3600) {
    return new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit",
      month: "2-digit",
    }).format(new Date(ts * 1000));
  }

  return new Intl.DateTimeFormat("vi-VN", {
    month: "2-digit",
    year: "2-digit",
  }).format(new Date(ts * 1000));
}

function tsToDateInput(ts) {
  const date = new Date(ts * 1000);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateStringToStartTs(value) {
  const [year, month, day] = value.split("-").map(Number);
  return Math.floor(new Date(year, month - 1, day, 0, 0, 0, 0).getTime() / 1000);
}

function dateStringToEndTs(value) {
  const [year, month, day] = value.split("-").map(Number);
  return Math.floor(new Date(year, month - 1, day, 23, 59, 59, 999).getTime() / 1000);
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function roundNumber(value, digits) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toAlpha(hex, alpha) {
  const cleanHex = hex.replace("#", "");
  const value = Number.parseInt(cleanHex, 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}
