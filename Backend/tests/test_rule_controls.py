from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.model_suite.validation import run_rule_controls


class RuleControlTests(unittest.TestCase):
    def _build_release(self, root: Path, *, mutated: bool = False) -> Path:
        (root / "tasks" / "point").mkdir(parents=True)
        (root / "audit").mkdir(parents=True)
        rows = []
        states = {
            "s1": {
                "LOW_RELATIVE_MOISTURE": "POSITIVE",
                "THERMAL_CONTEXT": "NEGATIVE",
                "MOISTURE_RISE": "NEGATIVE",
                "EC_SHIFT": "NEGATIVE",
            },
            "s2": {
                "LOW_RELATIVE_MOISTURE": "NEGATIVE",
                "THERMAL_CONTEXT": "NEGATIVE",
                "MOISTURE_RISE": "NEGATIVE",
                "EC_SHIFT": "NEGATIVE",
            },
        }
        for sample_id, sample_states in states.items():
            for rule_id, evidence_state in sample_states.items():
                rows.append(
                    {
                        "sample_id": sample_id,
                        "task_id": "POINT",
                        "rule_id": rule_id,
                        "evidence_state": evidence_state,
                    }
                )
        pd.DataFrame(rows).to_parquet(root / "audit" / "rule_firings.parquet", index=False)
        labels = ["low_relative_moisture_point", "reference_context_point"]
        if mutated:
            labels[0] = "reference_context_point"
        label_frame = pd.DataFrame(
            {
                "sample_id": ["s1", "s2"],
                "label_name": labels,
                "label_status": ["LABELED", "LABELED"],
            }
        )
        pd.DataFrame(
            {
                "sample_id": ["s1", "s2"],
                "task_id": ["POINT", "POINT"],
                "label": ["low_relative_moisture_point", "reference_context_point"],
            }
        ).to_parquet(root / "audit" / "assignments.parquet", index=False)
        pd.DataFrame(
            {
                "sample_id": ["s1", "s2"],
                "task_id": ["POINT", "POINT"],
                "resolved_label": ["low_relative_moisture_point", "reference_context_point"],
            }
        ).to_parquet(root / "audit" / "resolutions.parquet", index=False)
        path = root / "tasks" / "point" / "assignments.parquet"
        label_frame.to_parquet(path, index=False)
        return path

    def test_independent_controls_pass_when_artifacts_agree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._build_release(Path(temp_dir))
            rows = pd.read_parquet(path)
            summary = run_rule_controls(
                evaluation_partitions=("test",),
                partitions={"test": rows},
                label_artifact_path=path,
                output_dir=Path(temp_dir) / "output",
            )
            self.assertEqual(summary["positive_control_status"], "PASS")
            self.assertEqual(summary["independent_oracle_agreement_rate"], 1.0)
            self.assertEqual(summary["artifact_assignment_agreement_rate"], 1.0)
            self.assertEqual(summary["artifact_resolution_agreement_rate"], 1.0)

    def test_independent_oracle_rejects_mutated_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._build_release(Path(temp_dir), mutated=True)
            rows = pd.read_parquet(path)
            with self.assertRaisesRegex(ValueError, "positive control disagreement"):
                run_rule_controls(
                    evaluation_partitions=("test",),
                    partitions={"test": rows},
                    label_artifact_path=path,
                    output_dir=Path(temp_dir) / "output",
                )

    def test_temporal_independent_control_applies_k_to_point_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_dir = root / "tasks" / "temporal" / "horizon_3h"
            audit_dir = root / "audit"
            task_dir.mkdir(parents=True)
            audit_dir.mkdir(parents=True)
            samples = ["s1", "s2", "s3", "s4"]
            point_states = {
                "s1": "POSITIVE",
                "s2": "POSITIVE",
                "s3": "POSITIVE",
                "s4": "NEGATIVE",
            }
            firing_rows = []
            for sample_id, low_state in point_states.items():
                for rule_id, evidence_state in {
                    "LOW_RELATIVE_MOISTURE": low_state,
                    "THERMAL_CONTEXT": "NEGATIVE",
                    "MOISTURE_RISE": "NEGATIVE",
                    "EC_SHIFT": "NEGATIVE",
                }.items():
                    firing_rows.append(
                        {
                            "sample_id": sample_id,
                            "task_id": "POINT",
                            "rule_id": rule_id,
                            "evidence_state": evidence_state,
                        }
                    )
            pd.DataFrame(firing_rows).to_parquet(audit_dir / "rule_firings.parquet", index=False)
            continuity_rows = []
            for index, sample_id in enumerate(samples):
                continuity_rows.append(
                    {
                        "record.id": sample_id,
                        "deployment_segment_id": "seg1",
                        "sample_time_utc": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=16 * index),
                        "strictly_consecutive_from_previous": index > 0,
                    }
                )
            pd.DataFrame(continuity_rows).to_parquet(audit_dir / "continuity_registry.parquet", index=False)
            labels = [
                "unresolved_environmental_evidence_at_anchor",
                "unresolved_environmental_evidence_at_anchor",
                "persistent_low_relative_moisture_at_anchor",
                "reference_context_at_anchor",
            ]
            label_frame = pd.DataFrame(
                {
                    "sample_id": samples,
                    "task_id": ["temporal"] * 4,
                    "horizon_id": ["3h"] * 4,
                    "label_name": labels,
                    "label_status": ["LABELED"] * 4,
                }
            )
            label_frame.to_parquet(task_dir / "assignments.parquet", index=False)
            pd.DataFrame(
                {
                    "sample_id": samples,
                    "representation_history_status": ["ELIGIBLE"] * 4,
                }
            ).to_parquet(task_dir / "evidence.parquet", index=False)
            pd.DataFrame(
                {
                    "sample_id": samples,
                    "task_id": ["TEMPORAL_ANCHOR"] * 4,
                    "horizon_id": ["3h"] * 4,
                    "label": labels,
                }
            ).to_parquet(audit_dir / "assignments.parquet", index=False)
            pd.DataFrame(
                {
                    "sample_id": samples,
                    "task_id": ["TEMPORAL_ANCHOR"] * 4,
                    "horizon_id": ["3h"] * 4,
                    "resolved_label": labels,
                    "required_k": [3] * 4,
                }
            ).to_parquet(audit_dir / "resolutions.parquet", index=False)

            summary = run_rule_controls(
                evaluation_partitions=("test",),
                partitions={"test": label_frame},
                label_artifact_path=task_dir / "assignments.parquet",
                output_dir=root / "output",
            )
            self.assertEqual(summary["positive_control_status"], "PASS")
            self.assertEqual(summary["independent_oracle_agreement_rate"], 1.0)
            self.assertEqual(summary["artifact_assignment_agreement_rate"], 1.0)
            self.assertEqual(summary["artifact_resolution_agreement_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
