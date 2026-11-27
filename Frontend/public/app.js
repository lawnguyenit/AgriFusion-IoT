import { initializeApp } from "https://www.gstatic.com/firebasejs/12.7.0/firebase-app.js";
import {
  getDatabase,
  limitToLast,
  onChildAdded,
  onChildRemoved,
  onValue,
  query,
  ref,
} from "https://www.gstatic.com/firebasejs/12.7.0/firebase-database.js";

import { HISTORY_MAX_POINTS, GROUP_IDS, pickRecord } from "./contract.js";
import { METRIC_DEFS, GROUP_DEFS } from "./dashboard-model.js";
import { buildSampleResult } from "./sample-data.js";

await Promise.resolve(window.AgriFusionDashboardConfigReady);

const dashboardConfig = window.AgriFusionDashboardConfig || {};

// Retention on the server is 7 days (docs/contracts/result.md), so longer presets are not offered.
const RANGE_PRESETS = [
  { id: "3h", label: "3 giờ", hours: 3 },
  { id: "6h", label: "6 giờ", hours: 6 },
  { id: "12h", label: "12 giờ", hours: 12 },
  { id: "24h", label: "24 giờ", hours: 24 },
  { id: "7d", label: "7 ngày", hours: 24 * 7 },
  { id: "all", label: "Toàn bộ dữ liệu đang giữ", hours: null },
];

const HISTORY_GROUPS = GROUP_IDS;
const VIEW_DEBOUNCE_MS = 180;
const LIVE_GRACE_SECONDS = 40 * 60; // 2 sample intervals (15 min) plus slack
const SNAPSHOT_POINT_LIMIT = 10;
const MIN_PRESET_CONTEXT_POINTS = 6;

const PIPELINE_STATES = {
  live_syncing: {
    key: "live_syncing",
    label: "Live Syncing",
    tone: "live",
    detail: "Đang nhận dữ liệu từ RTDB; bản ghi mới sẽ tự xuất hiện.",
  },
  stale: {
    key: "stale",
    label: "Dữ liệu cũ",
    tone: "awaiting",
    detail: "Kết nối RTDB ổn nhưng backend chưa publish bản ghi mới trong thời gian gần đây.",
  },
  no_data: {
    key: "no_data",
    label: "Chưa có dữ liệu",
    tone: "awaiting",
    detail: "Kết nối RTDB ổn nhưng chưa có dữ liệu dưới result/history.",
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
    detail: "Mất kết nối với cơ sở dữ liệu thời gian thực.",
  },
  demo: {
    key: "demo",
    label: "Dữ liệu mẫu",
    tone: "historical",
    detail: "Đang hiển thị dữ liệu mẫu nội bộ, chưa phải dữ liệu từ server.",
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
    applySnapshot(buildSampleResult(), "demo", "Chế độ demo: dữ liệu mẫu theo đúng hợp đồng result/*.");
    return;
  }

  if (!firebaseReady) {
    applySnapshot(
      buildSampleResult(),
      "demo",
      "Chưa có cấu hình Firebase hợp lệ, hệ thống dùng dữ liệu mẫu."
    );
    return;
  }

  try {
    connectFirebase();
  } catch (error) {
    console.error("Firebase init error", error);
    applySnapshot(
      buildSampleResult(),
      "demo",
      "Không khởi tạo được kết nối Firebase, hệ thống dùng dữ liệu mẫu."
    );
  }
}

// One loading strategy: per group, a limitToLast(N) query with onChildAdded/onChildRemoved.
// The query delivers the existing window once and then only new/removed children,
// so there is no separate full-tree get() and no replay of the same history.
function connectFirebase() {
  state.mode = "firebase";
  state.connectionDetail = "Đang kết nối tới nguồn dữ liệu trực tiếp.";
  state.data = createEmptyResult();
  state.historyIndex = createHistoryMaps();
  state.pendingHistory = createHistoryMaps();
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

  onValue(ref(db, `${resultPath}/meta`), (snapshot) => {
    state.data.meta = normalizeMeta(snapshot.exists() ? snapshot.val() : null);
    scheduleRender();
  });

  onValue(ref(db, `${resultPath}/latest`), (snapshot) => {
    state.data.latest = normalizeLatest(snapshot.exists() ? snapshot.val() : null, state.data.history);
    scheduleRender();
  });

  for (const group of HISTORY_GROUPS) {
    const windowQuery = query(ref(db, `${resultPath}/history/${group}`), limitToLast(HISTORY_MAX_POINTS));
    onChildAdded(windowQuery, (snapshot) => {
      if (!snapshot.key) return;
      queueHistoryRecord(group, snapshot.key, snapshot.val());
    });
    onChildRemoved(windowQuery, (snapshot) => {
      if (!snapshot.key) return;
      removeHistoryRecord(group, snapshot.key);
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
  const record = pickRecord(group, payload, key);
  if (!record) return;
  state.pendingHistory[group].set(record.ts, record);
  flushPendingHistory();
}

function removeHistoryRecord(group, key) {
  const ts = Number(key);
  if (!Number.isFinite(ts)) return;
  state.pendingHistory[group].delete(ts);
  state.historyIndex[group].delete(ts);
  flushPendingHistory();
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
  const pipelineState = derivePipelineState(historicalBounds);

  renderPipelineState(pipelineState, historicalBounds);
  renderMainChart(chartModel);
  renderSummaryView(chartModel);
  renderSnapshotView(globalBounds);
  renderSideViews();
}

function buildChartModel(historicalBounds) {
  const group = getSelectedGroup();
  const resolvedScaleMode = group.forceNormalized ? "normalized" : state.scaleMode;
  const chartMode = state.sideView;
  const effectiveBounds = chartMode === "snapshot"
    ? getSnapshotBounds(historicalBounds)
    : historicalBounds;

  const activeSeries = group.metricIds
    .map((metricId) => buildSeries(metricMap[metricId], effectiveBounds, chartMode))
    .filter((series) => series && series.historyPoints.length);

  const xBounds = { minTs: effectiveBounds.minTs, maxTs: effectiveBounds.maxTs };
  const pointCount = Math.max(0, ...activeSeries.map((series) => series.historyPoints.length));

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

  return {
    metric,
    historyPoints: chartMode === "snapshot" ? historyPoints.slice(-SNAPSHOT_POINT_LIMIT) : historyPoints,
    stats: summarizeSeries(metric, historyPoints),
  };
}

function summarizeSeries(metric, historyPoints) {
  const values = historyPoints.map((point) => point.value);

  if (!values.length) {
    return { current: null, min: null, max: null, avg: null, delta: null, trend: "unknown", unit: metric.unit };
  }

  const current = values[values.length - 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const delta = values.length > 1 ? current - values[0] : null;

  return { current, min, max, avg, delta, trend: detectTrend(delta), unit: metric.unit };
}

function getAxisExtents(group, seriesList, scaleMode) {
  if (scaleMode === "normalized" || group.mode === "overview") {
    return {
      left: { min: 0, max: 1, label: "Chuẩn hóa", unit: "0-1" },
      right: null,
    };
  }

  const axisBuckets = { left: [], right: [] };

  for (const series of seriesList) {
    const bucket = axisBuckets[series.metric.axisId] || axisBuckets.left;
    bucket.push(...series.historyPoints.map((point) => point.value));
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
  const normalizeExtent = getExtent(series.historyPoints.map((point) => point.value));

  const mapValue = (pointValue) => {
    if (pointValue === null) return null;
    return scaleMode === "normalized" ? normalizeValue(pointValue, normalizeExtent) : pointValue;
  };

  const historyPoints = series.historyPoints
    .map((point) => ({ ...point, plottedValue: mapValue(point.value) }))
    .filter((point) => point.plottedValue !== null);

  const axisExtent = scaleMode === "normalized"
    ? axisExtents.left
    : axisExtents[series.metric.axisId] || axisExtents.left;

  return {
    ...series,
    historyPoints,
    axisExtent,
    frame,
    historyPath: buildValuePath(historyPoints, axisExtent, frame, xBounds),
    lastHistoryPoint: buildLastPoint(historyPoints, axisExtent, frame, xBounds),
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
  setTextNode(document.getElementById("focusValue"), `${groupSeries.length} đường dữ liệu`);

  const scaleSentence = chartModel.scaleMode === "normalized"
    ? "Biểu đồ đang ở chế độ chuẩn hóa xu hướng để so sánh hình dạng biến động."
    : "Biểu đồ đang ở chế độ giá trị tuyệt đối với trục Y đúng đơn vị kỹ thuật.";

  setTextNode(document.getElementById("focusDescription"), `${group.description} ${scaleSentence}`);

  const focusStats = document.getElementById("focusStats");
  if (!focusStats) return;

  const rangeCard = `
    <article class="focus-stat">
      <span class="focus-stat__label">Khoảng đang xem</span>
      <strong class="focus-stat__value">${escapeHtml(formatActiveRangeLabel(chartModel.historicalBounds))}</strong>
    </article>
    <article class="focus-stat">
      <span class="focus-stat__label">Số mẫu</span>
      <strong class="focus-stat__value">${escapeHtml(String(chartModel.pointCount))}</strong>
    </article>
  `;

  focusStats.innerHTML = groupSeries.map((series) => `
    <article class="focus-stat">
      <span class="focus-stat__label">${escapeHtml(series.metric.shortLabel)}</span>
      <strong class="focus-stat__value">${escapeHtml(formatMetric(series.stats.current, series.metric.unit))}</strong>
    </article>
  `).join("") + rangeCard;
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

function renderSideViews() {
  const summaryView = document.getElementById("summaryView");
  const snapshotView = document.getElementById("snapshotView");
  if (!summaryView || !snapshotView) return;

  summaryView.classList.toggle("insight-view--hidden", state.sideView !== "summary");
  snapshotView.classList.toggle("insight-view--hidden", state.sideView !== "snapshot");
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

  metaLines.push(
    `${escapeHtml(formatTimestamp(chartModel.xBounds.minTs))} → ${escapeHtml(formatTimestamp(chartModel.xBounds.maxTs))}`
  );

  return metaLines.join("<br />");
}

function buildLegendCard(series) {
  return `
    <article class="legend-chip">
      <div class="legend-chip__title">
        <span class="legend-chip__dot" style="background:${series.metric.color}"></span>
        <span>${escapeHtml(series.metric.label)}</span>
      </div>
      <div class="legend-chip__meta-row">
        <div class="legend-chip__meta">${escapeHtml(describeTrend(series.stats.trend, series.stats.delta, series.metric.unit))}</div>
      </div>
      <div class="legend-chip__value">${escapeHtml(formatMetric(series.stats.current, series.metric.unit))}</div>
      <div class="legend-chip__meta">
        ${escapeHtml(`Min ${formatMetric(series.stats.min, series.metric.unit)} · Max ${formatMetric(series.stats.max, series.metric.unit)}`)}
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

  const historicalPaths = chartModel.series.map((series) => `
    ${series.historyPath ? `<path class="chart-series ${chartModel.chartMode === "snapshot" ? "chart-series--snapshot" : ""}" d="${series.historyPath}" stroke="${series.metric.color}"></path>` : ""}
    ${series.lastHistoryPoint ? `<circle class="chart-point" cx="${series.lastHistoryPoint.x}" cy="${series.lastHistoryPoint.y}" r="4.8" fill="${series.metric.color}"></circle>` : ""}
  `).join("");

  return `
    <g>
      ${horizontalGrid.join("")}
      ${verticalGrid.join("")}
      <line class="chart-domain-line" x1="${frame.padding.left}" y1="${height - frame.padding.bottom}" x2="${width - frame.padding.right}" y2="${height - frame.padding.bottom}"></line>
      ${historicalPaths}
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

function derivePipelineState(historicalBounds) {
  if (state.mode !== "firebase") {
    return { ...PIPELINE_STATES.demo, detail: state.connectionDetail };
  }

  if (!state.connected) {
    return { ...PIPELINE_STATES.offline_error, detail: state.connectionDetail };
  }

  const latestTs = getLatestPublishTs(state.data);
  if (!latestTs) {
    return PIPELINE_STATES.no_data;
  }

  const nowSec = Math.floor(Date.now() / 1000);
  if (nowSec - latestTs > LIVE_GRACE_SECONDS) {
    return PIPELINE_STATES.stale;
  }

  if (historicalBounds.maxTs && historicalBounds.maxTs < latestTs - LIVE_GRACE_SECONDS) {
    return PIPELINE_STATES.historical_view;
  }

  return PIPELINE_STATES.live_syncing;
}

function getSnapshotBounds(bounds) {
  if (!bounds.minTs || !bounds.maxTs) return bounds;
  const fallbackSpan = 3 * 3600;
  return {
    minTs: Math.max(bounds.minTs, bounds.maxTs - fallbackSpan),
    maxTs: bounds.maxTs,
  };
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
  const normalizedHistory = {};
  for (const group of HISTORY_GROUPS) {
    normalizedHistory[group] = normalizeHistoryCollection(group, history[group]);
  }

  return {
    meta: normalizeMeta(raw?.meta),
    latest: normalizeLatest(raw?.latest, normalizedHistory),
    history: normalizedHistory,
  };
}

function normalizeMeta(raw) {
  return {
    schemaVersion: toNumber(raw?.schema_version),
    publishedTs: toNumber(raw?.published_ts),
    latestSampleTs: toNumber(raw?.latest_sample_ts),
    nodeId: typeof raw?.node_id === "string" ? raw.node_id : "",
    source: typeof raw?.source === "string" ? raw.source : "",
  };
}

function normalizeLatest(raw, history) {
  const latest = {};
  for (const group of HISTORY_GROUPS) {
    const fromRaw = pickRecord(group, raw?.[group], raw?.[group]?.ts);
    const tail = history[group]?.[history[group].length - 1];
    latest[group] = fromRaw || (tail ? { ...tail } : {});
  }
  return latest;
}

function normalizeHistoryCollection(group, collection) {
  if (!collection || typeof collection !== "object") return [];
  return Object.entries(collection)
    .map(([key, value]) => pickRecord(group, value, key))
    .filter(Boolean)
    .sort((left, right) => left.ts - right.ts);
}

function createEmptyResult() {
  const latest = {};
  const history = {};
  for (const group of HISTORY_GROUPS) {
    latest[group] = {};
    history[group] = [];
  }
  return { meta: normalizeMeta(null), latest, history };
}

function createHistoryMaps() {
  return Object.fromEntries(HISTORY_GROUPS.map((group) => [group, new Map()]));
}

function getLatestPublishTs(result) {
  const fromMeta = toNumber(result.meta.publishedTs);
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

