from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, hash_dataframe_rows, stable_hash_object
from Backend.Benchmark.pretrain_audit import PretrainAuditConfig, run_pretrain_audit
from Backend.Benchmark.pretrain_audit.selection import resolve_feature_selection


class PretrainAuditTests(unittest.TestCase):
    def test_selects_feature_groups_and_aligns_labels_and_splits_by_sample_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix, registry, labels, splits = self._write_inputs(root)
            result = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=matrix,
                    feature_registry_path=registry,
                    labels_path=labels,
                    splits_path=splits,
                    selected_groups=("values", "window_3h"),
                    target_columns=("target.co", "target.nox"),
                    output_root=root / "audit",
                    max_missing_fraction=0.5,
                )
            )
            manifest = json.loads((result.output_dir / "audit_manifest.json").read_text(encoding="utf-8"))
            selected = pd.read_parquet(result.output_dir / "selected_features.parquet")
            selected_labels = pd.read_parquet(result.output_dir / "selected_labels.parquet")

            self.assertEqual(result.status, "ready_for_model_policy_review")
            self.assertEqual(selected["sample_id"].tolist(), ["s2", "s1", "s3"])
            self.assertEqual(selected.columns.tolist(), ["sample_id", "value", "value__3h_mean"])
            self.assertEqual(selected_labels["sample_id"].tolist(), selected["sample_id"].tolist())
            self.assertEqual(manifest["selection"]["selected_groups"], ["values", "window_3h"])
            self.assertEqual(manifest["alignment"]["target_status"]["target.nox"]["missing_count"], 1)
            self.assertTrue((result.output_dir / "report.md").is_file())

    def test_blocks_all_missing_features_and_rejects_criterion_features(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix, registry, labels, splits = self._write_inputs(root, all_missing=True)
            result = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=matrix,
                    feature_registry_path=registry,
                    labels_path=labels,
                    splits_path=splits,
                    selected_groups=("values",),
                    target_columns=("target.co",),
                    output_root=root / "audit",
                )
            )
            manifest = json.loads((result.output_dir / "audit_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result.status, "blocked")
            self.assertIn("selected_features_all_missing", manifest["blocked_reasons"])

            bad_registry = root / "bad_registry.json"
            self._write_registry(bad_registry, pd.read_parquet(matrix), criterion=True)
            with self.assertRaisesRegex(ValueError, "Non-feature columns"):
                resolve_feature_selection(
                    registry_path=bad_registry,
                    selected_groups=("values",),
                    available_columns=["sample_id", "source_row_position", "criterion.co_gt", "value__3h_mean"],
                )

    def test_blocks_missing_training_labels_and_rejects_cross_partition_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix, registry, labels, splits = self._write_inputs(root)
            label_frame = pd.read_parquet(labels)
            label_frame.loc[label_frame["sample_id"].eq("s1"), "target.nox"] = pd.NA
            label_frame.to_parquet(labels, index=False)
            result = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=matrix,
                    feature_registry_path=registry,
                    labels_path=labels,
                    splits_path=splits,
                    selected_groups=("values",),
                    target_columns=("target.nox",),
                    output_root=root / "audit_missing",
                )
            )
            manifest = json.loads((result.output_dir / "audit_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result.status, "blocked")
            self.assertIn("one_or_more_targets_have_missing_training_labels", manifest["blocked_reasons"])

            split_frame = pd.read_parquet(splits)
            split_frame.loc[len(split_frame)] = ["s1", "test"]
            split_frame.to_parquet(splits, index=False)
            with self.assertRaisesRegex(ValueError, "multiple partitions within the same fold"):
                run_pretrain_audit(
                    PretrainAuditConfig(
                        feature_matrix_path=matrix,
                        feature_registry_path=registry,
                        labels_path=labels,
                        splits_path=splits,
                        selected_groups=("values",),
                        target_columns=("target.nox",),
                        output_root=root / "audit_leak",
                    )
                )

    @staticmethod
    def _write_inputs(root: Path, *, all_missing: bool = False) -> tuple[Path, Path, Path, Path]:
        value = [pd.NA, pd.NA, pd.NA] if all_missing else [1.0, 2.0, 3.0]
        matrix_frame = pd.DataFrame(
            {
                "sample_id": pd.Series(["s1", "s2", "s3"], dtype="string"),
                "source_row_position": [0, 1, 2],
                "value": value,
                "value__3h_mean": [1.0, 1.5, 2.0],
            }
        )
        matrix_path = root / "features.parquet"
        matrix_frame.to_parquet(matrix_path, index=False)
        registry_path = root / "registry.json"
        PretrainAuditTests._write_registry(registry_path, matrix_frame)
        labels_path = root / "labels.parquet"
        pd.DataFrame(
            {
                "sample_id": ["s1", "s2", "s3"],
                "target.co": [0, 1, 1],
                "target.nox": [0, pd.NA, 1],
            }
        ).convert_dtypes().to_parquet(labels_path, index=False)
        splits_path = root / "splits.parquet"
        pd.DataFrame(
            {
                "sample_id": ["s2", "s1", "s3"],
                "partition": ["test", "train", "train"],
            }
        ).to_parquet(splits_path, index=False)
        return matrix_path, registry_path, labels_path, splits_path

    @staticmethod
    def _write_registry(path: Path, frame: pd.DataFrame, *, criterion: bool = False) -> None:
        if criterion:
            frame = frame.rename(columns={"value": "criterion.co_gt"})
            ordered_features = ["criterion.co_gt", "value__3h_mean"]
            groups = {"values": ["criterion.co_gt"], "window_3h": ["value__3h_mean"]}
        else:
            ordered_features = ["value", "value__3h_mean"]
            groups = {"values": ["value"], "window_3h": ["value__3h_mean"]}
        feature_groups = {
            name: {
                "columns": columns,
                "columns_hash": stable_hash_object(columns),
                "values_hash": hash_dataframe_rows(frame.loc[:, columns]),
            }
            for name, columns in groups.items()
        }
        payload = {
            "identifier_columns": ["sample_id", "source_row_position"],
            "ordered_feature_columns": ordered_features,
            "ordered_feature_columns_hash": stable_hash_object(ordered_features),
            "feature_groups": feature_groups,
            "matrix_sha256": hashlib.sha256((path.parent / "features.parquet").read_bytes()).hexdigest(),
            "matrix_schema_hash": dataframe_schema_hash(frame),
            "row_count": len(frame),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
