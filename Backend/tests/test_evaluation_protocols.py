from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.evaluation_protocols.diagnostics import RollingFoldSpec
from Backend.Benchmark.evaluation_protocols.lineage import PRIMARY_PROTOCOL_ID, build_primary_protocol_artifacts
from Backend.Benchmark.evaluation_protocols.pipeline.consumption import (
    assert_no_forbidden_protocol_columns,
    build_comparison_training_manifest,
    build_task_training_manifest,
    load_dataset_view_feature_artifacts,
)
from Backend.Benchmark.evaluation_protocols.pipeline.layout import (
    build_artifact_catalog,
    build_evaluation_artifact_layout,
)
from Backend.Benchmark.evaluation_protocols.pipeline.tranche0_contracts import (
    build_comparison_registry,
    build_e1_fold_registry,
)
from Backend.Benchmark.evaluation_protocols.pipeline.reporting import write_benchmark_readiness_report
from Backend.Benchmark.evaluation_protocols.lineage.v6_partitions import build_fold_v6_event_assignments


class EvaluationProtocolsTests(unittest.TestCase):
    def test_primary_protocol_locks_5day_folds_and_runner_contract(self) -> None:
        fold_manifest = pd.DataFrame(
            [
                {
                    "fold_id": fold_id,
                    "partition": partition,
                    "block_days": 5,
                    "primary_benchmark_eligible": True,
                    "stress_analysis_eligible": True,
                    "status_reason": "temporal_completeness_passed",
                    "failed_criteria": "[]",
                }
                for fold_id in ("fold_01", "fold_02", "fold_03")
                for partition in ("train", "validation", "test")
            ]
        ).convert_dtypes()
        base_split_assignments = pd.DataFrame(
            [
                {"record_id": "r1", "fold_id": "fold_01", "effective_partition": "train"},
                {"record_id": "r2", "fold_id": "fold_02", "effective_partition": "validation"},
                {"record_id": "r3", "fold_id": "p2_target_holdout", "effective_partition": "target_test"},
            ]
        ).convert_dtypes()
        view_split_assignments = pd.DataFrame(
            [
                {"sample_id": "r1", "fold_id": "fold_01", "view_id": "v0_point_train", "effective_partition": "train"},
                {"sample_id": "r2", "fold_id": "fold_02", "view_id": "v2_same_y_3h", "effective_partition": "validation"},
                {"sample_id": "r3", "fold_id": "p2_target_holdout", "view_id": "v0_point_train", "effective_partition": "target_test"},
            ]
        ).convert_dtypes()
        matched_validation = pd.DataFrame(
            [
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "matched_cohort_id": "v0_vs_v2_mini_3h__fold_01__train",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "matched_record_count": 2,
                    "record_set_hash": "hash_a",
                    "exact_record_id_set_equality": True,
                    "exact_ordering_equality": True,
                    "exact_same_y_label_equality": True,
                    "no_duplicate_record_ids": True,
                    "no_p2_rows_in_p1_fold": True,
                    "no_purge_ineligible_v2_anchor": True,
                }
            ]
        ).convert_dtypes()
        matched_manifests = {
            "v0_vs_v2_mini_3h.csv": pd.DataFrame(
                [
                    {
                        "comparison_id": "v0_vs_v2_mini_3h",
                        "matched_cohort_id": "v0_vs_v2_mini_3h__fold_01__train",
                        "fold_id": "fold_01",
                        "partition": "train",
                        "record_id": "r1",
                        "record_id_order": 1,
                        "label": "normal_point",
                        "record_set_hash": "hash_a",
                    },
                    {
                        "comparison_id": "v0_vs_v2_mini_3h",
                        "matched_cohort_id": "v0_vs_v2_mini_3h__fold_01__train",
                        "fold_id": "fold_01",
                        "partition": "train",
                        "record_id": "r2",
                        "record_id_order": 2,
                        "label": "normal_point",
                        "record_set_hash": "hash_a",
                    },
                ]
            ).convert_dtypes()
        }

        artifacts = build_primary_protocol_artifacts(
            five_day_fold_manifest=fold_manifest,
            base_split_assignments=base_split_assignments,
            view_split_assignments=view_split_assignments,
            matched_cohort_manifests=matched_manifests,
            matched_cohort_validation=matched_validation,
        )

        self.assertEqual(artifacts.runner_contract["protocol_id"], PRIMARY_PROTOCOL_ID)
        self.assertEqual(artifacts.fold_manifest["fold_id"].astype("string").nunique(), 3)
        self.assertIn("p2_target_holdout", artifacts.base_split_assignments["fold_id"].astype("string").tolist())
        self.assertTrue(artifacts.validation["passed"].astype(bool).all())

    def test_v6_lineage_uses_episode_owned_start_end_for_atomic_boundary_exclusion(self) -> None:
        tz = "Asia/Ho_Chi_Minh"
        spec = RollingFoldSpec(
            fold_id="fold_01",
            train_start=pd.Timestamp("2026-07-01 00:00:00", tz=tz),
            train_end=pd.Timestamp("2026-07-01 01:40:00", tz=tz),
            validation_start=pd.Timestamp("2026-07-01 01:40:00", tz=tz),
            validation_end=pd.Timestamp("2026-07-01 03:20:00", tz=tz),
            test_start=pd.Timestamp("2026-07-01 03:20:00", tz=tz),
            test_end=pd.Timestamp("2026-07-01 05:00:00", tz=tz),
            fold_status="full_candidate",
        )
        event_start = pd.Timestamp("2026-07-01 01:30:00", tz=tz)
        event_end = pd.Timestamp("2026-07-01 01:50:00", tz=tz)
        v6_events = pd.DataFrame(
            [
                {
                    "sample_id": "evt_1",
                    "record.segment_id": "node1_seg_0001",
                    "record_ids": '["r1","r2"]',
                    "event_start_local": event_start.isoformat(),
                    "event_end_local": event_end.isoformat(),
                    "label_status": "LABELED",
                    "label_name": "persistent_low_relative_moisture_event",
                    "record_count": 2,
                }
            ]
        ).convert_dtypes()

        rows, boundary_rows = build_fold_v6_event_assignments(
            v6_events=v6_events,
            spec=spec,
            record_domain={"r1": "P1_SOURCE", "r2": "P1_SOURCE"},
            record_segment={"r1": "node1_seg_0001", "r2": "node1_seg_0001"},
            record_time={"r1": event_start, "r2": event_end},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["effective_partition"], "excluded")
        self.assertEqual(rows[0]["exclusion_reason"], "boundary_event")
        self.assertEqual(len(boundary_rows), 1)

    def test_v6_lineage_rejects_episode_owned_time_mismatch(self) -> None:
        tz = "Asia/Ho_Chi_Minh"
        spec = RollingFoldSpec(
            fold_id="fold_01",
            train_start=pd.Timestamp("2026-07-01 00:00:00", tz=tz),
            train_end=pd.Timestamp("2026-07-01 01:40:00", tz=tz),
            validation_start=pd.Timestamp("2026-07-01 01:40:00", tz=tz),
            validation_end=pd.Timestamp("2026-07-01 03:20:00", tz=tz),
            test_start=pd.Timestamp("2026-07-01 03:20:00", tz=tz),
            test_end=pd.Timestamp("2026-07-01 05:00:00", tz=tz),
            fold_status="full_candidate",
        )
        v6_events = pd.DataFrame(
            [
                {
                    "sample_id": "evt_bad",
                    "record.segment_id": "node1_seg_0001",
                    "record_ids": '["r1","r2"]',
                    "event_start_local": pd.Timestamp("2026-07-01 01:31:00", tz=tz).isoformat(),
                    "event_end_local": pd.Timestamp("2026-07-01 01:50:00", tz=tz).isoformat(),
                    "label_status": "LABELED",
                    "label_name": "persistent_low_relative_moisture_event",
                    "record_count": 2,
                }
            ]
        ).convert_dtypes()

        with self.assertRaises(ValueError):
            build_fold_v6_event_assignments(
                v6_events=v6_events,
                spec=spec,
                record_domain={"r1": "P1_SOURCE", "r2": "P1_SOURCE"},
                record_segment={"r1": "node1_seg_0001", "r2": "node1_seg_0001"},
                record_time={
                    "r1": pd.Timestamp("2026-07-01 01:30:00", tz=tz),
                    "r2": pd.Timestamp("2026-07-01 01:50:00", tz=tz),
                },
            )

    def test_consumption_rejects_protocol_columns_in_label_artifact(self) -> None:
        label_df = pd.DataFrame(
            [
                {
                    "sample_id": "r1",
                    "label_task_id": "v0_point_train",
                    "label_name": "normal_point",
                    "label_status": "LABELED",
                    "intrinsic_eligibility": True,
                    "effective_partition": "train",
                }
            ]
        ).convert_dtypes()

        with self.assertRaises(RuntimeError):
            assert_no_forbidden_protocol_columns(label_df, artifact_name="point_labels_train")

    def test_dataset_view_feature_resolution_pins_allowlist_and_row_index_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            shared_dir = run_dir / "shared"
            view_dir = run_dir / "views" / "v0_minimal_sensor"
            shared_dir.mkdir(parents=True)
            view_dir.mkdir(parents=True)

            row_index_df = pd.DataFrame(
                [
                    {"record.id": "r1", "source_row_position": 0},
                    {"record.id": "r2", "source_row_position": 1},
                ]
            ).convert_dtypes()
            row_index_path = shared_dir / "row_index.parquet"
            row_index_df.to_parquet(row_index_path, index=False)

            source_manifest = {
                "source": {
                    "canonical_history_hash": "canonical_hash",
                    "materialization_config_hash": "materialization_hash",
                }
            }
            (shared_dir / "source_manifest.json").write_text(json.dumps(source_manifest), encoding="utf-8")
            row_index_contract = {
                "parquet_path": str(row_index_path.resolve()),
                "file_hash": "row_index_file_hash",
                "record_id_hash": "record_id_hash",
                "row_count": 2,
            }
            (shared_dir / "row_index_contract.json").write_text(json.dumps(row_index_contract), encoding="utf-8")

            x_path = view_dir / "X.parquet"
            pd.DataFrame({"feature.a": [1.0, 2.0]}).to_parquet(x_path, index=False)
            schema_path = view_dir / "schema.json"
            schema_path.write_text(json.dumps({"columns": [{"name": "feature.a", "dtype": "float64"}]}), encoding="utf-8")
            feature_columns_path = view_dir / "feature_columns.json"
            feature_columns_path.write_text(
                json.dumps(
                    {
                        "allowed_feature_columns": ["feature.a"],
                        "identifier_columns": ["record.id", "source_row_position"],
                        "audit_only_columns": [],
                        "forbidden_columns": ["record.id"],
                    }
                ),
                encoding="utf-8",
            )
            manifest_path = view_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "ordered_feature_list": ["feature.a"],
                        "row_count": 2,
                        "row_index_hash": "row_index_file_hash",
                        "sample_id_hash": "record_id_hash",
                        "feature_artifact_path": str(x_path.resolve()),
                        "feature_schema_path": str(schema_path.resolve()),
                        "feature_columns_path": str(feature_columns_path.resolve()),
                        "feature_generator_config_hash": "generator_hash",
                        "feature_generator_code_commit": "code_commit",
                    }
                ),
                encoding="utf-8",
            )

            artifacts = load_dataset_view_feature_artifacts(run_dir, required_view_ids=("v0_minimal_sensor",))

        resolved = artifacts["v0_minimal_sensor"]
        self.assertEqual(resolved.allowed_feature_columns, ("feature.a",))
        self.assertEqual(resolved.identifier_columns, ("record.id", "source_row_position"))
        self.assertEqual(resolved.sample_id_hash, "record_id_hash")
        self.assertEqual(resolved.row_index_hash, "row_index_file_hash")
        self.assertEqual(resolved.sample_ids, frozenset({"r1", "r2"}))

    def test_task_training_manifest_reconciles_protocol_and_intrinsic_states(self) -> None:
        feature_artifact_path = Path("D:/AgriFusion-IoT/Backend/Benchmark/dataset_views/artifacts/fake/views/v0_minimal_sensor/X.parquet")
        registry_df = pd.DataFrame(
            [
                {
                    "experiment_id": "v0_point",
                    "feature_view_id": "v0_point",
                    "feature_source_view_id": "v0_minimal_sensor",
                    "label_task_id": "v0_point_train",
                    "protocol_view_id": "v0_point_train",
                    "sample_unit": "record",
                    "feature_join_key": "record.id",
                    "label_join_key": "sample_id",
                    "label_artifact_path": "weak_labels::<run_dir>/point/point_labels_train.parquet",
                    "split_artifact_path": "evaluation_protocols::<run_dir>/primary_protocol/folds/view_effective_split_assignments.parquet",
                    "dataset_views_run_dir": "dataset_views::<run_dir>",
                    "feature_artifact_status": "resolved",
                    "scientific_blocker": "",
                    "feature_artifact_ready": True,
                    "feature_schema_ready": True,
                    "feature_join_ready": True,
                    "feature_artifact_path": str(feature_artifact_path),
                    "feature_artifact_hash": "feature_hash",
                    "feature_schema_path": str(feature_artifact_path.with_name("schema.json")),
                    "feature_schema_hash": "schema_hash",
                    "feature_columns_path": str(feature_artifact_path.with_name("feature_columns.json")),
                    "feature_columns_hash": "feature_columns_hash",
                    "feature_generator_config_hash": "generator_hash",
                    "feature_generator_code_commit": "code_commit",
                    "source_canonical_hash": "canonical_hash",
                    "materialization_config_hash": "materialization_hash",
                    "row_index_path": "row_index_path",
                    "row_index_hash": "row_index_hash",
                    "sample_id_hash": "sample_id_hash",
                    "row_count": 2,
                    "allowed_feature_columns_json": "[\"feature.a\"]",
                    "identifier_columns_json": "[\"record.id\",\"source_row_position\"]",
                    "audit_only_columns_json": "[]",
                    "forbidden_columns_json": "[\"record.id\"]",
                }
            ]
        ).convert_dtypes()
        view_assignments = pd.DataFrame(
            [
                {
                    "sample_id": "r1",
                    "view_id": "v0_point_train",
                    "fold_id": "fold_01",
                    "deployment_domain": "P1_SOURCE",
                    "effective_partition": "train",
                    "exclusion_reason": pd.NA,
                },
                {
                    "sample_id": "r2",
                    "view_id": "v0_point_train",
                    "fold_id": "fold_01",
                    "deployment_domain": "P1_SOURCE",
                    "effective_partition": "validation",
                    "exclusion_reason": pd.NA,
                },
            ]
        ).convert_dtypes()
        label_frame = pd.DataFrame(
            [
                {
                    "sample_id": "r1",
                    "label_task_id": "v0_point_train",
                    "label_name": "normal_point",
                    "label_status": "LABELED",
                    "intrinsic_eligibility": True,
                    "intrinsic_exclusion_reason": pd.NA,
                },
                {
                    "sample_id": "r2",
                    "label_task_id": "v0_point_train",
                    "label_name": pd.NA,
                    "label_status": "ABSTAIN_INSUFFICIENT_EVIDENCE",
                    "intrinsic_eligibility": False,
                    "intrinsic_exclusion_reason": "core_environment_not_fully_evaluable",
                },
            ]
        ).convert_dtypes()
        feature_artifacts = {
            "v0_minimal_sensor": type(
                "FeatureArtifact",
                (),
                {
                    "sample_ids": frozenset({"r1", "r2"}),
                },
            )()
        }

        manifest_df, validation_df = build_task_training_manifest(
            registry_df=registry_df,
            view_assignments=view_assignments,
            label_frames={"v0_point_train": label_frame},
            label_paths={"v0_point_train": Path("D:/AgriFusion-IoT/Backend/Benchmark/weak_labels/artifacts/fake/point/point_labels_train.parquet")},
            label_hashes={"v0_point_train": "label_hash"},
            protocol_artifact_path=Path("D:/AgriFusion-IoT/Backend/Benchmark/evaluation_protocols/artifacts/fake/primary_protocol/folds/view_effective_split_assignments.parquet"),
            protocol_artifact_hash="protocol_hash",
            feature_artifacts=feature_artifacts,
            cohort_manifests={},
        )

        self.assertEqual(len(manifest_df), 2)
        self.assertEqual(manifest_df.loc[0, "feature_view_id"], "v0_point")
        self.assertEqual(manifest_df.loc[0, "feature_source_view_id"], "v0_minimal_sensor")
        self.assertTrue(bool(manifest_df.loc[0, "feature_artifact_ready"]))
        self.assertTrue(bool(manifest_df.loc[0, "feature_join_ready"]))
        self.assertEqual(int(validation_df.loc[0, "protocol_eligible_count"]), 2)
        self.assertEqual(int(validation_df.loc[0, "final_trainable_count"]), 1)
        self.assertEqual(int(validation_df.loc[0, "intrinsic_excluded_count"]), 1)
        self.assertEqual(int(validation_df.loc[0, "feature_blocked_count"]), 0)
        self.assertTrue(bool(validation_df.loc[0, "count_assertion_passed"]))
        self.assertEqual(
            manifest_df.loc[manifest_df["sample_id"] == "r2", "intrinsic_exclusion_reason"].iloc[0],
            "core_environment_not_fully_evaluable",
        )

    def test_comparison_training_manifest_tracks_comparison_id_and_feature_view(self) -> None:
        task_training_manifest = pd.DataFrame(
            [
                {
                    "sample_id": "r1",
                    "feature_view_id": "v0_point",
                    "feature_source_view_id": "v0_minimal_sensor",
                    "label_task_id": "v0_point_train",
                    "protocol_view_id": "v0_point_train",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "label_name": "normal_point",
                    "label_status": "LABELED",
                    "intrinsic_eligibility": True,
                    "protocol_eligibility": True,
                    "feature_artifact_ready": True,
                    "feature_join_ready": True,
                    "final_trainability": True,
                    "feature_artifact_path": "x0",
                    "feature_artifact_hash": "hx0",
                    "feature_schema_hash": "sx0",
                    "feature_columns_hash": "cx0",
                    "feature_generator_config_hash": "gx0",
                    "feature_generator_code_commit": "cc0",
                    "source_canonical_hash": "sc0",
                    "sample_id_hash": "sid0",
                },
                {
                    "sample_id": "r1",
                    "feature_view_id": "v2_same_y_mini_3h",
                    "feature_source_view_id": "v2_minimal_sensor_window_3h",
                    "label_task_id": "v2_same_y_3h",
                    "protocol_view_id": "v2_same_y_3h",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "label_name": "normal_point",
                    "label_status": "LABELED",
                    "intrinsic_eligibility": True,
                    "protocol_eligibility": True,
                    "feature_artifact_ready": True,
                    "feature_join_ready": True,
                    "final_trainability": True,
                    "feature_artifact_path": "x2",
                    "feature_artifact_hash": "hx2",
                    "feature_schema_hash": "sx2",
                    "feature_columns_hash": "cx2",
                    "feature_generator_config_hash": "gx2",
                    "feature_generator_code_commit": "cc2",
                    "source_canonical_hash": "sc2",
                    "sample_id_hash": "sid2",
                },
            ]
        ).convert_dtypes()
        cohort_manifests = {
            "v0_vs_v2_mini_3h.csv": pd.DataFrame(
                [
                    {
                        "comparison_id": "v0_vs_v2_mini_3h",
                        "matched_cohort_id": "v0_vs_v2_mini_3h__fold_01__train",
                        "fold_id": "fold_01",
                        "partition": "train",
                        "record_id": "r1",
                        "record_id_order": 1,
                        "label": "normal_point",
                        "record_set_hash": "hash_a",
                    }
                ]
            ).convert_dtypes()
        }

        comparison_df, validation_df = build_comparison_training_manifest(
            task_training_manifest=task_training_manifest,
            cohort_manifests=cohort_manifests,
        )

        self.assertEqual(len(comparison_df), 2)
        self.assertEqual(
            set(comparison_df["comparison_id"].astype("string").tolist()),
            {"v0_vs_v2_mini_3h"},
        )
        self.assertEqual(
            set(comparison_df["feature_view_id"].astype("string").tolist()),
            {"v0_point", "v2_same_y_mini_3h"},
        )
        self.assertTrue(validation_df["count_assertion_passed"].astype(bool).all())

    def test_e1_fold_registry_marks_locked_primary_folds_by_fold_id(self) -> None:
        tz = "Asia/Ho_Chi_Minh"
        fold_specs = [
            RollingFoldSpec(
                fold_id="fold_01",
                train_start=pd.Timestamp("2026-04-01 00:00:00", tz=tz),
                train_end=pd.Timestamp("2026-04-16 00:00:00", tz=tz),
                validation_start=pd.Timestamp("2026-04-16 00:00:00", tz=tz),
                validation_end=pd.Timestamp("2026-04-21 00:00:00", tz=tz),
                test_start=pd.Timestamp("2026-04-21 00:00:00", tz=tz),
                test_end=pd.Timestamp("2026-04-26 00:00:00", tz=tz),
                fold_status="full_candidate",
            ),
            RollingFoldSpec(
                fold_id="fold_03",
                train_start=pd.Timestamp("2026-04-01 00:00:00", tz=tz),
                train_end=pd.Timestamp("2026-04-26 00:00:00", tz=tz),
                validation_start=pd.Timestamp("2026-04-26 00:00:00", tz=tz),
                validation_end=pd.Timestamp("2026-05-01 00:00:00", tz=tz),
                test_start=pd.Timestamp("2026-05-01 00:00:00", tz=tz),
                test_end=pd.Timestamp("2026-05-06 00:00:00", tz=tz),
                fold_status="partial_stress",
            ),
            RollingFoldSpec(
                fold_id="fold_04",
                train_start=pd.Timestamp("2026-04-01 00:00:00", tz=tz),
                train_end=pd.Timestamp("2026-05-01 00:00:00", tz=tz),
                validation_start=pd.Timestamp("2026-05-01 00:00:00", tz=tz),
                validation_end=pd.Timestamp("2026-05-06 00:00:00", tz=tz),
                test_start=pd.Timestamp("2026-05-06 00:00:00", tz=tz),
                test_end=pd.Timestamp("2026-05-11 00:00:00", tz=tz),
                fold_status="full_candidate",
            ),
        ]

        registry = build_e1_fold_registry(
            fold_specs=fold_specs,
            threshold_fit_manifest_hash="threshold_hash",
            preprocessing_fit_manifest_hash="preprocess_hash",
        )

        statuses = registry.set_index("fold_id")["analysis_status"].astype("string").to_dict()
        self.assertEqual(statuses["fold_01"], "PRIMARY_LOCKED")
        self.assertEqual(statuses["fold_03"], "PRIMARY_LOCKED")
        self.assertEqual(statuses["fold_04"], "SECONDARY_EXPLORATORY")

    def test_comparison_registry_marks_8h_history_as_sensitivity_only(self) -> None:
        comparison_registry = build_comparison_registry()
        status_lookup = comparison_registry.set_index("comparison_id")["analysis_status"].astype("string").to_dict()

        self.assertEqual(status_lookup["CMP_HISTORY_MINI_3H"], "PRIMARY_LOCKED")
        self.assertEqual(status_lookup["CMP_HISTORY_FULL_3H"], "PRIMARY_LOCKED")
        self.assertEqual(status_lookup["CMP_HISTORY_MINI_8H"], "SENSITIVITY_ONLY")
        self.assertEqual(status_lookup["CMP_HISTORY_FULL_8H"], "SENSITIVITY_ONLY")

    def test_artifact_catalog_includes_reader_guides(self) -> None:
        layout = build_evaluation_artifact_layout(Path("D:/fake-evaluation-protocol-run"))
        catalog = pd.DataFrame(build_artifact_catalog(layout)).convert_dtypes()
        paths = set(catalog["path"].astype("string").tolist())

        self.assertIn(str(layout.root / "ARTIFACT_GUIDE.md"), paths)
        self.assertIn(str(layout.run_metadata / "README.md"), paths)
        self.assertIn(str(layout.domain_manifests / "README.md"), paths)
        self.assertIn(str(layout.primary_protocol / "README.md"), paths)
        self.assertIn(str(layout.primary_runner / "README.md"), paths)

    def test_write_benchmark_readiness_report_summarizes_scope_and_v2_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "run_metadata").mkdir(parents=True)
            (run_dir / "primary_protocol" / "folds").mkdir(parents=True)
            full_dir = run_dir / "primary_protocol" / "runner" / "full_train"
            full_dir.mkdir(parents=True)
            (run_dir / "temporal_diagnostics" / "v2_coverage").mkdir(parents=True)

            (run_dir / "run_metadata" / "protocol_validation_report.json").write_text(
                json.dumps(
                    {
                        "primary_threshold_value_q10": 60.05,
                        "primary_protocol": {"selected_fold_ids": ["fold_01", "fold_02", "fold_03"]},
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                [
                    {
                        "fold_id": "fold_03",
                        "partition": "test",
                        "unsupported_class_reporting_required": True,
                        "unsupported_views_json": '["v2_same_y_8h","v2_temporal_8h"]',
                    }
                ]
            ).to_csv(run_dir / "primary_protocol" / "folds" / "fold_manifest.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "stage_id": "primary_task_matrix",
                        "partition": "test",
                        "feature_view_id": "v2_same_y_full_3h",
                        "pooled_row_count": 1245,
                        "accuracy": 0.9542,
                        "supported_class_macro_f1": 0.8651,
                        "supported_class_balanced_accuracy": 0.8423,
                    }
                ]
            ).to_csv(full_dir / "pooled_oof_metrics.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "range_name": "P1_LATE_CHAIN",
                        "window_horizon_name": "3h",
                        "row_count": 517,
                        "eligible_count": 441,
                        "eligible_ratio": 0.8530,
                        "insufficient_history_count": 62,
                    },
                    {
                        "range_name": "P1_LATE_CHAIN",
                        "window_horizon_name": "8h",
                        "row_count": 517,
                        "eligible_count": 371,
                        "eligible_ratio": 0.7176,
                        "insufficient_history_count": 132,
                    },
                    {
                        "range_name": "P2_TARGET_DEPLOYMENT",
                        "window_horizon_name": "3h",
                        "row_count": 873,
                        "eligible_count": 704,
                        "eligible_ratio": 0.8064,
                        "insufficient_history_count": 141,
                    },
                    {
                        "range_name": "P2_TARGET_DEPLOYMENT",
                        "window_horizon_name": "8h",
                        "row_count": 873,
                        "eligible_count": 515,
                        "eligible_ratio": 0.5899,
                        "insufficient_history_count": 330,
                    },
                ]
            ).to_csv(run_dir / "temporal_diagnostics" / "v2_coverage" / "v2_coverage_range_summary.csv", index=False)

            report_path = write_benchmark_readiness_report(
                protocol_run_dir=run_dir,
                full_output_dir=full_dir,
                readiness_report={"ready_for_full_benchmark": True},
            )
            report_text = report_path.read_text(encoding="utf-8")

        self.assertIn("READY_FOR_FULL_BENCHMARK", report_text)
        self.assertIn("V6", report_text)
        self.assertIn("P1_LATE_CHAIN", report_text)
        self.assertIn("insufficient_history", report_text)
        self.assertIn("v2_same_y_full_3h", report_text)


if __name__ == "__main__":
    unittest.main()
