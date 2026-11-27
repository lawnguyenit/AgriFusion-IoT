// Single machine-readable copy of the `result/*` contract.
// Human-readable spec: docs/contracts/result.md. Keep the two in sync;
// Frontend/test/contract.test.js fails when sample data or UI metrics drift.

export const CONTRACT_VERSION = 1;

// Retention limits the backend publisher must enforce (see docs/contracts/result.md).
export const HISTORY_RETENTION_SECONDS = 7 * 24 * 3600;
export const HISTORY_MAX_POINTS = 800;

// Every value field: type "number" (finite). Absent key = no valid value (never 0, never null).
// `source` = canonical column in Backend Layer1 (canonical_fields.py).
export const HISTORY_GROUPS = {
  air: {
    source_note: "sht.*",
    fields: {
      temperature_c: { unit: "°C", source: "sht.temp_c", min: -40, max: 85 },
      humidity_pct: { unit: "%", source: "sht.humidity_pct", min: 0, max: 100 },
    },
  },
  soil: {
    source_note: "npk.* (soil probe)",
    fields: {
      temperature_c: { unit: "°C", source: "npk.soil_temp_c", min: -40, max: 85 },
      moisture_pct: { unit: "%", source: "npk.soil_moisture_pct", min: 0, max: 100 },
      ph: { unit: "pH", source: "npk.ph", min: 0, max: 14 },
      // Canonical catalog does not state the EC unit: chưa kiểm chứng.
      ec: { unit: "", unit_note: "chưa kiểm chứng", source: "npk.ec", min: 0, max: null },
    },
  },
  npk: {
    source_note: "npk.*_proxy",
    fields: {
      n_proxy: { unit: "proxy (uncalibrated)", source: "npk.n_proxy", min: 0, max: null },
      p_proxy: { unit: "proxy (uncalibrated)", source: "npk.p_proxy", min: 0, max: null },
      k_proxy: { unit: "proxy (uncalibrated)", source: "npk.k_proxy", min: 0, max: null },
    },
  },
};

export const GROUP_IDS = Object.keys(HISTORY_GROUPS);

export const META_FIELDS = {
  schema_version: { type: "int", required: true },
  published_ts: { type: "int", required: true, note: "epoch seconds, backend clock at publish" },
  latest_sample_ts: { type: "int", required: false, note: "max ts over all groups; absent when no data" },
  node_id: { type: "string", required: true },
  source: { type: "string", required: true },
};

const isInt = (v) => typeof v === "number" && Number.isInteger(v);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);

// Returns an array of error strings (empty = valid). `result` has the RTDB shape.
export function validateResult(result) {
  const errors = [];
  const rootKeys = ["meta", "latest", "history"];
  if (!result || typeof result !== "object") return ["result: not an object"];
  for (const key of Object.keys(result)) {
    if (!rootKeys.includes(key)) errors.push(`result.${key}: not in contract`);
  }

  const meta = result.meta;
  if (!meta || typeof meta !== "object") {
    errors.push("result.meta: missing");
  } else {
    for (const [name, spec] of Object.entries(META_FIELDS)) {
      const value = meta[name];
      if (value === undefined) {
        if (spec.required) errors.push(`result.meta.${name}: missing`);
        continue;
      }
      if (spec.type === "int" && !isInt(value)) errors.push(`result.meta.${name}: expected int`);
      if (spec.type === "string" && typeof value !== "string") errors.push(`result.meta.${name}: expected string`);
    }
    for (const key of Object.keys(meta)) {
      if (!(key in META_FIELDS)) errors.push(`result.meta.${key}: not in contract`);
    }
    if (isInt(meta.schema_version) && meta.schema_version !== CONTRACT_VERSION) {
      errors.push(`result.meta.schema_version: expected ${CONTRACT_VERSION}`);
    }
  }

  const checkRecord = (path, group, record, expectedKey) => {
    if (!record || typeof record !== "object") {
      errors.push(`${path}: not an object`);
      return;
    }
    if (!isInt(record.ts)) errors.push(`${path}.ts: expected int epoch seconds`);
    if (expectedKey !== undefined && String(record.ts) !== expectedKey) {
      errors.push(`${path}: key must equal String(ts)`);
    }
    const fields = HISTORY_GROUPS[group].fields;
    let valueCount = 0;
    for (const [name, value] of Object.entries(record)) {
      if (name === "ts") continue;
      const spec = fields[name];
      if (!spec) {
        errors.push(`${path}.${name}: not in contract`);
        continue;
      }
      if (!isNum(value)) {
        errors.push(`${path}.${name}: expected finite number (omit the key instead of null)`);
        continue;
      }
      valueCount += 1;
      if (spec.min !== null && value < spec.min) errors.push(`${path}.${name}: below ${spec.min}`);
      if (spec.max !== null && value > spec.max) errors.push(`${path}.${name}: above ${spec.max}`);
    }
    if (valueCount === 0) errors.push(`${path}: record has no value field (do not publish)`);
  };

  const latest = result.latest;
  if (!latest || typeof latest !== "object") {
    errors.push("result.latest: missing");
  } else {
    for (const group of Object.keys(latest)) {
      if (!HISTORY_GROUPS[group]) errors.push(`result.latest.${group}: not in contract`);
    }
    for (const group of GROUP_IDS) {
      if (latest[group] !== undefined) checkRecord(`result.latest.${group}`, group, latest[group]);
    }
  }

  const history = result.history;
  if (!history || typeof history !== "object") {
    errors.push("result.history: missing");
  } else {
    for (const group of Object.keys(history)) {
      if (!HISTORY_GROUPS[group]) errors.push(`result.history.${group}: not in contract`);
    }
    for (const group of GROUP_IDS) {
      const records = history[group];
      if (records === undefined) continue;
      const entries = Object.entries(records);
      if (entries.length > HISTORY_MAX_POINTS) {
        errors.push(`result.history.${group}: ${entries.length} points > ${HISTORY_MAX_POINTS}`);
      }
      const newest = Math.max(0, ...entries.map(([, r]) => (r && isInt(r.ts) ? r.ts : 0)));
      for (const [key, record] of entries) {
        checkRecord(`result.history.${group}.${key}`, group, record, key);
        if (record && isInt(record.ts) && newest - record.ts > HISTORY_RETENTION_SECONDS) {
          errors.push(`result.history.${group}.${key}: older than retention`);
        }
      }
      // latest must equal the newest history record when both exist.
      const tail = entries.map(([, r]) => r).filter((r) => r && isInt(r.ts)).sort((a, b) => a.ts - b.ts).pop();
      if (tail && latest && latest[group] && latest[group].ts !== tail.ts) {
        errors.push(`result.latest.${group}: ts differs from newest history record`);
      }
    }
  }

  return errors;
}

// Keep only contract fields of a raw RTDB record; returns null when ts is unusable.
export function pickRecord(group, raw, fallbackKey) {
  if (!raw || typeof raw !== "object") return null;
  const ts = Number.isFinite(Number(raw.ts)) ? Number(raw.ts) : Number(fallbackKey);
  if (!Number.isFinite(ts)) return null;
  const record = { ts };
  for (const name of Object.keys(HISTORY_GROUPS[group].fields)) {
    const value = raw[name];
    if (typeof value === "number" && Number.isFinite(value)) record[name] = value;
  }
  return record;
}
