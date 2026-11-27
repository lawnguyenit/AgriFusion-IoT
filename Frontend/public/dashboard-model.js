// Metric and group definitions for the dashboard. Pure data, imported by app.js
// and checked against the contract by Frontend/test/contract.test.js.
import { HISTORY_GROUPS } from "./contract.js";

const unitOf = (group, field) => HISTORY_GROUPS[group].fields[field].unit;

export const METRIC_DEFS = [
  { id: "air_temperature", label: "Nhiệt độ không khí", shortLabel: "Nhiệt độ KK", unit: unitOf("air", "temperature_c"), color: "#d6a33b", historyKey: "air", metricKey: "temperature_c", axisId: "left" },
  { id: "air_humidity", label: "Độ ẩm không khí", shortLabel: "Độ ẩm KK", unit: unitOf("air", "humidity_pct"), color: "#2f8f83", historyKey: "air", metricKey: "humidity_pct", axisId: "right" },
  { id: "soil_temperature", label: "Nhiệt độ đất", shortLabel: "Nhiệt độ đất", unit: unitOf("soil", "temperature_c"), color: "#cf7243", historyKey: "soil", metricKey: "temperature_c", axisId: "left" },
  { id: "soil_moisture", label: "Độ ẩm đất", shortLabel: "Độ ẩm đất", unit: unitOf("soil", "moisture_pct"), color: "#4d95bf", historyKey: "soil", metricKey: "moisture_pct", axisId: "right" },
  { id: "soil_ph", label: "pH đất", shortLabel: "pH đất", unit: unitOf("soil", "ph"), color: "#7e9946", historyKey: "soil", metricKey: "ph", axisId: "left" },
  { id: "soil_ec", label: "EC đất (chưa rõ đơn vị)", shortLabel: "EC đất", unit: unitOf("soil", "ec"), color: "#b35f70", historyKey: "soil", metricKey: "ec", axisId: "right" },
  { id: "npk_n", label: "Nitơ (proxy)", shortLabel: "N proxy", unit: "proxy", color: "#719d4b", historyKey: "npk", metricKey: "n_proxy", axisId: "left" },
  { id: "npk_p", label: "Phốt pho (proxy)", shortLabel: "P proxy", unit: "proxy", color: "#e0aa39", historyKey: "npk", metricKey: "p_proxy", axisId: "left" },
  { id: "npk_k", label: "Kali (proxy)", shortLabel: "K proxy", unit: "proxy", color: "#d97b48", historyKey: "npk", metricKey: "k_proxy", axisId: "left" },
];

export const GROUP_DEFS = [
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
    axes: { left: { label: "Nhiệt độ", unit: "°C" }, right: { label: "Độ ẩm", unit: "%" } },
  },
  {
    id: "soil",
    label: "Đất",
    description: "Nhiệt độ đất và độ ẩm đất để theo dõi nền môi trường canh tác.",
    metricIds: ["soil_temperature", "soil_moisture"],
    axes: { left: { label: "Nhiệt độ", unit: "°C" }, right: { label: "Độ ẩm", unit: "%" } },
  },
  {
    id: "chemistry",
    label: "pH & EC đất",
    description: "pH đất và EC đất. Đơn vị EC chưa được kiểm chứng nên trục EC không ghi đơn vị.",
    metricIds: ["soil_ph", "soil_ec"],
    axes: { left: { label: "pH", unit: "pH" }, right: { label: "EC (chưa rõ đơn vị)", unit: "" } },
  },
  {
    id: "npk",
    label: "NPK (proxy)",
    description: "Ba chỉ số proxy N/P/K từ cảm biến, chưa hiệu chuẩn: đây không phải nồng độ ppm.",
    metricIds: ["npk_n", "npk_p", "npk_k"],
    axes: { left: { label: "NPK proxy", unit: "proxy" }, right: null },
  },
];
