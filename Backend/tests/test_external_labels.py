from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.external_labels.contracts import ExternalLabelConfig
from Backend.Benchmark.external_labels.engine import build_candidate_labels
from Backend.Benchmark.external_labels.pipeline import run_external_label_candidates
from Backend.Benchmark.external_labels.profiles import PROFILES


class ExternalLabelCandidateTests(unittest.TestCase):
    def test_pipeline_verifies_source_and_only_reads_allowlisted_label_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            intake_dir = root / "intake"
            intake_dir.mkdir()
            raw_manifest_path = root / "raw_manifest.json"
            raw_manifest_path.write_text("{}", encoding="utf-8")
            raw_hash = hashlib.sha256(raw_manifest_path.read_bytes()).hexdigest()
            canonical_path = intake_dir / "canonical.parquet"
            canonical = pd.DataFrame(
                {
                    "sample_id": [f"s{i}" for i in range(9)],
                    "timestamp": pd.date_range("2023-06-29", periods=9, freq="10min", tz="UTC"),
                    "entity_id": ["line_1"] * 9,
                    "soil_moisture_pct": [0, 0, 0, 0, 20, 20, 20, 20, 20],
                    "criterion.unrelated": [999] * 9,
                    "water_volume_m3": [123] * 9,
                }
            )
            canonical.to_parquet(canonical_path, index=False)
            manifest_path = intake_dir / "run_manifest.json"
            manifest = {
                "dataset_id": "stuard_tomato_irrigation_2023",
                "run_id": "intake-fixture",
                "raw_manifest_path": str(raw_manifest_path),
                "raw_manifest_sha256": raw_hash,
                "dataset_metadata": {"doi": "fixture"},
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            catalog = [
                {"path": canonical_path.name, "sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest()},
                {"path": manifest_path.name, "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()},
            ]
            (intake_dir / "artifact_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            result = run_external_label_candidates(
                ExternalLabelConfig(
                    canonical_path=canonical_path,
                    intake_manifest_path=manifest_path,
                    output_root=root / "labels",
                    tail_shares=(0.20,),
                    tau_minutes=(30,),
                )
            )
            labels = pd.read_parquet(result.candidate_labels_path)
            saved_manifest = json.loads((result.output_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(labels), len(canonical))
            self.assertFalse(any(column.startswith("criterion.") for column in labels.columns))
            self.assertNotIn("water_volume_m3", labels.columns)
            self.assertEqual(saved_manifest["canonical_sha256"], hashlib.sha256(canonical_path.read_bytes()).hexdigest())
            self.assertFalse(saved_manifest["primary_candidate_selected"])

    def test_stuard_uses_lower_tail_tau_cadence_and_unknown_for_short_runs(self) -> None:
        source = pd.DataFrame(
            {
                "sample_id": [f"s{i}" for i in range(7)],
                "timestamp": pd.date_range("2023-06-29", periods=7, freq="10min", tz="UTC"),
                "entity_id": ["line_1"] * 7,
                "soil_moisture_pct": [0, 0, 0, 0, 20, 20, None],
            }
        )
        config = ExternalLabelConfig(
            canonical_path=Path("canonical.parquet"),
            intake_manifest_path=Path("run_manifest.json"),
            output_root=Path("out"),
            tail_shares=(0.20,),
            tau_minutes=(30, 45),
        )
        labels, registry, cadence, support, calibration = build_candidate_labels(
            source, PROFILES["stuard_tomato_irrigation_2023"], config
        )
        q20_tau30 = "label_soil_moisture_low_q20_tau030m"
        q20_tau45 = "label_soil_moisture_low_q20_tau045m"
        self.assertEqual(labels[q20_tau30].fillna(-1).tolist(), [-1, -1, 1, 1, 0, 0, -1])
        self.assertEqual(labels[q20_tau45].fillna(-1).tolist(), [-1, -1, -1, -1, 0, 0, -1])
        self.assertEqual(labels["joint_label_soil_moisture_low_q20_tau030m"].tolist(), [
            "UNRES", "UNRES", "LOW_MOISTURE", "LOW_MOISTURE", "REF", "REF", "UNRES",
        ])
        self.assertEqual(int(cadence.iloc[0]["persistence_k"]), 3)
        self.assertEqual(int(cadence.loc[cadence["tau_minutes"].eq(45), "persistence_k"].iloc[0]), 5)
        self.assertEqual(int(support.loc[support["tau_minutes"].eq(30), "positive_event_count"].iloc[0]), 1)
        self.assertFalse(calibration["primary_candidate_selected"])
        self.assertEqual(registry.iloc[0]["candidate_status"], "SENSITIVITY_CANDIDATE_NOT_PRIMARY")

    def test_uci_keeps_independent_heads_and_ref_requires_both_negative(self) -> None:
        n = 20
        times = pd.date_range("2004-03-10", periods=n, freq="h")
        co = list(range(100, 96, -1)) + list(range(1, 17))
        nox = list(range(1, 3)) + list(range(100, 96, -1)) + list(range(3, 17))
        source = pd.DataFrame(
            {
                "sample_id": [f"u{i}" for i in range(n)],
                "timestamp": times,
                "sensor.co": co,
                "sensor.nox": [*nox[:-1], None],
            }
        )
        config = ExternalLabelConfig(
            canonical_path=Path("canonical.parquet"),
            intake_manifest_path=Path("run_manifest.json"),
            output_root=Path("out"),
            tail_shares=(0.20,),
            tau_minutes=(30,),
        )
        labels, registry, _, support, _ = build_candidate_labels(
            source, PROFILES["uci_air_quality_360"], config
        )
        joint = labels["joint_label_joint_q20_tau030m"]
        self.assertIn("CO", set(joint))
        self.assertIn("NOX", set(joint))
        self.assertIn("CO+NOX", set(joint))
        self.assertIn("REF", set(joint))
        self.assertEqual(joint.iloc[-1], "UNRES")
        self.assertTrue(labels["label_co_q20_tau030m"].eq(1).any())
        self.assertTrue(labels["label_nox_q20_tau030m"].eq(1).any())
        self.assertTrue(registry["joint_label_column"].eq("joint_label_joint_q20_tau030m").all())
        all_rows = support.loc[support["scope"].eq("ALL"), "row_count"]
        self.assertEqual(int(all_rows.sum()), n * 2)

    def test_threshold_is_fit_only_from_initial_calibration_interval(self) -> None:
        times = pd.date_range("2023-01-01", periods=30, freq="1D", tz="UTC")
        source = pd.DataFrame(
            {
                "sample_id": [f"s{i}" for i in range(len(times))],
                "timestamp": times,
                "entity_id": ["line_1"] * len(times),
                "soil_moisture_pct": [float(value) for value in range(30)],
            }
        )
        config = ExternalLabelConfig(
            canonical_path=Path("canonical.parquet"),
            intake_manifest_path=Path("run_manifest.json"),
            output_root=Path("out"),
            tail_shares=(0.10,),
            tau_minutes=(30,),
        )
        _, registry, _, _, calibration = build_candidate_labels(
            source, PROFILES["stuard_tomato_irrigation_2023"], config
        )
        self.assertEqual(int(registry.iloc[0]["threshold_fit_count"]), 21)
        self.assertEqual(float(registry.iloc[0]["threshold_value"]), 2.0)
        self.assertEqual(calibration["calibration_days"], 21)

    def test_gap_outside_strict_cadence_bounds_resets_persistence(self) -> None:
        source = pd.DataFrame(
            {
                "sample_id": [f"s{i}" for i in range(4)],
                "timestamp": pd.to_datetime(
                    [
                        "2023-06-29T00:00:00Z",
                        "2023-06-29T00:10:00Z",
                        "2023-06-29T00:40:00Z",
                        "2023-06-29T00:50:00Z",
                    ]
                ),
                "entity_id": ["line_1"] * 4,
                "soil_moisture_pct": [0, 0, 0, 0],
            }
        )
        config = ExternalLabelConfig(
            canonical_path=Path("canonical.parquet"),
            intake_manifest_path=Path("run_manifest.json"),
            output_root=Path("out"),
            tail_shares=(0.20,),
            tau_minutes=(30,),
        )
        labels, _, _, support, _ = build_candidate_labels(
            source, PROFILES["stuard_tomato_irrigation_2023"], config
        )
        self.assertTrue(labels["label_soil_moisture_low_q20_tau030m"].isna().all())
        all_scope = support.loc[support["scope"].eq("ALL"), "positive_event_count"]
        self.assertEqual(int(all_scope.iloc[0]), 0)

    def test_criterion_fields_cannot_enter_label_engine(self) -> None:
        source = pd.DataFrame(
            {
                "sample_id": ["a", "b"],
                "timestamp": pd.date_range("2024-01-01", periods=2, freq="h"),
                "sensor.co": [1, 2],
                "sensor.nox": [3, 4],
                "criterion.co_gt_mg_m3": [5, 6],
            }
        )
        config = ExternalLabelConfig(
            canonical_path=Path("canonical.parquet"),
            intake_manifest_path=Path("run_manifest.json"),
            output_root=Path("out"),
            tail_shares=(0.20,),
            tau_minutes=(30,),
        )
        with self.assertRaisesRegex(ValueError, "Criterion-only"):
            build_candidate_labels(source, PROFILES["uci_air_quality_360"], config)


if __name__ == "__main__":
    unittest.main()
