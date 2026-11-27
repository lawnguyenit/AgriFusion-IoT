// Single source of demo data. Output has exactly the shape of `result/*`
// (docs/contracts/result.md) and is validated by Frontend/test/contract.test.js.
import { CONTRACT_VERSION } from "./contract.js";

const SAMPLE_STEP_SECONDS = 15 * 60; // firmware production sample interval
const SAMPLE_SPAN_HOURS = 72;

const round = (value, digits) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function buildSampleResult(nowSec = Math.floor(Date.now() / 1000)) {
  const latestTs = Math.floor(nowSec / SAMPLE_STEP_SECONDS) * SAMPLE_STEP_SECONDS;
  const startTs = latestTs - SAMPLE_SPAN_HOURS * 3600;
  const air = {};
  const soil = {};
  const npk = {};

  for (let ts = startTs, i = 0; ts <= latestTs; ts += SAMPLE_STEP_SECONDS, i += 1) {
    const heat = Math.sin(i / 11) * 2.8 + Math.cos(i / 32) * 0.9;
    const humidity = 78 + Math.sin(i / 15) * 10 - Math.cos(i / 8) * 4;
    const soilMoisture = 63 + Math.sin(i / 21) * 6 - Math.max(0, Math.sin(i / 7)) * 2.5;
    const soilTemp = 29.6 + Math.sin(i / 18) * 1.4 + Math.cos(i / 25) * 0.5;

    air[ts] = {
      ts,
      temperature_c: round(29.1 + heat, 2),
      humidity_pct: round(clamp(humidity, 56, 99.99), 2),
    };
    soil[ts] = {
      ts,
      temperature_c: round(soilTemp, 2),
      moisture_pct: round(clamp(soilMoisture, 44, 82), 2),
      ph: round(clamp(6.55 + Math.sin(i / 27) * 0.35, 5.4, 7.4), 2),
      ec: round(clamp(590 + Math.cos(i / 20) * 80 + Math.sin(i / 8) * 30, 360, 760), 1),
    };
    npk[ts] = {
      ts,
      n_proxy: round(clamp(88 + Math.sin(i / 13) * 22 + Math.cos(i / 29) * 6, 42, 128), 1),
      p_proxy: round(clamp(228 + Math.cos(i / 17) * 42 + Math.sin(i / 31) * 16, 142, 334), 1),
      k_proxy: round(clamp(210 + Math.sin(i / 19) * 38 + Math.cos(i / 11) * 14, 138, 320), 1),
    };
  }

  return {
    meta: {
      schema_version: CONTRACT_VERSION,
      published_ts: latestTs,
      latest_sample_ts: latestTs,
      node_id: "demo",
      source: "demo-sample",
    },
    latest: { air: air[latestTs], soil: soil[latestTs], npk: npk[latestTs] },
    history: { air, soil, npk },
  };
}
