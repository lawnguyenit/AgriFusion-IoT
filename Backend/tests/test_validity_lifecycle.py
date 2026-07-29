from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.validity_lifecycle.audits.comparisons import build_comparison_hash_audit
from Backend.Benchmark.validity_lifecycle.audits.dependencies import classify_dependency_relationship
from Backend.Benchmark.validity_lifecycle.audits.eligibility import build_environment_eligibility_matrix
from Backend.Benchmark.validity_lifecycle.audits.support import classify_support_status
from Backend.Benchmark.validity_lifecycle.contracts import EnvironmentSpec, ValidityLifecycleConfig
from Backend.Benchmark.validity_lifecycle.defaults import PRIMARY_VIEW_IDS, default_environment_specs, primary_claims_payload
from Backend.Benchmark.validity_lifecycle.registry import assign_environment_id
from Backend.Benchmark.validity_lifecycle.reporting import build_validation_payload, render_validity_lifecycle_report


class ValidityLifecycleTests(unittest.TestCase):
    def test_assign_environment_id_uses_boundary_contract(self) -> None:
        specs = default_environment_specs()
        before_boundary = pd.Timestamp("2026-05-08T23:59:59", tz="Asia/Ho_Chi_Minh")
        after_boundary = pd.Timestamp("2026-05-09T00:00:00", tz="Asia/Ho_Chi_Minh")
        self.assertEqual(assign_environment_id(before_boundary, specs).environment_id, "E1")
        self.assertEqual(assign_environment_id(after_boundary, specs).environment_id, "E2")

    def test_classify_support_status(self) -> None:
        self.assertEqual(
            classify_support_status(
                total_rows=20,
                class_rows=10,
                day_count=3,
                segment_count=1,
                min_samples=5,
                min_days=2,
                min_segments=1,
            ),
            "FULL",
        )
        self.assertEqual(
            classify_support_status(
                total_rows=20,
                class_rows=0,
                day_count=0,
                segment_count=0,
                min_samples=5,
                min_days=2,
                min_segments=1,
            ),
            "ABSENT",
        )
        self.assertEqual(
            classify_support_status(
                total_rows=0,
                class_rows=0,
                day_count=0,
                segment_count=0,
                min_samples=5,
                min_days=2,
                min_segments=1,
            ),
            "NOT_ESTIMABLE",
        )

    def test_environment_eligibility_matrix_counts_loss_reasons(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "environment_id": "E1",
                    "environment_stage_name": "Discovery",
                    "view_id": "v2_same_y_mini_3h",
                    "target_label": "NRM",
                    "view_eligible": True,
                    "view_exclusion_reason": pd.NA,
                    "view_label_status": "LABELED",
                    "technical_valid": True,
                    "missing_slot_count": 0,
                    "buffered": False,
                    "replayed": False,
                },
                {
                    "environment_id": "E1",
                    "environment_stage_name": "Discovery",
                    "view_id": "v2_same_y_mini_3h",
                    "target_label": "NRM",
                    "view_eligible": False,
                    "view_exclusion_reason": "insufficient_history",
                    "view_label_status": "EXCLUDED_WINDOW_INELIGIBLE",
                    "technical_valid": True,
                    "missing_slot_count": 2,
                    "buffered": False,
                    "replayed": False,
                },
            ]
        ).convert_dtypes()
        result = build_environment_eligibility_matrix(frame)
        self.assertEqual(int(result.loc[0, "base_row_count"]), 2)
        self.assertEqual(int(result.loc[0, "eligible_row_count"]), 1)
        self.assertEqual(int(result.loc[0, "insufficient_history_excluded_count"]), 1)

    def test_comparison_hash_audit_fails_on_mismatch(self) -> None:
        comparison_df = pd.DataFrame(
            [
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "matched_cohort_id": "cohort",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "comparison_side": "left",
                    "sample_id": "s1",
                    "record_set_hash": "abc",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "matched_cohort_id": "cohort",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "comparison_side": "right",
                    "sample_id": "s2",
                    "record_set_hash": "xyz",
                },
            ]
        ).convert_dtypes()
        observation_registry = pd.DataFrame(
            [
                {"sample_id": "s1", "point_target": "NRM", "timestamp": 1},
                {"sample_id": "s2", "point_target": "LRM", "timestamp": 2},
            ]
        ).convert_dtypes()
        result = build_comparison_hash_audit(comparison_df, observation_registry)
        self.assertEqual(str(result.loc[0, "status"]), "FAIL")

    def test_classify_dependency_relationship(self) -> None:
        self.assertEqual(
            classify_dependency_relationship(
                row_count=10,
                unique_ec_count=10,
                conflicting_mapping_count=0,
                pearson_r=1.0,
                spearman_r=1.0,
                r2_linear=1.0,
                max_abs_residual=0.0,
                median_abs_residual=0.0,
            ),
            "DETERMINISTIC_EC_DERIVED_PROXY",
        )
        self.assertEqual(
            classify_dependency_relationship(
                row_count=10,
                unique_ec_count=10,
                conflicting_mapping_count=3,
                pearson_r=0.5,
                spearman_r=0.4,
                r2_linear=0.2,
                max_abs_residual=50.0,
                median_abs_residual=10.0,
            ),
            "INCONCLUSIVE",
        )

    def test_report_rendering_includes_mermaid_and_stage_answers(self) -> None:
        config = ValidityLifecycleConfig(
            evaluation_protocol_run_dir=Path("D:/fake"),
            output_root=Path("D:/fake-out"),
            environment_specs=default_environment_specs(),
        )
        support_df = pd.DataFrame(
            [{"environment_id": "E1", "view_id": "v0_point", "support_status": "FULL"}]
        ).convert_dtypes()
        eligibility_df = pd.DataFrame(
            [{"environment_id": "E1", "view_id": "v0_point", "base_row_count": 1, "eligible_row_count": 1, "eligible_rate": 1.0}]
        ).convert_dtypes()
        comparison_df = pd.DataFrame([{"status": "PASS"}]).convert_dtypes()
        ec_df = pd.DataFrame([{"environment_id": "ALL", "nutrient_column": "npk.n_proxy", "relationship_class": "DETERMINISTIC_EC_DERIVED_PROXY"}]).convert_dtypes()
        ph_df = pd.DataFrame([{"environment_id": "ALL", "stability_class": "STABLE_RANGE"}]).convert_dtypes()
        payload = build_validation_payload(
            config=config,
            support_df=support_df,
            eligibility_df=eligibility_df,
            comparison_hash_df=comparison_df,
            ec_dependency_df=ec_df,
            ph_stability_df=ph_df,
        )
        markdown = render_validity_lifecycle_report(
            validation_payload=payload,
            config=config,
            support_df=support_df,
            eligibility_df=eligibility_df,
            comparison_hash_df=comparison_df,
            ec_dependency_df=ec_df,
            ph_stability_df=ph_df,
        )
        self.assertIn("```mermaid", markdown)
        self.assertIn("Stage Answers", markdown)
        self.assertIn("Discovery", markdown)

    def test_primary_lifecycle_scope_aligns_to_current_3h_public_views(self) -> None:
        payload = primary_claims_payload()

        self.assertEqual(
            PRIMARY_VIEW_IDS,
            ("v0_point", "v1_point", "v2_same_y_mini_3h", "v2_same_y_full_3h"),
        )
        self.assertEqual(
            payload["comparisons"],
            ["v0_vs_v2_mini_3h", "v1_vs_v2_full_3h"],
        )


if __name__ == "__main__":
    unittest.main()
