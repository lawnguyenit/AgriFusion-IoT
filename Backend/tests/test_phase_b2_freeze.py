from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

import pandas as pd
import yaml

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.b2 import (
    _validate_anchor_safety,
    _load_selection,
    _validate_distribution_task_specific,
    _validate_window,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.contracts import PhaseB2Config
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract import freeze_phase_b_contract
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.review_template import build_phase_b2_review_template
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.fold_comparison import build_fold_policy_comparison
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.candidate_contracts import (
    DERIVED_CONTRACT_ID,
    CONTINUITY_CONTRACT_ID,
    WINDOW_CONTRACT_ID,
    build_candidate_contract_bundle,
)


class PhaseB2FreezeTests(unittest.TestCase):
    def test_selection_profile_uses_concrete_k6(self) -> None:
        selection = _load_selection(
            Path("Backend/Benchmark/weak_labels/lifecycle/phase_b_contract/config/qk_synchronized_7d.yaml"),
            {},
        )
        self.assertEqual(selection["primary"], {"q": "Q10", "k": 3, "fold_policy_id": "E1_PRIMARY_7D_V1"})
        self.assertIn(
            {"q": "Q10", "k": 6, "fold_policy_id": "E1_PRIMARY_7D_V1"},
            selection["diagnostics"],
        )

    def test_synchronized_five_day_profile_uses_one_fold_policy(self) -> None:
        selection = _load_selection(
            Path("Backend/Benchmark/weak_labels/lifecycle/phase_b_contract/config/qk_synchronized_5d.yaml"),
            {},
        )
        self.assertTrue(all(item["fold_policy_id"] == "E1_DIAGNOSTIC_5D_V1" for item in [selection["primary"], *selection["diagnostics"]]))

    def test_fold_comparison_recommends_seven_day_when_primary_safety_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b1 = root / "b1"
            (b1 / "operationalization").mkdir(parents=True)
            seven_profile = Path("Backend/Benchmark/weak_labels/lifecycle/phase_b_contract/config/qk_synchronized_7d.yaml")
            five_profile = Path("Backend/Benchmark/weak_labels/lifecycle/phase_b_contract/config/qk_synchronized_5d.yaml")
            rows = []
            for profile_path, policy_id, unsafe_primary in ((seven_profile, "E1_PRIMARY_7D_V1", False), (five_profile, "E1_DIAGNOSTIC_5D_V1", True)):
                payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
                for item in [payload["primary"], *payload["diagnostics"]]:
                    rows.append({
                        "q_contract_id": item["q"], "k": item["k"], "fold_policy_id": policy_id,
                        "fold_id": "fold_01", "cross_split_anchor_count": int(unsafe_primary and item is payload["primary"]),
                        "cross_deployment_anchor_count": 0, "purge_applied": True,
                        "dependency_admissible_anchor_count": 10,
                    })
            pd.DataFrame(rows).to_csv(b1 / "operationalization" / "qk_fold_support.csv", index=False)
            pd.DataFrame(columns=["q_contract_id", "k", "fold_policy_id", "task_id"]).to_parquet(
                b1 / "operationalization" / "qk_distribution_audit.parquet", index=False
            )
            report = build_fold_policy_comparison(b1, seven_profile, five_profile, root / "comparison")
            self.assertEqual(report["provisional_recommendation"], "E1_PRIMARY_7D_V1")
            self.assertEqual(report["selection_authority"], "B2_HUMAN_REVIEW")

    def test_anchor_safety_rejects_cross_split_anchor(self) -> None:
        frame = pd.DataFrame(
            [{
                "q_contract_id": "Q10",
                "k": 3,
                "fold_policy_id": "E1_PRIMARY_7D_V1",
                "fold_id": "fold_01",
                "split_role": "validation",
                "unique_anchor_count": 10,
                "dependency_admissible_anchor_count": 9,
                "purge_excluded_count": 1,
                "boundary_excluded_count": 0,
                "cross_split_anchor_count": 1,
                "cross_deployment_anchor_count": 0,
                "purge_applied": True,
            }]
        )
        with self.assertRaises(ValueError):
            _validate_anchor_safety(frame, "Q10", 3)

    def test_anchor_safety_ignores_feature_only_crossing_for_semantic_gate(self) -> None:
        frame = pd.DataFrame([{
            "q_contract_id": "Q10", "k": 3, "fold_policy_id": "E1_PRIMARY_7D_V1",
            "fold_id": "fold_01", "split_role": "validation",
            "unique_anchor_count": 10, "dependency_admissible_anchor_count": 0,
            "semantic_admissible_anchor_count": 10,
            "evaluation_admissible_anchor_count": 0,
            "purge_excluded_count": 0, "boundary_excluded_count": 0,
            "cross_split_anchor_count": 10, "cross_deployment_anchor_count": 0,
            "semantic_cross_split_anchor_count": 0,
            "semantic_cross_deployment_anchor_count": 0,
            "purge_applied": True,
        }])
        _validate_anchor_safety(frame, "Q10", 3)

    def test_anchor_safety_rejects_semantic_crossing_even_if_feature_also_crosses(self) -> None:
        frame = pd.DataFrame([{
            "q_contract_id": "Q10", "k": 3, "fold_policy_id": "E1_PRIMARY_7D_V1",
            "fold_id": "fold_01", "split_role": "validation",
            "unique_anchor_count": 10, "dependency_admissible_anchor_count": 0,
            "semantic_admissible_anchor_count": 9,
            "evaluation_admissible_anchor_count": 0,
            "purge_excluded_count": 0, "boundary_excluded_count": 1,
            "cross_split_anchor_count": 10, "cross_deployment_anchor_count": 1,
            "semantic_cross_split_anchor_count": 1,
            "semantic_cross_deployment_anchor_count": 0,
            "purge_applied": True,
        }])
        with self.assertRaises(ValueError):
            _validate_anchor_safety(frame, "Q10", 3)

    def test_window_contract_is_not_filled_with_defaults(self) -> None:
        with self.assertRaises(ValueError):
            _validate_window({"coverage": {"numerator": "occupied_slots"}})

    def test_task_specific_distribution_does_not_apply_event_gate_to_same_y(self) -> None:
        rows = []
        for task, k, horizon, label, event_count, clusters in (
            ("POINT", pd.NA, "NONE", "LOW", 0, 0),
            ("TEMPORAL", 3, "3H", "TEMPORAL_PERSISTENT_LOW", 2, 2),
            ("SAME_Y", 3, "3H", "ELIGIBLE", 0, 2),
        ):
            for split in ("train", "validation", "test"):
                rows.append({
                    "q_contract_id": "Q10", "k": k, "task_id": task,
                    "horizon_id": horizon, "fold_policy_id": "E1_PRIMARY_7D_V1",
                    "fold_id": "fold_01", "split_role": split,
                    "class_label": label, "class_count": 5,
                    "event_count": event_count, "unique_cluster_count": clusters,
                })
        decision = {
            "point_ontology_policy": {"primary_train_eligible": ["LOW"]},
            "temporal_ontology": {"primary_train_eligible": ["TEMPORAL_PERSISTENT_LOW"]},
            "support_gate": {
                "task_support": {
                    "POINT": {"min_train_class_count": 1, "min_validation_class_count": 1, "min_test_class_count": 1},
                    "TEMPORAL": {"min_train_class_count": 1, "min_validation_class_count": 1, "min_test_class_count": 1, "min_train_event_count": 1, "min_validation_event_count": 1, "min_test_event_count": 1, "min_unique_cluster_count": 1},
                    "SAME_Y": {"min_train_class_count": 1, "min_validation_class_count": 1, "min_test_class_count": 1, "min_unique_cluster_count": 1},
                }
            },
        }
        _validate_distribution_task_specific(
            pd.DataFrame(rows), decision, "Q10", 3, "E1_PRIMARY_7D_V1"
        )

    def test_review_template_is_pending_and_preserves_b1_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            b1 = root / "b1"
            (b1 / "run_metadata").mkdir(parents=True)
            (b1 / "operationalization").mkdir()
            (b1 / "run_metadata" / "run_manifest.json").write_text(
                json.dumps({"decision_pack_hash": "b1-hash"}), encoding="utf-8"
            )
            pd.DataFrame([
                {"q_contract_id": "Q10", "k": 3, "task_id": "TEMPORAL", "horizon_id": "3H", "fold_policy_id": "E1_PRIMARY_7D_V1", "fold_id": "fold_01", "split_role": "train", "class_label": "TEMPORAL_PERSISTENT_LOW", "class_count": 4, "event_count": 2, "unique_cluster_count": 2},
            ]).to_parquet(b1 / "operationalization" / "qk_distribution_audit.parquet", index=False)
            selection = root / "selection.yaml"
            selection.write_text(
                "profile_id: TEST_PROFILE\nprimary:\n  q: Q10\n  k: 3\n  fold_policy_id: E1_PRIMARY_7D_V1\ndiagnostics: []\n",
                encoding="utf-8",
            )
            output = build_phase_b2_review_template(b1, selection, root / "review.yaml")
            payload = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision_status"], "PENDING_REVIEW")
            self.assertEqual(payload["reviewed_decision_pack_hash"], "b1-hash")

    def test_real_candidate_bundle_is_referenceable_not_manual(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            phase_a = root / "phase_a"
            b1 = root / "b1"
            (phase_a / "threshold_diagnostics").mkdir(parents=True)
            (phase_a / "run_metadata").mkdir(parents=True)
            (b1 / "operationalization").mkdir(parents=True)
            thresholds = pd.DataFrame([
                {"threshold_id": "LOW_MOISTURE_Q05_E1_DISCOVERY_CANDIDATE", "threshold_value": 58.65, "threshold_unit": "percent", "code_hash": "x"},
                {"threshold_id": "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE", "threshold_value": 59.96, "threshold_unit": "percent", "code_hash": "x"},
                {"threshold_id": "LOW_MOISTURE_Q15_E1_DISCOVERY_CANDIDATE", "threshold_value": 61.127, "threshold_unit": "percent", "code_hash": "x"},
                {"threshold_id": "LOW_MOISTURE_Q20_E1_DISCOVERY_CANDIDATE", "threshold_value": 62.03, "threshold_unit": "percent", "code_hash": "x"},
                {"threshold_id": "THERMAL_VPD_FIXED_2_5_REFERENCE", "threshold_value": 2.5, "threshold_unit": "kPa", "code_hash": "x"},
                {"threshold_id": "MOISTURE_RISE_FIXED_5PP_REFERENCE", "threshold_value": 5.0, "threshold_unit": "percentage_points", "code_hash": "x"},
                {"threshold_id": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE", "threshold_value": 6.0, "threshold_unit": "canonical_ec_unit", "code_hash": "x"},
            ])
            thresholds.to_csv(phase_a / "threshold_diagnostics" / "threshold_registry.csv", index=False)
            (phase_a / "run_metadata" / "run_manifest.json").write_text(
                json.dumps({"run_id": "phase-a", "strict_policy": {"policy_id": "STRICT_15M_PM2_V1", "min_gap_minutes": 13, "max_gap_minutes": 17}, "window_horizons_hours": [3, 8]}),
                encoding="utf-8",
            )
            pd.DataFrame([
                {"q_contract_id": "Q10", "fold_policy_id": "E1_PRIMARY_7D_V1", "task_id": "POINT", "class_label": "LOW", "class_count": 25, "event_count": 0, "unique_cluster_count": 0},
            ]).to_parquet(b1 / "operationalization" / "qk_distribution_audit.parquet", index=False)
            bundle = build_candidate_contract_bundle(phase_a, b1, b1 / "contracts" / "candidates")
            self.assertEqual(bundle["derived_evidence_contract_id"], DERIVED_CONTRACT_ID)
            self.assertEqual(bundle["continuity_contract_id"], CONTINUITY_CONTRACT_ID)
            self.assertEqual(bundle["window_contract_id"], WINDOW_CONTRACT_ID)
            self.assertTrue((b1 / "contracts" / "candidates" / "derived_evidence_contract_registry.csv").exists())

    def test_missing_review_inputs_block_without_final_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "out"
            result = freeze_phase_b_contract(
                PhaseB2Config(
                    phase_a_run_dir=root / "phase_a",
                    phase_b1_decision_pack_dir=root / "b1",
                    protocol_registry_run_dir=root / "registry",
                    review_decision_path=root / "review.yaml",
                    anchor_safety_audit_path=root / "anchor.parquet",
                    distribution_audit_path=root / "distribution.parquet",
                    derived_evidence_contract_path=root / "derived.csv",
                    continuity_contract_path=root / "continuity.yaml",
                    window_contract_path=root / "window.yaml",
                    expected_difference_contract_path=root / "expected.csv",
                    canonical_history_path=root / "canonical.csv",
                    output_root=output,
                    selection_config_path=root / "selection.yaml",
                )
            )
            self.assertEqual(result.status, "CONTRACT_FREEZE_BLOCKED")
            self.assertIsNone(result.output_dir)
            self.assertFalse(any(path.name.startswith("semantic_contract_") for path in output.iterdir() if path.is_dir() and path.name != ".staging"))


if __name__ == "__main__":
    unittest.main()
