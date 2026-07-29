from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from Backend.Benchmark.model_suite.cli import build_parser
from Backend.Benchmark.model_suite.config import TRAINING_PROFILES_PATH
from Backend.Benchmark.model_suite.contracts import ModelUnavailableError
from Backend.Benchmark.model_suite.data import list_training_profiles
from Backend.Benchmark.model_suite.data.scope_resolver import load_stage_specs_for_profile
from Backend.Benchmark.model_suite.pipeline.guides import write_run_guides
from Backend.Benchmark.model_suite.pipeline.training_job import train_tabular_classifier
from Backend.Benchmark.model_suite.registries import (
    DEFAULT_ARTIFACT_ROOT,
    assert_models_available,
    build_estimator,
    inspect_model_availability,
    list_model_profiles,
    resolve_model_profile,
)


class ModelSuiteTests(unittest.TestCase):
    def test_cli_supports_progress_toggle(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--no-progress"])
        self.assertTrue(args.no_progress)

    def test_cli_supports_model_check(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--check-models", "--model-keys", "dummy_majority"])
        self.assertTrue(args.check_models)
        self.assertEqual(args.model_keys, ["dummy_majority"])

    def test_cli_supports_profile_listing(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--list-profiles"])
        self.assertTrue(args.list_profiles)

    def test_training_profiles_include_full_benchmark(self) -> None:
        profiles = {row["profile_name"] for row in list_training_profiles(TRAINING_PROFILES_PATH)}
        self.assertIn("smoke_phase1_protocol", profiles)
        self.assertIn("phase1_primary_tasks", profiles)
        self.assertIn("phase1_primary_comparisons", profiles)
        self.assertIn("phase2_frozen_target_holdout", profiles)
        self.assertIn("full_benchmark_v0_v2", profiles)

    def test_primary_profiles_align_to_current_3h_public_scope(self) -> None:
        for profile_name in (
            "smoke_phase1_protocol",
            "phase1_primary_tasks",
            "phase1_primary_comparisons",
            "phase2_frozen_target_holdout",
            "full_benchmark_v0_v2",
        ):
            stage_specs = load_stage_specs_for_profile(TRAINING_PROFILES_PATH, profile_name)
            for stage_spec in stage_specs:
                feature_views = {str(value) for value in stage_spec.get("feature_views", [])}
                comparison_ids = {str(value) for value in stage_spec.get("comparison_ids", [])}
                self.assertNotIn("v2_same_y_mini_8h", feature_views)
                self.assertNotIn("v2_same_y_full_8h", feature_views)
                self.assertNotIn("v0_vs_v2_mini_8h", comparison_ids)
                self.assertNotIn("v1_vs_v2_full_8h", comparison_ids)

    def test_profile_run_guides_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "model_suite_run"
            (output_dir / "profiles" / "phase1_primary_tasks" / "jobs").mkdir(parents=True, exist_ok=True)

            rows = write_run_guides(output_dir=output_dir, profile_name="phase1_primary_tasks")

            self.assertTrue((output_dir / "ARTIFACT_GUIDE.md").exists())
            self.assertTrue((output_dir / "profiles" / "README.md").exists())
            self.assertTrue((output_dir / "profiles" / "phase1_primary_tasks" / "README.md").exists())
            self.assertTrue((output_dir / "profiles" / "phase1_primary_tasks" / "jobs" / "README.md").exists())
            self.assertIn("artifact_guide", {str(row["role"]) for row in rows})
            self.assertIn("profile_run_guide", {str(row["role"]) for row in rows})
            self.assertIn("job_group_guide", {str(row["role"]) for row in rows})

    def test_smoke_run_guides_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "model_suite_run"
            (output_dir / "smoke_protocol").mkdir(parents=True, exist_ok=True)

            rows = write_run_guides(output_dir=output_dir, profile_name="smoke_phase1_protocol")

            self.assertTrue((output_dir / "ARTIFACT_GUIDE.md").exists())
            self.assertTrue((output_dir / "smoke_protocol" / "README.md").exists())
            self.assertIn("artifact_guide", {str(row["role"]) for row in rows})
            self.assertIn("smoke_protocol_guide", {str(row["role"]) for row in rows})

    def test_model_catalog_exposes_registered_model_keys(self) -> None:
        model_keys = {profile.model_key for profile in list_model_profiles()}

        self.assertEqual(
            model_keys,
            {
                "dummy_majority",
                "logistic_regression",
                "extra_trees",
                "xgboost",
                "realmlp",
                "ft_transformer",
                "tabpfn",
            },
        )
        self.assertEqual(
            DEFAULT_ARTIFACT_ROOT,
            Path("D:/AgriFusion-IoT/Backend/Benchmark/model_suite/artifacts"),
        )

    def test_train_tabular_classifier_writes_bundle_and_manifest(self) -> None:
        profile = resolve_model_profile("dummy_majority")
        train_labels = pd.Series(
            ["normal_point", "low_relative_moisture_point", "normal_point"],
            dtype="string",
        )
        validation_labels = pd.Series(
            ["normal_point", "low_relative_moisture_point"],
            dtype="string",
        )
        test_labels = pd.Series(
            ["low_relative_moisture_point", "normal_point"],
            dtype="string",
        )
        train_features = np.array(
            [
                [1.0, 0.1],
                [0.2, 1.0],
                [1.1, 0.2],
            ],
            dtype=np.float32,
        )
        validation_features = np.array(
            [
                [1.0, 0.2],
                [0.3, 1.1],
            ],
            dtype=np.float32,
        )
        test_features = np.array(
            [
                [0.1, 1.2],
                [1.2, 0.2],
            ],
            dtype=np.float32,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "job"
            result = train_tabular_classifier(
                profile=profile,
                train_features=train_features,
                evaluation_features={
                    "validation": validation_features,
                    "test": test_features,
                },
                train_labels=train_labels,
                allowed_feature_columns=["f1", "f2"],
                train_sample_ids=["r1", "r2", "r3"],
                output_dir=output_dir,
                random_seed=20260717,
                thread_count=1,
                task_metadata={"task_id": "unit_test"},
            )

            self.assertEqual(result.class_names, ["low_relative_moisture_point", "normal_point"])
            self.assertEqual(result.selected_feature_names, ["f1", "f2"])
            self.assertEqual(sorted(result.evaluation_predictions), ["test", "validation"])
            self.assertTrue((output_dir / "dummy_majority.joblib").exists())
            self.assertTrue((output_dir / "model_bundle.joblib").exists())
            self.assertTrue((output_dir / "preprocessing_metadata.json").exists())
            self.assertTrue((output_dir / "model_manifest.json").exists())
            self.assertTrue((output_dir / "training_console.log").exists())

            manifest = json.loads((output_dir / "model_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["model_key"], "dummy_majority")
            self.assertEqual(manifest["task_metadata"]["task_id"], "unit_test")
            self.assertEqual(
                manifest["class_names"],
                ["low_relative_moisture_point", "normal_point"],
            )

    def test_logistic_regression_builder_matches_runtime_api(self) -> None:
        profile = resolve_model_profile("logistic_regression")

        estimator, library_version = build_estimator(
            profile=profile,
            random_seed=20260717,
            thread_count=1,
            class_count=2,
        )

        self.assertEqual(estimator.__class__.__name__, "LogisticRegression")
        self.assertTrue(hasattr(estimator, "fit"))
        self.assertTrue(hasattr(estimator, "predict"))
        self.assertIsInstance(library_version, str)

    def test_dummy_model_reports_available(self) -> None:
        info = inspect_model_availability("dummy_majority")
        self.assertTrue(info.available)
        self.assertEqual(info.model_key, "dummy_majority")
        self.assertIsNone(info.note)

    def test_assert_models_available_accepts_dummy_majority(self) -> None:
        infos = assert_models_available(("dummy_majority",))
        self.assertEqual(len(infos), 1)
        self.assertTrue(infos[0].available)

    def test_ft_transformer_availability_note_contains_install_hint_when_unavailable(self) -> None:
        info = inspect_model_availability("ft_transformer")
        if not info.available:
            self.assertIsNotNone(info.note)
            self.assertIn("install_hint=", str(info.note))

    def test_realmlp_builder_matches_runtime_api(self) -> None:
        profile = resolve_model_profile("realmlp")

        estimator, library_version = build_estimator(
            profile=profile,
            random_seed=20260717,
            thread_count=1,
            class_count=2,
        )

        self.assertTrue(hasattr(estimator, "fit"))
        self.assertTrue(hasattr(estimator, "predict"))
        self.assertTrue(hasattr(estimator, "predict_proba"))
        self.assertIsInstance(library_version, str)

    def test_ft_transformer_builder_matches_runtime_api(self) -> None:
        profile = resolve_model_profile("ft_transformer")

        estimator, library_version = build_estimator(
            profile=profile,
            random_seed=20260717,
            thread_count=1,
            class_count=2,
        )

        self.assertTrue(hasattr(estimator, "fit"))
        self.assertTrue(hasattr(estimator, "predict"))
        self.assertTrue(hasattr(estimator, "predict_proba"))
        self.assertIsInstance(library_version, str)

    def test_tabpfn_builder_requires_token_or_model_path(self) -> None:
        profile = resolve_model_profile("tabpfn")

        with self.assertRaises(ModelUnavailableError):
            build_estimator(
                profile=profile,
                random_seed=20260717,
                thread_count=1,
                class_count=2,
            )


if __name__ == "__main__":
    unittest.main()
