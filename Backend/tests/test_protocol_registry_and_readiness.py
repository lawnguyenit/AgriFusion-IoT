from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from Backend.Benchmark.protocol_registry import (
    ProtocolRegistry,
    authorize_arm_operation,
    authorize_operation,
    build_protocol_registry,
    load_protocol_registry,
)
from Backend.Benchmark.evaluation_protocols.contracts import EvaluationProtocolConfig
from Backend.Benchmark.evaluation_protocols.pipeline.build import (
    _validate_protocol_registry_authority,
)
from Backend.Benchmark.validity_lifecycle.contracts import ValidityLifecycleConfig
from Backend.Benchmark.validity_lifecycle.pipeline.build import (
    _validate_protocol_registry_link,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness import PhaseAReadinessConfig, build_phase_a_readiness
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.canonical import _logical_measurement_fingerprints
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.continuity import build_causal_dependency_audit
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.evidence import (
    build_candidate_evidence,
    build_rule_applicability,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_CONFIG = REPO_ROOT / "Backend" / "Benchmark" / "protocol_registry" / "config" / "protocol_v1.yaml"
LAYER1_MANIFEST = REPO_ROOT / "Backend" / "Output_data" / "Layer1" / "manifest.json"
CANONICAL_HISTORY = REPO_ROOT / "Backend" / "Output_data" / "Layer1" / "canonical" / "telemetry_history.csv"


class ProtocolRegistryTests(unittest.TestCase):
    def test_registry_separates_authorities_and_locks_fold_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = build_protocol_registry(
                PROTOCOL_CONFIG,
                LAYER1_MANIFEST,
                output_root=Path(temp_dir),
            )
            registry = load_protocol_registry(run_dir)
            self.assertNotIn("fit_allowed", registry.environment_manifest.columns)
            self.assertEqual(
                dict(
                    zip(
                        registry.fold_policy_registry["fold_policy_id"],
                        registry.fold_policy_registry["fold_policy_role"],
                    )
                ),
                {
                    "E1_PRIMARY_7D_V1": "PRIMARY",
                    "E1_DIAGNOSTIC_5D_V1": "DIAGNOSTIC",
                },
            )
            complete = registry.e1_fold_registry.loc[
                registry.e1_fold_registry["evaluation_usable"].fillna(False).astype(bool)
            ]
            complete_counts = complete.groupby("fold_policy_id").size().to_dict()
            self.assertEqual(int(complete_counts["E1_PRIMARY_7D_V1"]), 1)
            self.assertEqual(int(complete_counts["E1_DIAGNOSTIC_5D_V1"]), 3)
            self.assertFalse(
                authorize_operation(registry, "PHASE_A_AUDIT", "E2", "inspect_sensitive").allowed
            )
            self.assertTrue(
                authorize_operation(registry, "PHASE_A_AUDIT", "E2", "inspect_structural").allowed
            )
            self.assertFalse(
                authorize_operation(
                    registry,
                    "RQ2B_E3_REEVALUATION_BATCH",
                    "E3_TARGET_PREEXPOSED",
                    "fit",
                ).allowed
            )
            self.assertFalse(
                authorize_arm_operation(
                    registry,
                    "RQ2A_E2_RELEASE",
                    "E2",
                    "E1_ONLY_FROZEN",
                    "model_refit",
                ).allowed
            )
            self.assertTrue(
                authorize_arm_operation(
                    registry,
                    "RQ2A_E2_RELEASE",
                    "E2",
                    "E1_PLUS_E2_SOURCE_EXPANSION",
                    "preprocessing_refit",
                ).allowed
            )
            self.assertFalse(
                authorize_arm_operation(
                    registry,
                    "RQ2A_E2_RELEASE",
                    "E2",
                    "E1_PLUS_E2_SOURCE_EXPANSION",
                    "hyperparameter_refit",
                ).allowed
            )
            self.assertTrue(
                authorize_operation(
                    registry,
                    "RQ2B_E3_REEVALUATION_BATCH",
                    "E3_TARGET_PREEXPOSED",
                    "evaluate",
                ).allowed
            )

    def test_registry_rejects_overlapping_environment_intervals(self) -> None:
        payload = yaml.safe_load(PROTOCOL_CONFIG.read_text(encoding="utf-8"))
        payload["environments"][1]["start_time"] = "2026-05-08T00:00:00+07:00"
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_config = Path(temp_dir) / "invalid.yaml"
            invalid_config.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overlap"):
                build_protocol_registry(
                    invalid_config,
                    LAYER1_MANIFEST,
                    output_root=Path(temp_dir) / "artifacts",
                )

    def test_phase_a_registry_blocks_downstream_governed_runners(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = build_protocol_registry(
                PROTOCOL_CONFIG,
                LAYER1_MANIFEST,
                output_root=Path(temp_dir),
            )
            registry = load_protocol_registry(run_dir)
            evaluation_config = EvaluationProtocolConfig(
                protocol_registry_run_dir=run_dir,
                protocol_stage_id="RQ2B_E3_REEVALUATION_BATCH",
                canonical_history_path=CANONICAL_HISTORY,
                feature_catalog_path=REPO_ROOT
                / "Backend"
                / "Output_data"
                / "Layer1"
                / "canonical"
                / "feature_catalog.csv",
                manifest_path=LAYER1_MANIFEST,
                segment_manifest_path=None,
                dataset_views_run_dir=Path(temp_dir) / "views",
                native_label_release_dir=Path(temp_dir) / "labels",
                output_root=Path(temp_dir) / "evaluation",
            )
            with self.assertRaisesRegex(PermissionError, "Phase A audit-only"):
                _validate_protocol_registry_authority(evaluation_config, registry)
            lifecycle_config = ValidityLifecycleConfig(
                evaluation_protocol_run_dir=Path(temp_dir) / "evaluation",
                output_root=Path(temp_dir) / "validity",
                environment_specs=(),
                protocol_registry_run_dir=run_dir,
            )
            with self.assertRaisesRegex(PermissionError, "Phase A audit-only"):
                _validate_protocol_registry_link(lifecycle_config, registry)

    def test_logical_fingerprint_ignores_source_path(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "record.node_id": "Node1",
                    "record.ts_sample": 1,
                    "record.source_path": "copy/a",
                    "sht.temp_c": 25,
                    "npk.soil_moisture_pct": 60,
                },
                {
                    "record.node_id": "Node1",
                    "record.ts_sample": 1,
                    "record.source_path": "copy/b",
                    "sht.temp_c": 25,
                    "npk.soil_moisture_pct": 60,
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "canonical.csv"
            frame.to_csv(path, index=False)
            fingerprints = _logical_measurement_fingerprints(path)
        self.assertEqual(fingerprints[0], fingerprints[1])


class PhaseAReadinessTests(unittest.TestCase):
    def test_field_validity_keeps_moisture_evaluable_when_aggregate_npk_is_invalid(self) -> None:
        frame = pd.DataFrame(
            {
                "sample_time": pd.to_datetime(["2026-04-01T00:00:00+07:00"]),
                "record.segment_id": ["segment-1"],
                "sht.packet_present": [False],
                "npk.packet_present": [True],
                "sht.valid": [False],
                "npk.valid": [False],  # pH is invalid, but the overlay fields are usable.
                "npk.soil_moisture_pct": [100.0],
                "npk.soil_moisture_valid": [True],
                "npk.ec": [220.0],
                "npk.ec_valid": [True],
                "sht.temp_c": [pd.NA],
                "sht.humidity_pct": [pd.NA],
                "strictly_consecutive_from_previous": [False],
                "moisture_delta_strict": [pd.NA],
                "ec_delta_abs_strict": [pd.NA],
            }
        )
        result = build_rule_applicability(frame)
        self.assertTrue(bool(result.loc[0, "soil_moisture_evaluable"]))
        self.assertTrue(bool(result.loc[0, "low_rule_applicability"]))
        self.assertFalse(bool(result.loc[0, "vpd_evaluable"]))

    def test_candidate_ontology_does_not_promote_missing_context_to_reference(self) -> None:
        frame = pd.DataFrame(
            [
                _candidate_row(moisture=50, low_applicable=True, context_applicable=False),
                _candidate_row(moisture=70, low_applicable=True, context_applicable=False),
                _candidate_row(moisture=70, low_applicable=True, context_applicable=True),
                _candidate_row(
                    moisture=70,
                    low_applicable=True,
                    context_applicable=True,
                    derived_vpd_kpa=3.0,
                ),
            ]
        ).convert_dtypes()
        result = build_candidate_evidence(frame, low_q10=60.0, ec_q95=6.0)
        self.assertEqual(
            result["candidate_resolution"].astype(str).tolist(),
            ["LOW", "UNRESOLVED", "REFERENCE", "UNRESOLVED"],
        )

    def test_full_observed_run_crossing_does_not_control_anchor_eligibility(self) -> None:
        times = pd.to_datetime(
            [
                "2026-04-01T00:30:00+07:00",
                "2026-04-01T00:45:00+07:00",
                "2026-04-01T01:00:00+07:00",
                "2026-04-01T01:15:00+07:00",
            ]
        )
        evidence = pd.DataFrame(
            {
                "record.id": ["r1", "r2", "r3", "r4"],
                "sample_time": times,
                "strict_continuity_id": ["strict1"] * 4,
                "deployment_segment_id": ["deployment1"] * 4,
                "observed_low_run_id": ["run1"] * 4,
            }
        ).convert_dtypes()
        registry = _minimal_registry(
            pd.DataFrame(
                [
                    {
                        "fold_policy_id": "TEST_FOLD",
                        "fold_policy_role": "PRIMARY",
                        "fold_id": "fold_01",
                        "train_start": "2026-04-01T00:00:00+07:00",
                        "train_end": "2026-04-01T01:00:00+07:00",
                        "validation_start": "2026-04-01T01:00:00+07:00",
                        "validation_end": "2026-04-01T02:00:00+07:00",
                        "test_start": "2026-04-01T02:00:00+07:00",
                        "test_end": "2026-04-01T03:00:00+07:00",
                        "evaluation_usable": True,
                    }
                ]
            ).convert_dtypes()
        )
        audit = build_causal_dependency_audit(
            evidence,
            registry,
            window_horizons_hours=(0,),
            persistence_candidates=(2,),
        )
        anchor = audit.loc[audit["record_id"].astype("string") == "r2"].iloc[0]
        self.assertTrue(bool(anchor["observed_run_crosses_split"]))
        self.assertTrue(bool(anchor["evaluation_dependency_eligible"]))
        self.assertFalse(bool(anchor["observed_run_crossing_used_for_eligibility"]))

    def test_real_snapshot_phase_a_passes_without_legacy_baseline(self) -> None:
        required = [
            CANONICAL_HISTORY,
            LAYER1_MANIFEST,
        ]
        if not all(path.exists() for path in required):
            self.skipTest("Layer1 snapshot required by the Phase A integration test is unavailable.")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry_dir = build_protocol_registry(
                PROTOCOL_CONFIG,
                LAYER1_MANIFEST,
                output_root=root / "registry",
            )
            result = build_phase_a_readiness(
                PhaseAReadinessConfig(
                    protocol_registry_run_dir=registry_dir,
                    canonical_history_path=CANONICAL_HISTORY,
                    canonical_manifest_path=LAYER1_MANIFEST,
                    output_root=root / "readiness",
                )
            )
            self.assertEqual(result.overall_status, "PASS")
            threshold_registry = pd.read_csv(
                result.output_dir / "threshold_diagnostics" / "threshold_registry.csv"
            )
            candidate = threshold_registry.loc[
                threshold_registry["threshold_id"]
                == "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE"
            ].iloc[0]
            self.assertEqual(int(candidate["fit_record_count"]), 1850)
            self.assertAlmostEqual(float(candidate["threshold_value"]), 59.96, places=6)
            hash_audit = pd.read_csv(
                result.output_dir / "legacy_compatibility" / "baseline_hash_audit.csv"
            )
            self.assertTrue(hash_audit["status"].eq("NOT_AVAILABLE").all())
            membership = pd.read_csv(
                result.output_dir
                / "canonical_integrity"
                / "environment_membership_audit.csv"
            )
            sealed = membership.loc[
                membership["environment_id"].isin(["E2", "E3_TARGET_PREEXPOSED"])
            ]
            self.assertTrue(sealed["visibility_status"].eq("STRUCTURAL_ONLY").all())
            self.assertFalse(sealed["sensitive_artifacts_materialized"].astype(bool).any())

    def test_static_dependency_direction(self) -> None:
        registry_source = (
            REPO_ROOT / "Backend" / "Benchmark" / "protocol_registry" / "registry.py"
        ).read_text(encoding="utf-8")
        readiness_source = (
            REPO_ROOT
            / "Backend"
            / "Benchmark"
            / "weak_labels"
            / "lifecycle"
            / "phase_a_readiness"
            / "pipeline.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "Backend.Benchmark.weak_labels",
            "Backend.Benchmark.evaluation_protocols",
            "Backend.Benchmark.dataset_views",
            "Backend.Benchmark.model_suite",
        ):
            self.assertNotIn(forbidden, registry_source)
        self.assertNotIn("weak_labels.point", readiness_source)
        self.assertNotIn("weak_labels.v2", readiness_source)
        self.assertNotIn("build_point_label_artifacts", readiness_source)


def _candidate_row(
    *,
    moisture: float,
    low_applicable: bool,
    context_applicable: bool,
    derived_vpd_kpa: float = 1.0,
) -> dict[str, object]:
    return {
        "npk.soil_moisture_pct": moisture,
        "derived_vpd_kpa": derived_vpd_kpa,
        "moisture_delta_strict": 0.0,
        "ec_delta_abs_strict": 0.0,
        "low_rule_applicability": low_applicable,
        "thermal_rule_applicability": context_applicable,
        "rise_rule_applicability": context_applicable,
        "ec_shift_rule_applicability": context_applicable,
        "low_target_eligibility": low_applicable,
        "full_point_ontology_eligibility": low_applicable and context_applicable,
    }


def _minimal_registry(folds: pd.DataFrame) -> ProtocolRegistry:
    empty = pd.DataFrame()
    return ProtocolRegistry(
        run_dir=Path("."),
        environment_manifest=empty,
        visibility_policy_registry=empty,
        experiment_arm_manifest=empty,
        fold_policy_registry=empty,
        e1_fold_registry=folds,
        threshold_fit_cohort_manifest=empty,
        future_target_policy=empty,
        stage_registry=empty,
        run_manifest={},
    )


if __name__ == "__main__":
    unittest.main()
