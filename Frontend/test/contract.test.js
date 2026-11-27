import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  CONTRACT_VERSION,
  HISTORY_GROUPS,
  HISTORY_MAX_POINTS,
  validateResult,
  pickRecord,
} from "../public/contract.js";
import { buildSampleResult } from "../public/sample-data.js";
import { METRIC_DEFS, GROUP_DEFS } from "../public/dashboard-model.js";

const FIXED_NOW = 1_800_000_000;

test("demo sample data follows the contract exactly", () => {
  const errors = validateResult(buildSampleResult(FIXED_NOW));
  assert.deepEqual(errors, []);
});

test("sample data is deterministic and within retention/size limits", () => {
  const a = buildSampleResult(FIXED_NOW);
  const b = buildSampleResult(FIXED_NOW);
  assert.deepEqual(a, b);
  for (const group of Object.keys(HISTORY_GROUPS)) {
    const count = Object.keys(a.history[group]).length;
    assert.ok(count > 0 && count <= HISTORY_MAX_POINTS, `${group}: ${count}`);
  }
  assert.equal(a.meta.schema_version, CONTRACT_VERSION);
});

test("validator rejects out-of-contract data", () => {
  const bad = buildSampleResult(FIXED_NOW);
  const ts = Object.keys(bad.history.air)[0];
  bad.history.air[ts].n_ppm = 1; // legacy field name
  bad.history.air[ts].humidity_pct = null; // null must be omitted
  bad.history.weather = {}; // out of contract group
  bad.analysis = {}; // out of contract root
  const errors = validateResult(bad).join("\n");
  assert.match(errors, /n_ppm: not in contract/);
  assert.match(errors, /humidity_pct: expected finite number/);
  assert.match(errors, /history\.weather: not in contract/);
  assert.match(errors, /result\.analysis: not in contract/);
});

test("NPK fields are proxies and EC unit is not asserted", () => {
  assert.deepEqual(Object.keys(HISTORY_GROUPS.npk.fields), ["n_proxy", "p_proxy", "k_proxy"]);
  for (const spec of Object.values(HISTORY_GROUPS.npk.fields)) {
    assert.equal(spec.unit, "proxy (uncalibrated)");
  }
  assert.equal(HISTORY_GROUPS.soil.fields.ec.unit, "");
  assert.equal(HISTORY_GROUPS.soil.fields.ec.unit_note, "chưa kiểm chứng");
});

test("every UI metric maps to a contract field with a consistent unit", () => {
  for (const metric of METRIC_DEFS) {
    const spec = HISTORY_GROUPS[metric.historyKey]?.fields[metric.metricKey];
    assert.ok(spec, `${metric.id}: ${metric.historyKey}.${metric.metricKey} not in contract`);
    assert.ok(spec.unit.startsWith(metric.unit), `${metric.id}: unit ${metric.unit} vs ${spec.unit}`);
  }
  const ids = new Set(METRIC_DEFS.map((m) => m.id));
  for (const group of GROUP_DEFS) {
    for (const id of group.metricIds) assert.ok(ids.has(id), `${group.id}: unknown metric ${id}`);
  }
});

test("pickRecord keeps only contract fields", () => {
  const record = pickRecord("npk", { ts: 5, n_proxy: 1, n_ppm: 2, junk: 3, p_proxy: "x" });
  assert.deepEqual(record, { ts: 5, n_proxy: 1 });
  assert.equal(pickRecord("air", { temperature_c: 1 }, "abc"), null);
});

test("app.js/index.html contain no out-of-contract result paths", () => {
  const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  for (const forbidden of ["analysis", "forecast", "recommendations", "anomalies", "weather", "diagnosis", "n_ppm", "ec_us_cm"]) {
    assert.ok(!app.includes(forbidden), `app.js still mentions ${forbidden}`);
  }
  assert.ok(!/ppm/i.test(app + html), "UI still mentions ppm");
  assert.ok(!app.includes('get(ref(db, resultPath))'), "full-tree get() reintroduced");
});

test("database.rules.json: public read only under result, no public write", () => {
  const rules = JSON.parse(readFileSync(new URL("../database.rules.json", import.meta.url), "utf8")).rules;
  assert.equal(rules[".read"], false);
  assert.equal(rules[".write"], false);
  assert.equal(rules.result[".read"], true);
  assert.equal(rules.result[".write"], false);
  const walk = (node, path) => {
    for (const [key, value] of Object.entries(node)) {
      if (key === ".read" || key === ".write") {
        if (value === true) assert.ok(path === "result" && key === ".read", `public ${key} at ${path || "/"}`);
      } else if (value && typeof value === "object") {
        walk(value, path ? `${path}/${key}` : key);
      }
    }
  };
  walk(rules, "");
  for (const device of ["Node2", "debug", "control", "ops"]) {
    assert.match(rules[device][".read"], /auth != null/);
    assert.match(rules[device][".write"], /auth != null/);
  }
});
