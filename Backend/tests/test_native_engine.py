from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import (
    NativeContract,
    NativeContractError,
    deterministic_id,
)
from Backend.Benchmark.weak_labels.compatibility.differential.audit import build_shadow_differential_audit
from Backend.Benchmark.weak_labels.semantic.continuity.primitives import build_continuity_primitives
from Backend.Benchmark.weak_labels.semantic.derived_evidence.transforms import build_derived_evidence
from Backend.Benchmark.weak_labels.provenance.materialize import materialize_from_assignments
from Backend.Benchmark.weak_labels.provenance.release import (
    build_label_release_manifest,
    materialize_label_release_frame,
)
from Backend.Benchmark.evaluation_protocols.pipeline.consumption import load_native_label_sources
from Backend.Benchmark.weak_labels.semantic.point.resolver import resolve_point_assignments
from Backend.Benchmark.weak_labels.semantic.same_y.projection import build_same_y_transfer_projection


class NativeEngineTests(unittest.TestCase):
    def test_deterministic_ids_are_namespaced_and_collision_safe(self) -> None:
        base = {
            "schema_version": "v1",
            "semantic_contract_hash": "contract",
            "operationalization_id": "PRIMARY",
            "task_id": "POINT",
            "horizon_id": "NONE",
            "sample_id": "r1",
        }
        firing_a = deterministic_id({**base, "object_type": "RULE_FIRING", "rule_id": "LOW"})
        firing_b = deterministic_id({**base, "object_type": "RULE_FIRING", "rule_id": "EC"})
        resolution = deterministic_id({**base, "object_type": "RESOLUTION", "compatibility_row_id": "r"})
        assignment = deterministic_id({**base, "object_type": "ASSIGNMENT", "resolution_instance_id": resolution, "assignment_mode": "RULE_EVALUATION"})
        self.assertEqual(len({firing_a, firing_b, resolution, assignment}), 4)

    def test_contract_loader_fails_closed_without_derived_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "run_metadata").mkdir()
            (root / "run_metadata" / "run_manifest.json").write_text(
                '{"semantic_contract_frozen": true, "native_engine_implemented": false, "downstream_runners_unlocked": false, "semantic_contract_id": "id", "semantic_contract_hash": "hash"}',
                encoding="utf-8",
            )
            with self.assertRaises(NativeContractError):
                NativeContract.load(root)

    def test_point_resolution_separates_context_incomplete_from_observed_positive(self) -> None:
        contract = _contract_for_tests()
        frame = pd.DataFrame(
            {
                "record.id": ["low", "unresolved", "incomplete", "reference"],
                "time_integrity_ok": [True, True, True, True],
                "environment_id": ["E1"] * 4,
            }
        )
        states = pd.DataFrame(
            {
                "sample_id": ["low", "unresolved", "incomplete", "reference"],
                "low_state": ["POSITIVE", "NEGATIVE", "NEGATIVE", "NEGATIVE"],
                "thermal_state": ["NEGATIVE", "POSITIVE", "NOT_EVALUABLE", "NEGATIVE"],
                "rise_state": ["NOT_EVALUABLE", "NEGATIVE", "NEGATIVE", "NEGATIVE"],
                "ec_state": ["NOT_EVALUABLE", "NEGATIVE", "NEGATIVE", "NEGATIVE"],
            }
        )
        firings = _firings(states)
        resolutions, assignments = resolve_point_assignments(frame, states, firings, contract, _operationalization())
        labels = dict(zip(assignments["sample_id"], assignments["label"], strict=True))
        codes = dict(zip(resolutions["sample_id"], resolutions["resolution_code"], strict=True))
        self.assertEqual(labels["low"], "low_relative_moisture_point")
        self.assertEqual(codes["unresolved"], "POINT_UNRESOLVED_AUXILIARY_POSITIVE")
        self.assertEqual(codes["incomplete"], "POINT_CONTEXT_INCOMPLETE")
        self.assertEqual(labels["reference"], "reference_context_point")

    def test_same_y_preserves_source_label_and_only_projects_history_status(self) -> None:
        contract = _contract_for_tests()
        point = pd.DataFrame(
            {
                "assignment_id": ["a1"],
                "sample_id": ["r1"],
                "label": ["low_relative_moisture_point"],
                "train_inclusion_status": ["INCLUDED"],
            }
        )
        window = pd.DataFrame({"sample_id": ["r1"], "representation_history_status": ["INELIGIBLE"]})
        output = build_same_y_transfer_projection(point, window, contract, _operationalization(), "3h")
        self.assertEqual(output.iloc[0]["source_label"], output.iloc[0]["transferred_label"])
        self.assertEqual(output.iloc[0]["intrinsic_transfer_status"], "EXCLUDED_FROM_COHORT")

    def test_differential_requires_precommitted_predicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "expected.csv"
            pd.DataFrame(
                [
                    {
                        "difference_type": "CONTEXT_INCOMPLETE_SPLIT",
                        "priority": 1,
                        "required_old_state": "reference_context_point",
                        "required_new_state": "point_context_incomplete",
                        "required_evidence_condition": "auxiliary_missing",
                        "authority_decision_id": "DEC-1",
                    }
                ]
            ).to_csv(expected, index=False)
            native = pd.DataFrame({"sample_id": ["r1"], "task_id": ["POINT"], "horizon_id": ["NONE"], "label": ["point_context_incomplete"]})
            legacy = pd.DataFrame({"sample_id": ["r1"], "task_id": ["POINT"], "horizon_id": ["NONE"], "label": ["reference_context_point"]})
            result = build_shadow_differential_audit(
                native_assignments=native,
                legacy_assignments=legacy,
                expected_difference_contract_path=expected,
                output_dir=root / "audit",
            )
            self.assertEqual(result.status, "PASS")

    def test_materialization_requires_assignment_resolution_lineage(self) -> None:
        assignments = pd.DataFrame(
            [{"assignment_id": "a", "sample_id": "r", "task_id": "POINT", "label": "reference_context_point", "resolution_instance_id": "res"}]
        )
        output = materialize_from_assignments(assignments)
        self.assertTrue(bool(output.iloc[0]["materialized_from_assignment"]))

    def test_native_release_materialization_preserves_assignment_label(self) -> None:
        assignments = pd.DataFrame(
            [
                {
                    "assignment_id": "a1",
                    "sample_id": "r1",
                    "label": "low_relative_moisture_point",
                    "train_inclusion_status": "INCLUDED",
                    "semantic_assignment_admissible": True,
                    "semantic_contract_hash": "contract",
                }
            ]
        )
        output = materialize_label_release_frame(
            assignments,
            task_kind="POINT",
            task_id="point",
            horizon_id="NONE",
        )
        self.assertEqual(output.iloc[0]["label_name"], "low_relative_moisture_point")
        self.assertEqual(output.iloc[0]["label_status"], "LABELED")
        self.assertTrue(bool(output.iloc[0]["intrinsic_eligibility"]))

    def test_native_release_materializes_same_y_transfer_identity(self) -> None:
        transfers = pd.DataFrame(
            [
                {
                    "same_y_transfer_id": "transfer-1",
                    "sample_id": "r1",
                    "transferred_label": "reference_context_point",
                    "source_assignment_id": "point-1",
                    "intrinsic_transfer_status": "ELIGIBLE",
                    "semantic_contract_hash": "contract",
                }
            ]
        )
        output = materialize_label_release_frame(
            transfers,
            task_kind="SAME_Y",
            task_id="same_y",
            horizon_id="3h",
        )
        self.assertEqual(output.iloc[0]["assignment_id"], "transfer-1")
        self.assertEqual(output.iloc[0]["source_assignment_id"], "point-1")
        self.assertEqual(output.iloc[0]["label_name"], "reference_context_point")

    def test_native_release_manifest_hashes_task_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_path = root / "tasks" / "point" / "assignments.parquet"
            task_path.parent.mkdir(parents=True)
            pd.DataFrame([{"sample_id": "r1", "label_name": "reference", "assignment_id": "a1"}]).to_parquet(task_path, index=False)
            manifest = build_label_release_manifest(
                root,
                semantic_contract_id="contract-id",
                semantic_contract_hash="contract-hash",
                operationalization_id="PRIMARY",
                task_paths={"point": task_path},
            )
            self.assertEqual(manifest["tasks"]["point"]["row_count"], 1)
            self.assertTrue(manifest["tasks"]["point"]["sha256"])

    def test_evaluation_consumes_native_release_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "run_metadata").mkdir()
            tasks = {
                "point": root / "tasks" / "point" / "assignments.parquet",
                "same_y/3h": root / "tasks" / "same_y" / "horizon_3h" / "assignments.parquet",
                "same_y/8h": root / "tasks" / "same_y" / "horizon_8h" / "assignments.parquet",
                "temporal/3h": root / "tasks" / "temporal" / "horizon_3h" / "assignments.parquet",
                "temporal/8h": root / "tasks" / "temporal" / "horizon_8h" / "assignments.parquet",
            }
            for path in tasks.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(
                    [{
                        "assignment_id": path.stem,
                        "sample_id": "r1",
                        "label_name": "reference_context_point",
                        "label_status": "LABELED",
                        "intrinsic_eligibility": True,
                        "semantic_contract_hash": "contract",
                        "source_assignment_id": pd.NA,
                    }]
                ).to_parquet(path, index=False)
            manifest = build_label_release_manifest(
                root,
                semantic_contract_id="contract-id",
                semantic_contract_hash="contract",
                operationalization_id="PRIMARY",
                task_paths=tasks,
            )
            (root / "run_metadata" / "label_release_manifest.json").write_text(
                __import__("json").dumps(manifest), encoding="utf-8"
            )
            sources = load_native_label_sources(root)
            self.assertEqual(set(sources.point_labels_train["task_id"].unique()), {"v0_point_train", "v1_point_train"})
            self.assertEqual(sources.v2_same_y_labels.iloc[0]["task_id"], "v2_same_y_3h")

    def test_strict_linkage_controls_delta_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "continuity").mkdir()
            (root / "continuity" / "strict_continuity_contract.yaml").write_text(
                "allowed_gap_minutes: [13, 17]\n", encoding="utf-8"
            )
            formulas = {"VPD_MAGNUS_V1": "VPD_MAGNUS", "MOISTURE_RISE_V1": "CURRENT_MINUS_STRICT_PREVIOUS", "EC_SHIFT_ABS_V1": "ABS_CURRENT_MINUS_STRICT_PREVIOUS"}
            derived_registry = pd.DataFrame(
                [
                    {"derived_evidence_id": evidence_id, "transform_id": evidence_id, "transform_version": "v1", "source_field_ids": "x", "source_units": "u", "output_unit": "u", "formula_expression_or_formula_id": formula, "previous_observation_policy": "STRICT_PREVIOUS_ONLY", "absolute_value_applied": False, "clipping_policy": "FAIL", "null_policy": "PROPAGATE", "infinity_policy": "FAIL", "rounding_policy": "NONE", "comparison_precision": "FULL", "code_reference_hash": "hash"}
                    for evidence_id, formula in formulas.items()
                ]
            )
            contract = replace(_contract_for_tests(), run_dir=root, derived_evidence_registry=derived_registry)
            frame = pd.DataFrame(
                {
                    "record.id": ["r1", "r2", "r3"],
                    "record.segment_id": ["s1", "s1", "s1"],
                    "sample_time_utc": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:15:00Z", "2026-01-01T00:45:00Z"], utc=True),
                    "environment_id": ["E1"] * 3,
                    "npk.soil_moisture_pct": [50.0, 55.0, 60.0],
                    "npk.ec": [1.0, 2.0, 4.0],
                    "sht.temp_c": [25.0, 25.0, 25.0],
                    "sht.humidity_pct": [50.0, 50.0, 50.0],
                }
            )
            linked = build_continuity_primitives(frame, contract)
            enriched = build_derived_evidence(linked, contract)
            self.assertTrue(bool(enriched.loc[1, "strictly_consecutive_from_previous"]))
            self.assertFalse(bool(enriched.loc[2, "strictly_consecutive_from_previous"]))
            self.assertEqual(float(enriched.loc[1, "moisture_rise_delta"]), 5.0)
            self.assertTrue(pd.isna(enriched.loc[2, "moisture_rise_delta"]))


def _operationalization() -> pd.Series:
    return pd.Series({"operationalization_id": "PRIMARY", "q_contract_id": "Q10", "persistence_contract_id": "K3_PRIMARY"})


def _contract_for_tests() -> NativeContract:
    matrix_rows = []
    for low in ("POSITIVE", "NEGATIVE"):
        for thermal in ("POSITIVE", "NEGATIVE", "NOT_EVALUABLE"):
            for rise in ("POSITIVE", "NEGATIVE", "NOT_EVALUABLE"):
                for ec in ("POSITIVE", "NEGATIVE", "NOT_EVALUABLE"):
                    matrix_rows.append({"compatibility_row_id": f"{low}-{thermal}-{rise}-{ec}", "low_state": low, "thermal_state": thermal, "rise_state": rise, "ec_state": ec, "resolution_id": "candidate"})
    return NativeContract(
        run_dir=Path("."),
        run_manifest={"semantic_contract_frozen": True, "native_engine_implemented": False, "downstream_runners_unlocked": False},
        semantic_contract_hash="contract",
        semantic_contract_id="contract-id",
        primary_operationalization_id="PRIMARY",
        operationalizations=pd.DataFrame([_operationalization()]),
        q_registry=pd.DataFrame([{"threshold_id": "LOW_MOISTURE_Q10", "threshold_value": 59.96}]),
        persistence_registry=pd.DataFrame([{"contract_id": "K3_PRIMARY", "selected_k": 3}]),
        derived_evidence_registry=pd.DataFrame(),
        window_contracts={},
        point_compatibility_matrix=pd.DataFrame(matrix_rows),
        point_resolution_contract={},
        temporal_resolution_contract={},
    )


def _firings(states: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in states.to_dict(orient="records"):
        for rule_id, state in (("LOW_RELATIVE_MOISTURE", row["low_state"]), ("THERMAL_CONTEXT", row["thermal_state"]), ("MOISTURE_RISE", row["rise_state"]), ("EC_SHIFT", row["ec_state"])):
            rows.append({"rule_firing_id": f"{row['sample_id']}-{rule_id}", "sample_id": row["sample_id"], "task_id": "POINT", "rule_id": rule_id, "evidence_state": state})
    return pd.DataFrame(rows).convert_dtypes()
