from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, hash_dataframe_rows, stable_hash_object
from Backend.Benchmark.pretrain_audit import PretrainAuditConfig, run_pretrain_audit
from Backend.Benchmark.model_suite.multilabel import MultiLabelRunConfig, run_independent_binary_heads
from Backend.Benchmark.model_suite.multilabel.runner import _derive_joint_predictions


class MultiLabelRunnerTests(unittest.TestCase):
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
            features = pd.DataFrame({"sample_id": [f"s{i}" for i in range(8)], "value": [0., 1., 2., 3., 4., 5., 6., 7.]})
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
                "target.co": [0, 0, 0, 1, 1, 1, 0, 1],
                "target.nox": [0, 1, 0, 1, 0, 1, 1, pd.NA],
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
            ))

            run = run_independent_binary_heads(MultiLabelRunConfig(
                audit_dir=audit.output_dir,
                target_columns=("target.co", "target.nox"),
                model_key="logistic_regression",
                output_root=root / "models",
            ))
            manifest = json.loads((run.output_dir / "run_manifest.json").read_text(encoding="utf-8"))
            predictions = pd.read_parquet(run.output_dir / "predictions.parquet")

            self.assertEqual(run.status, "complete")
            self.assertEqual(len(manifest["heads"]), 2)
            self.assertEqual(predictions["joint_true_state"].isna().sum(), 1)
            self.assertEqual(predictions.loc[predictions["joint_true_state"].isna(), "sample_id"].iloc[0], "s7")
            self.assertTrue((run.output_dir / "artifact_catalog.json").is_file())
            self.assertEqual(manifest["joint_state_policy"], "REF only when every selected head predicts 0; otherwise the positive target set")


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
