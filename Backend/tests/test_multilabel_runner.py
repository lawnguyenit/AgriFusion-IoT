from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, hash_dataframe_rows, stable_hash_object
from Backend.Benchmark.pretrain_audit import PretrainAuditConfig, run_pretrain_audit
from Backend.Benchmark.model_suite.multilabel import MultiLabelRunConfig, run_independent_binary_heads
from Backend.Benchmark.model_suite.multilabel.runner import _derive_joint_predictions
from Backend.Benchmark.model_suite.multilabel.entity_metrics import build_entity_metrics
from Backend.Benchmark.model_suite.multilabel.temporal_bootstrap import build_temporal_bootstrap_metrics
from Backend.Benchmark.model_suite.multilabel.stuard_controls import StuardControlConfig, run_stuard_control_arms
from Backend.Benchmark.model_suite.multilabel.stuard_acquisition_controls import run_stuard_acquisition_controls


class MultiLabelRunnerTests(unittest.TestCase):
    def test_entity_metrics_marks_single_class_as_not_estimable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            labels = pd.DataFrame({
                "sample_id": ["a", "b", "c", "d"],
                "entity_id": ["line_1", "line_1", "line_2", "line_2"],
                "timestamp": pd.date_range("2024-01-01", periods=4, freq="h"),
            })
            source = Path(temp_dir) / "labels.parquet"
            labels.to_parquet(source, index=False)
            predictions = pd.DataFrame({
                "fold_id": ["f1"] * 4,
                "partition": ["test"] * 4,
                "sample_id": ["a", "b", "c", "d"],
                "target": ["target.x"] * 4,
                "y_true": [0, 1, 0, 1],
                "y_pred": pd.array([0, 1, 0, pd.NA], dtype="Int64"),
                "positive_probability": [0.1, 0.9, 0.2, float("nan")],
                "probability_threshold": [0.5] * 4,
                "x_observable": [True, True, True, False],
                "prediction_status": ["PREDICTED"] * 3 + ["MODEL_ABSTAIN_NO_X"],
            })
            result = build_entity_metrics(predictions, source).set_index("entity_id")
            self.assertTrue(result.loc["line_1", "within_entity_estimable"])
            self.assertFalse(result.loc["line_2", "within_entity_estimable"])
            self.assertEqual(result.loc["line_2", "estimability_status"], "probabilistic_losses_only")
            self.assertTrue(pd.isna(result.loc["line_2", "roc_auc"]))
            self.assertTrue(bool(result.loc["line_2", "probabilistic_loss_estimable"]))
            self.assertAlmostEqual(float(result.loc["line_2", "brier_score"]), 0.04)
            self.assertAlmostEqual(float(result.loc["line_2", "log_loss"]), -math.log(0.8))
            self.assertEqual(result.loc["line_2", "known_truth_count"], 2)
            self.assertEqual(result.loc["line_2", "known_but_no_x_count"], 1)
            self.assertEqual(result.loc["line_2", "evaluated_known_count"], 1)

    def test_temporal_bootstrap_reports_prevalence_and_reproducible_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            labels = pd.DataFrame({
                "sample_id": [f"s{i}" for i in range(8)],
                "timestamp": pd.date_range("2024-01-01", periods=8, freq="6h"),
            })
            source = Path(temp_dir) / "labels.parquet"
            labels.to_parquet(source, index=False)
            predictions = pd.DataFrame({
                "fold_id": ["f1"] * 8,
                "partition": ["test"] * 8,
                "sample_id": labels["sample_id"],
                "target": ["target.x"] * 8,
                "y_true": [0, 1] * 4,
                "positive_probability": [0.2, 0.8] * 4,
            })
            result = build_temporal_bootstrap_metrics(predictions, source, repetitions=100, seed=41)
            self.assertEqual(result.loc[0, "temporal_cluster_count"], 2)
            self.assertEqual(result.loc[0, "positive_prevalence"], 0.5)
            self.assertEqual(result.loc[0, "bootstrap_status"], "complete")
            self.assertLessEqual(result.loc[0, "log_loss_ci_low"], result.loc[0, "log_loss_ci_high"])

    def test_joint_state_preserves_each_independent_positive_combination(self) -> None:
        rows = []
        for sample_id, co, nox in (("ref", 0, 0), ("co", 1, 0), ("nox", 0, 1), ("both", 1, 1), ("unknown", 1, pd.NA)):
            for target, truth in (("target.co", co), ("target.nox", nox)):
                rows.append({
                    "fold_id": "f1", "partition": "test", "sample_id": sample_id,
                    "target": target, "y_true": truth, "y_pred": co if target == "target.co" else (0 if nox is pd.NA else nox),
                    "positive_probability": 0.75, "probability_threshold": 0.5,
                })
        joint = _derive_joint_predictions(pd.DataFrame(rows).convert_dtypes(), ("target.co", "target.nox"))
        states = joint.set_index("sample_id")["joint_true_state"]

        self.assertEqual(states["ref"], "REF")
        self.assertEqual(states["co"], "CO")
        self.assertEqual(states["nox"], "NOX")
        self.assertEqual(states["both"], "CO+NOX")
        self.assertTrue(pd.isna(states["unknown"]))

    def test_trains_independent_heads_and_preserves_unknown_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features = pd.DataFrame({
                "sample_id": [f"s{i}" for i in range(8)],
                "value": pd.Series([pd.NA, 1., 2., 3., 4., 5., 6., pd.NA], dtype="Float64"),
            })
            feature_path = root / "features.parquet"
            features.to_parquet(feature_path, index=False)
            registry_path = root / "registry.json"
            group = ["value"]
            registry_path.write_text(json.dumps({
                "identifier_columns": ["sample_id"],
                "ordered_feature_columns": group,
                "ordered_feature_columns_hash": stable_hash_object(group),
                "feature_groups": {"values": {
                    "columns": group,
                    "columns_hash": stable_hash_object(group),
                    "values_hash": hash_dataframe_rows(features[group]),
                }},
                "matrix_sha256": _sha256(feature_path),
                "matrix_schema_hash": dataframe_schema_hash(features),
                "row_count": len(features),
            }), encoding="utf-8")
            labels = pd.DataFrame({
                "sample_id": features["sample_id"],
                "target.co": [pd.NA, 0, 0, 1, 1, 1, 0, 1],
                "target.nox": [0, pd.NA, 0, 1, 0, 1, 1, pd.NA],
            }).convert_dtypes()
            labels_path = root / "labels.parquet"
            labels.to_parquet(labels_path, index=False)
            splits = pd.DataFrame({
                "sample_id": features["sample_id"],
                "fold_id": ["fold_0"] * 8,
                "partition": ["train"] * 6 + ["test"] * 2,
            })
            splits_path = root / "splits.parquet"
            splits.to_parquet(splits_path, index=False)
            audit = run_pretrain_audit(PretrainAuditConfig(
                feature_matrix_path=feature_path,
                feature_registry_path=registry_path,
                labels_path=labels_path,
                splits_path=splits_path,
                selected_groups=("values",),
                target_columns=("target.co", "target.nox"),
                output_root=root / "audits",
                training_label_policy="per_head_known",
            ))

            run = run_independent_binary_heads(MultiLabelRunConfig(
                audit_dir=audit.output_dir,
                target_columns=("target.co", "target.nox"),
                model_key="logistic_regression",
                output_root=root / "models",
                require_observable_features=True,
            ))
            manifest = json.loads((run.output_dir / "run_manifest.json").read_text(encoding="utf-8"))
            predictions = pd.read_parquet(run.output_dir / "predictions.parquet")

            self.assertEqual(run.status, "complete")
            self.assertEqual(len(manifest["heads"]), 2)
            co_head = manifest["heads"]["fold_0/target.co"]
            nox_head = manifest["heads"]["fold_0/target.nox"]
            self.assertEqual(co_head["train_sample_count"], 5)
            self.assertEqual(nox_head["train_sample_count"], 4)
            self.assertNotEqual(co_head["train_sample_hash"], nox_head["train_sample_hash"])
            self.assertEqual(manifest["training_cohort_policy"], "per_head_known")
            self.assertEqual(predictions["joint_true_state"].isna().sum(), 1)
            self.assertEqual(predictions.loc[predictions["joint_true_state"].isna(), "sample_id"].iloc[0], "s7")
            no_x_row = predictions.loc[predictions["sample_id"].eq("s7")].iloc[0]
            self.assertEqual(no_x_row["prediction_status::target.co"], "MODEL_ABSTAIN_NO_X")
            self.assertTrue(pd.isna(no_x_row["y_pred::target.co"]))
            self.assertTrue(pd.isna(no_x_row["probability::target.co"]))
            self.assertEqual(nox_head["train_known_no_x_excluded_count"], 1)
            co_eval = json.loads((run.output_dir / "fold_0" / "target_co" / "metrics_test.json").read_text(encoding="utf-8"))
            self.assertEqual(co_eval["partition_row_count"], 2)
            self.assertEqual(co_eval["target_known_count"], 2)
            self.assertEqual(co_eval["known_truth_no_x_count"], 1)
            self.assertEqual(co_eval["metric_evaluation_count"], 1)
            self.assertTrue((run.output_dir / "artifact_catalog.json").is_file())
            self.assertIn("REF only when every selected head predicts 0", manifest["joint_state_policy"])
            self.assertIn("joint state is abstain/unknown", manifest["joint_state_policy"])

            single_labels_path = root / "single_labels.parquet"
            labels.loc[:, ["sample_id", "target.co"]].to_parquet(single_labels_path, index=False)
            single_audit = run_pretrain_audit(PretrainAuditConfig(
                feature_matrix_path=feature_path,
                feature_registry_path=registry_path,
                labels_path=single_labels_path,
                splits_path=splits_path,
                selected_groups=("values",),
                target_columns=("target.co",),
                output_root=root / "single_audits",
                training_label_policy="per_head_known",
            ))
            single_run = run_independent_binary_heads(MultiLabelRunConfig(
                audit_dir=single_audit.output_dir,
                target_columns=("target.co",),
                model_key="logistic_regression",
                output_root=root / "single_models",
            ))
            single_manifest = json.loads((single_run.output_dir / "run_manifest.json").read_text(encoding="utf-8"))
            single_metrics = json.loads((single_run.output_dir / "metrics.json").read_text(encoding="utf-8"))
            single_predictions = pd.read_parquet(single_run.output_dir / "predictions.parquet")
            self.assertEqual(single_run.status, "complete")
            self.assertTrue(single_run.run_id.startswith("binary_head_"))
            self.assertEqual(len(single_manifest["heads"]), 1)
            self.assertEqual(single_manifest["head_architecture"], "single_binary_estimator")
            self.assertEqual(len(single_predictions), 2)
            single_joint = single_metrics["joint_metrics"]["fold_0/test"]
            self.assertEqual(single_joint["joint_class_order"], ["REF", "CO"])
            self.assertEqual(len(single_joint["joint_confusion_matrix"]), 2)

    def test_stuard_controls_compare_four_arms_on_the_same_observable_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample_ids = [f"s{i}" for i in range(20)]
            feature_frame = pd.DataFrame({
                "sample_id": sample_ids,
                "soil_temperature_c": [20.0 + i for i in range(20)],
                "soil_ec_us_cm": [400.0 + i for i in range(20)],
                "air_temperature_c": [float("nan") if i % 5 == 0 else 25.0 + i for i in range(20)],
                "air_humidity_pct": [float("nan") if i % 5 == 0 else 40.0 + i for i in range(20)],
                "air_co2_ppm": [float("nan") if i % 5 == 0 else 500.0 + i for i in range(20)],
                "air_pressure_hpa": [float("nan") if i % 5 == 0 else 1000.0 + i for i in range(20)],
            })
            feature_path = root / "features.parquet"
            feature_frame.to_parquet(feature_path, index=False)
            group = [
                "soil_temperature_c", "soil_ec_us_cm", "air_temperature_c",
                "air_humidity_pct", "air_co2_ppm", "air_pressure_hpa",
            ]
            registry_path = root / "registry.json"
            registry_path.write_text(json.dumps({
                "identifier_columns": ["sample_id"],
                "ordered_feature_columns": group,
                "ordered_feature_columns_hash": stable_hash_object(group),
                "feature_groups": {"values": {
                    "columns": group,
                    "columns_hash": stable_hash_object(group),
                    "values_hash": hash_dataframe_rows(feature_frame[group]),
                }},
                "matrix_sha256": _sha256(feature_path),
                "matrix_schema_hash": dataframe_schema_hash(feature_frame),
                "row_count": len(feature_frame),
            }), encoding="utf-8")
            target = [i % 2 for i in range(20)]
            labels = pd.DataFrame({
                "sample_id": sample_ids,
                "label_soil_moisture_low_q10_tau1440m": target,
                "entity_id": ["line_1" if i % 2 else "line_2" for i in range(20)],
                "timestamp": pd.date_range("2024-01-01", periods=20, freq="h"),
            })
            labels_path = root / "labels.parquet"
            labels.to_parquet(labels_path, index=False)
            source_labels = pd.DataFrame({
                "sample_id": sample_ids,
                "entity_id": ["line_1" if i % 2 else "line_2" for i in range(20)],
                "timestamp": pd.date_range("2024-01-01", periods=20, freq="h"),
            })
            source_labels_path = root / "source_labels.parquet"
            source_labels.to_parquet(source_labels_path, index=False)
            split_frame = pd.DataFrame({
                "sample_id": sample_ids,
                "fold_id": ["fold_0"] * 20,
                "partition": ["train"] * 12 + ["validation"] * 4 + ["test"] * 4,
            })
            splits_path = root / "splits.parquet"
            split_frame.to_parquet(splits_path, index=False)
            audit = run_pretrain_audit(PretrainAuditConfig(
                feature_matrix_path=feature_path,
                feature_registry_path=registry_path,
                labels_path=labels_path,
                splits_path=splits_path,
                selected_groups=("values",),
                target_columns=("label_soil_moisture_low_q10_tau1440m",),
                output_root=root / "audits",
                training_label_policy="per_head_known",
            ))
            evaluation_ids = sample_ids[12:]
            sensor_predictions = root / "sensor_predictions.parquet"
            pd.DataFrame({
                "sample_id": evaluation_ids,
                "target": ["label_soil_moisture_low_q10_tau1440m"] * 8,
                "positive_probability": [0.1 if target[i] == 0 else 0.9 for i in range(12, 20)],
                "prediction_status": ["PREDICTED"] * 8,
            }).to_parquet(sensor_predictions, index=False)
            result = run_stuard_control_arms(StuardControlConfig(
                audit_dir=audit.output_dir,
                target_column="label_soil_moisture_low_q10_tau1440m",
                sensor_predictions_path=sensor_predictions,
                output_root=root / "controls",
                model_key="logistic_regression",
                random_seed=17,
            ))
            metrics = pd.read_csv(result / "control_metrics.csv")
            contrasts = pd.read_csv(result / "control_contrasts.csv")
            manifest = json.loads((result / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(metrics["arm"]), {"global_train_prior", "line_train_prior", "sensor_only", "line_plus_sensors"})
            self.assertEqual(len(metrics), 8)
            self.assertTrue(metrics["metric_evaluation_count"].eq(4).all())
            self.assertFalse(any(column.startswith("paired_") for column in metrics.columns))
            line_sensor = metrics.loc[metrics["arm"].eq("line_plus_sensors")].iloc[0]
            self.assertEqual(line_sensor["sensor_feature_count"], 6)
            self.assertEqual(line_sensor["group_context_columns"], "line")
            self.assertEqual(line_sensor["group_context_count"], 1)
            self.assertEqual(line_sensor["transformed_model_dimension"], 8)
            line_prior = metrics.loc[metrics["arm"].eq("line_train_prior")].iloc[0]
            self.assertTrue(bool(line_prior["uses_entity_identity"]))
            self.assertEqual(len(contrasts), 2)
            self.assertEqual(contrasts.iloc[0]["baseline_arm"], "line_train_prior")
            self.assertFalse(manifest["balanced_sample_weight"])
            self.assertTrue((result / "artifact_catalog.json").is_file())

            acquisition = run_stuard_acquisition_controls(
                audit_dir=audit.output_dir,
                target_column="label_soil_moisture_low_q10_tau1440m",
                output_dir=root / "acquisition_controls",
                model_key="logistic_regression",
                random_seed=17,
                bootstrap_repetitions=30,
            )
            acquisition_metrics = pd.read_csv(acquisition / "control_metrics.csv")
            acquisition_contrasts = pd.read_csv(acquisition / "control_contrasts.csv")
            acquisition_manifest = json.loads((acquisition / "run_manifest.json").read_text(encoding="utf-8"))
            expected_arms = {
                "B_line_plus_all_availability", "B_plus_soil_values",
                "B_plus_environment_values", "B_plus_all_values",
            }
            self.assertEqual(set(acquisition_metrics["arm"]), expected_arms)
            self.assertEqual(len(acquisition_metrics), 8)
            self.assertEqual(len(acquisition_contrasts), 6)
            self.assertEqual(set(acquisition_contrasts["baseline_arm"]), {"B_line_plus_all_availability"})
            self.assertTrue(acquisition_metrics["availability_indicator_count"].eq(6).all())
            self.assertTrue(acquisition_metrics["metric_evaluation_count"].eq(4).all())
            dimensions = acquisition_metrics.set_index("arm")["transformed_model_dimension"].to_dict()
            self.assertEqual(dimensions, {
                "B_line_plus_all_availability": 8,
                "B_plus_soil_values": 10,
                "B_plus_environment_values": 12,
                "B_plus_all_values": 14,
            })
            for features in acquisition_metrics["availability_features"]:
                self.assertEqual(len(json.loads(features)), 6)
            predictions = pd.read_csv(acquisition / "control_predictions.csv")
            for partition in ("validation", "test"):
                ids_by_arm = [
                    set(group["sample_id"].astype("string"))
                    for _, group in predictions.loc[predictions["partition"].eq(partition)].groupby("arm")
                ]
                self.assertEqual(len(ids_by_arm), 4)
                self.assertTrue(all(ids == ids_by_arm[0] for ids in ids_by_arm[1:]))
            self.assertEqual(len(acquisition_manifest["arms"]), 4)
            self.assertEqual(acquisition_manifest["train_fit_count"], 12)


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
