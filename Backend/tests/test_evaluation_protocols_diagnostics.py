from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from Backend.Benchmark.evaluation_protocols.diagnostics import (
    annotate_core_fold_status,
    build_v2_coverage_artifacts,
)
from Backend.Benchmark.evaluation_protocols.pipeline.metrics import summarize_protocol_classification


class EvaluationProtocolDiagnosticsTests(unittest.TestCase):
    def test_annotate_core_fold_status_marks_primary_fold_with_unsupported_reporting(self) -> None:
        fold_manifest = pd.DataFrame(
            [
                {
                    "fold_id": "fold_03",
                    "partition": "test",
                    "fold_status": "partial_stress",
                    "primary_benchmark_eligible": True,
                    "status_reason": "temporal_completeness_passed",
                }
            ]
        ).convert_dtypes()
        unsupported_class_audit = pd.DataFrame(
            [
                {
                    "fold_id": "fold_03",
                    "partition": "test",
                    "view_id": "v2_same_y_8h",
                    "unsupported_classes": '["low_relative_moisture_point"]',
                }
            ]
        ).convert_dtypes()

        annotated = annotate_core_fold_status(fold_manifest, unsupported_class_audit)

        self.assertEqual(
            str(annotated.loc[0, "fold_status"]),
            "primary_with_unsupported_class_reporting",
        )
        self.assertEqual(
            str(annotated.loc[0, "status_reason"]),
            "temporal_completeness_passed_with_unsupported_class_reporting",
        )
        self.assertTrue(bool(annotated.loc[0, "unsupported_class_reporting_required"]))

    def test_summarize_protocol_classification_separates_supported_and_fixed_ontology_macro(self) -> None:
        metrics = summarize_protocol_classification(
            np.array([0, 1, 1, 0]),
            np.array([0, 1, 0, 0]),
            ["normal_point", "unknown_environment_point", "low_relative_moisture_point"],
        )

        self.assertAlmostEqual(float(metrics["supported_class_macro_f1"]), 0.7333333333, places=6)
        self.assertAlmostEqual(float(metrics["fixed_ontology_macro_f1"]), 0.4888888888, places=6)
        self.assertEqual(metrics["unsupported_classes"], ["low_relative_moisture_point"])
        self.assertFalse(bool(metrics["ontology_all_classes_supported"]))

    def test_build_v2_coverage_artifacts_highlights_8h_loss_from_insufficient_history(self) -> None:
        base_rows = [
            {
                "record.id": "r1",
                "record.ts_sample": 1778428800,
                "eligible_for_training": True,
                "intrinsic_exclusion_reason": pd.NA,
                "valid_observation_count": 11,
                "actual_window_span_sec": 10800,
                "max_internal_gap_sec": 980,
            },
            {
                "record.id": "r2",
                "record.ts_sample": 1778429700,
                "eligible_for_training": False,
                "intrinsic_exclusion_reason": "insufficient_history",
                "valid_observation_count": 5,
                "actual_window_span_sec": 4200,
                "max_internal_gap_sec": 1200,
            },
        ]
        evidence_3h = pd.DataFrame(base_rows).convert_dtypes()
        evidence_8h = pd.DataFrame(
            base_rows
            + [
                {
                    "record.id": "r3",
                    "record.ts_sample": 1778429800,
                    "eligible_for_training": False,
                    "intrinsic_exclusion_reason": "insufficient_history",
                    "valid_observation_count": 7,
                    "actual_window_span_sec": 5200,
                    "max_internal_gap_sec": 1250,
                }
            ]
        ).convert_dtypes()

        artifacts = build_v2_coverage_artifacts(
            v2_evidence_3h=evidence_3h,
            v2_evidence_8h=evidence_8h,
        )

        self.assertFalse(artifacts.daily.empty)
        self.assertFalse(artifacts.range_summary.empty)
        self.assertIn("V2 Coverage Loss Report", artifacts.markdown_report)


if __name__ == "__main__":
    unittest.main()
