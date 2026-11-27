"""Publisher tests (no network): mapping, contract validity, retention, idempotency, CLI."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from agrifusion.publish import build_groups, build_plan, load_schema, validate_result
from agrifusion.publish.cli import run
from Backend.tests.architecture_graph import build_edges

SCHEMA = load_schema()
NOW = 1_800_000_000


def make_df(n: int = 6, start: int = 1_788_217_200, step: int = 900) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "record.id": f"Node2:{start + i * step}", "record.node_id": "Node2",
            "record.ts_sample": start + i * step, "record.is_demo": False, "record.excluded_reason": None,
            "sht.temp_c": 25.0 + i % 10, "sht.humidity_pct": 60.0 + i % 10, "sht.value_valid": True,
            "npk.soil_temp_c": 26.0, "npk.soil_temp_valid": True,
            "npk.soil_moisture_pct": 40.0, "npk.soil_moisture_valid": None,
            "npk.ph": 6.5, "npk.ph_valid": None, "npk.ec": 400.0, "npk.ec_valid": None,
            "npk.n_proxy": 30.0, "npk.p_proxy": 20.0, "npk.k_proxy": 10.0,
            "npk.n_proxy_valid": None, "npk.p_proxy_valid": True, "npk.k_proxy_valid": True,
        })
    return pd.DataFrame(rows)


class FakeClient:
    def __init__(self, tree=None):
        self.tree = tree
        self.updates: list[dict] = []

    def read(self, path):
        return copy.deepcopy(self.tree)

    def update(self, paths):
        self.updates.append(paths)
        for path, value in paths.items():
            parts = path.split("/")[1:]
            node = self.tree = self.tree or {}
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            if value is None:
                node.pop(parts[-1], None)
            else:
                node[parts[-1]] = copy.deepcopy(value)


def plan_for(df, remote=None, **kw):
    groups, node = build_groups(df, SCHEMA)
    return build_plan(groups, schema=SCHEMA, node_id=node, source="t", now_ts=NOW, remote=remote, **kw)


class MappingTests(unittest.TestCase):
    def test_tree_validates_and_omits_missing(self):
        df = make_df()
        df.loc[1, "sht.temp_c"] = float("nan")
        df.loc[2, "npk.ph"] = 99.0  # out of range -> key dropped
        df.loc[3, "npk.k_proxy_valid"] = False  # flag false -> key dropped
        df.loc[4, "record.is_demo"] = True
        df.loc[5, "record.excluded_reason"] = "bad"
        plan = plan_for(df)
        self.assertEqual(validate_result(plan.tree, SCHEMA), [])
        h = plan.tree["history"]
        base = 1_788_217_200
        self.assertNotIn("temperature_c", h["air"][str(base + 900)])
        self.assertNotIn("ph", h["soil"][str(base + 1800)])
        self.assertNotIn("k_proxy", h["npk"][str(base + 2700)])
        self.assertNotIn(str(base + 3600), h["air"])
        self.assertNotIn(str(base + 4500), h["air"])
        self.assertEqual(plan.tree["latest"]["air"]["ts"], base + 2700)
        self.assertNotIn(None, json.dumps(plan.tree).split())
        self.assertNotIn("null", json.dumps(plan.tree))
        self.assertEqual(plan.tree["meta"]["node_id"], "Node2")

    def test_sht_invalid_flag_drops_record(self):
        df = make_df(2)
        df.loc[1, "sht.value_valid"] = False
        groups, _ = build_groups(df, SCHEMA)
        self.assertEqual(len(groups["air"]), 1)
        self.assertEqual(len(groups["soil"]), 2)

    def test_empty_raises(self):
        df = make_df(2)
        df["record.is_demo"] = True
        with self.assertRaises(ValueError):
            plan_for(df)

    def test_golden_chain_output_validates(self):
        from Backend.tests.golden_chain_support import run_chain

        with tempfile.TemporaryDirectory() as tmp:
            settings = run_chain(Path(tmp))
            df = pd.read_parquet(settings.layer1_root / "canonical" / "telemetry_history.parquet")
            plan = plan_for(df)
        self.assertEqual(validate_result(plan.tree, SCHEMA), [])
        self.assertTrue(plan.tree["history"]["air"])

    def test_validator_rejects_bad_tree(self):
        tree = copy.deepcopy(plan_for(make_df()).tree)
        ts = next(iter(tree["history"]["air"]))
        tree["history"]["air"][ts]["humidity_pct"] = None
        tree["history"]["air"][ts]["n_ppm"] = 1
        tree["analysis"] = {}
        text = "\n".join(validate_result(tree, SCHEMA))
        self.assertIn("expected finite number", text)
        self.assertIn("n_ppm: not in contract", text)
        self.assertIn("result.analysis: not in contract", text)


class RetentionTests(unittest.TestCase):
    def test_cap_800(self):
        plan = plan_for(make_df(900, step=60))
        self.assertEqual(len(plan.tree["history"]["air"]), 800)
        newest = 1_788_217_200 + 899 * 60
        self.assertIn(str(newest), plan.tree["history"]["air"])
        self.assertNotIn(str(1_788_217_200), plan.tree["history"]["air"])
        self.assertEqual(validate_result(plan.tree, SCHEMA), [])

    def test_seven_days(self):
        plan = plan_for(make_df(12, step=86_400))  # 12 daily points
        air = plan.tree["history"]["air"]
        newest = 1_788_217_200 + 11 * 86_400
        self.assertEqual(len(air), 8)  # newest-7d is kept (inclusive), as the contract validator allows
        self.assertTrue(all(newest - int(k) <= 604_800 for k in air))

    def test_deletions_for_trimmed_remote_children(self):
        first = plan_for(make_df(5, step=86_400 * 2))
        remote = first.tree
        later = make_df(1, start=1_788_217_200 + 4 * 86_400 * 2 + 10 * 86_400)
        second = plan_for(later, remote=remote)
        deleted = [p for p, v in second.updates.items() if v is None]
        self.assertTrue(deleted)
        self.assertTrue(all(p.startswith("result/history/") for p in deleted))
        self.assertEqual(validate_result(second.tree, SCHEMA), [])


class IdempotencyTests(unittest.TestCase):
    def test_second_run_is_empty(self):
        df = make_df(20)
        client = FakeClient()
        first = plan_for(df, remote=client.read("result"))
        client.update(first.updates)
        second = plan_for(df, remote=client.read("result"))
        self.assertEqual(second.updates, {})
        # also later wall clock only changes published_ts -> still no change
        again = build_plan(*[build_groups(df, SCHEMA)[0]], schema=SCHEMA, node_id="Node2", source="t",
                           now_ts=NOW + 900, remote=client.read("result"))
        self.assertEqual(again.updates, {})

    def test_new_row_writes_only_delta(self):
        client = FakeClient()
        client.update(plan_for(make_df(5), remote=None).updates)
        plan = plan_for(make_df(6), remote=client.read("result"))
        history_paths = [p for p in plan.updates if "/history/" in p]
        self.assertEqual(len(history_paths), 3)  # one new child per group
        self.assertIn("result/meta", plan.updates)
        self.assertEqual(sum(1 for p in plan.updates if p.startswith("result/latest/")), 3)


class CliTests(unittest.TestCase):
    def _canon(self, tmp: Path) -> Path:
        path = tmp / "h.parquet"
        make_df(5).to_parquet(path)
        return path

    def test_dry_run_apply_out(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            src, out = self._canon(tmp), tmp / "tree.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(run(["--input", str(src), "--out", str(out)], now_ts=NOW), 0)
            self.assertIn("dry-run", buf.getvalue())
            self.assertEqual(validate_result(json.loads(out.read_text()), SCHEMA), [])
            client = FakeClient()
            with contextlib.redirect_stdout(io.StringIO()):
                run(["--input", str(src)], client=client, now_ts=NOW)
            self.assertEqual(client.updates, [])
            with contextlib.redirect_stdout(io.StringIO()):
                run(["--input", str(src), "--apply"], client=client, now_ts=NOW)
                run(["--input", str(src), "--apply"], client=client, now_ts=NOW + 5)
            self.assertEqual(len(client.updates), 1)  # second apply: no changes


class ArchitectureTests(unittest.TestCase):
    def test_only_cli_imports_publish(self):
        importers = {src for (src, dst) in build_edges() if dst == "publish"}
        self.assertEqual(importers, {"cli"})


if __name__ == "__main__":
    unittest.main()
