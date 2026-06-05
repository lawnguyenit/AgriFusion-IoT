from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class PreparedDirectExperimentBundle:
    dataframe: pd.DataFrame
    feature_columns: list[str]
    class_names: list[str]
    train_features: np.ndarray
    validation_features: np.ndarray
    test_features: np.ndarray
    train_labels: np.ndarray
    validation_labels: np.ndarray
    test_labels: np.ndarray
    split_counts: dict[str, int]
    source_kind: str
    source_csvs: list[str]
    label_mode: str


def load_build_manifest(build_run_dir: Path) -> dict[str, object]:
    manifest_path = build_run_dir / "dataset_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_prepared_direct_experiment(
    build_run_dir: Path,
    experiment_name: str,
) -> PreparedDirectExperimentBundle:
    experiment_dir = build_run_dir / "experiments" / experiment_name
    dataset_path = experiment_dir / "prepared_dataset.csv"
    schema_path = experiment_dir / "feature_schema.json"
    policy_path = experiment_dir / "label_policy.json"
    if not dataset_path.exists():
        raise FileNotFoundError(f"Prepared dataset not found: {dataset_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Feature schema not found: {schema_path}")
    if not policy_path.exists():
        raise FileNotFoundError(f"Label policy not found: {policy_path}")

    frame = pd.read_csv(dataset_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    feature_columns = [str(name) for name in schema.get("feature_columns", [])]
    class_names = [str(name) for name in policy.get("class_names", [])]
    label_column = str(policy.get("label_column", "selected_label_name"))
    label_id_column = str(policy.get("label_id_column", "selected_label_id"))
    if not feature_columns:
        raise ValueError(f"feature_columns missing in schema: {schema_path}")
    if not class_names:
        raise ValueError(f"class_names missing in policy: {policy_path}")
    if label_column not in frame.columns or label_id_column not in frame.columns:
        raise ValueError(f"Prepared dataset missing selected label columns: {dataset_path}")
    if "split" not in frame.columns:
        raise ValueError(f"Prepared dataset missing split column: {dataset_path}")

    train_frame = frame.loc[frame["split"] == "train"].copy().reset_index(drop=True)
    validation_frame = frame.loc[frame["split"] == "validation"].copy().reset_index(drop=True)
    test_frame = frame.loc[frame["split"] == "test"].copy().reset_index(drop=True)
    if train_frame.empty or validation_frame.empty or test_frame.empty:
        raise ValueError(f"Prepared dataset has an empty split: {dataset_path}")

    return PreparedDirectExperimentBundle(
        dataframe=frame,
        feature_columns=feature_columns,
        class_names=class_names,
        train_features=train_frame[feature_columns].to_numpy(dtype=np.float32),
        validation_features=validation_frame[feature_columns].to_numpy(dtype=np.float32),
        test_features=test_frame[feature_columns].to_numpy(dtype=np.float32),
        train_labels=train_frame[label_id_column].to_numpy(dtype=np.int64),
        validation_labels=validation_frame[label_id_column].to_numpy(dtype=np.int64),
        test_labels=test_frame[label_id_column].to_numpy(dtype=np.int64),
        split_counts={name: int((frame["split"] == name).sum()) for name in ["train", "validation", "test", "excluded_gap"]},
        source_kind=str(schema.get("source_kind", experiment_name)),
        source_csvs=[str(path) for path in schema.get("source_csvs", [])],
        label_mode=str(policy.get("selected_mode", "")),
    )
