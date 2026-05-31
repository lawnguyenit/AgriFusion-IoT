from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from Backend.Benchmark.context_classifier.src.data.label_schemes import infer_label_scheme_from_context_labels


@dataclass
class TabularDataBundle:
    feature_names: list[str]
    class_names: list[str]
    train_features: np.ndarray
    validation_features: np.ndarray
    test_features: np.ndarray
    train_labels: np.ndarray
    validation_labels: np.ndarray
    test_labels: np.ndarray
    scaler: StandardScaler
    imputer: SimpleImputer


@dataclass
class SequenceDataBundle:
    feature_names: list[str]
    class_names: list[str]
    train_features: np.ndarray
    validation_features: np.ndarray
    test_features: np.ndarray
    train_labels: np.ndarray
    validation_labels: np.ndarray
    test_labels: np.ndarray
    scaler_mean: np.ndarray
    scaler_std: np.ndarray


def _load_split_frame(build_run_dir: Path, split_name: str, file_name: str) -> pd.DataFrame:
    path = build_run_dir / "splits" / split_name / file_name
    if not path.exists():
        raise FileNotFoundError(f"Split file not found: {path}")
    return pd.read_csv(path)


def _class_names_from_manifest(build_run_dir: Path) -> list[str]:
    manifest = load_build_manifest(build_run_dir)
    class_names = manifest.get("class_names")
    if not isinstance(class_names, list) or not class_names:
        label_summary_path = build_run_dir / "context_label_summary.json"
        if label_summary_path.exists():
            summary = json.loads(label_summary_path.read_text(encoding="utf-8"))
            summary_class_names = summary.get("class_names")
            if isinstance(summary_class_names, list) and summary_class_names:
                class_names = summary_class_names
            else:
                context_counts = summary.get("context_label_counts")
                if isinstance(context_counts, dict) and context_counts:
                    inferred_scheme = infer_label_scheme_from_context_labels(list(context_counts.keys()))
                    if inferred_scheme is not None:
                        class_names = list(inferred_scheme.class_names)
    if not isinstance(class_names, list) or not class_names:
        raise ValueError(
            f"Build manifest/summary does not contain a valid class_names list: {build_run_dir}"
        )
    return [str(name) for name in class_names]


def _encode_labels(series: pd.Series, class_to_id: dict[str, int]) -> np.ndarray:
    mapped = series.astype(str).map(class_to_id)
    if mapped.isna().any():
        missing = sorted(series[mapped.isna()].astype(str).unique().tolist())
        raise ValueError(f"Found unsupported labels: {missing}")
    return mapped.to_numpy(dtype=np.int64)


def _tabular_feature_columns(df: pd.DataFrame) -> list[str]:
    blacklist = {
        "timestamp",
        "context_label",
        "data_origin",
        "is_synthetic",
        "split_name",
        "source_reference",
        "event_primary",
        "event_labels",
        "packet_loss_flag",
        "suspected_cause",
        "cause_confidence",
    }
    numeric_columns = []
    for column in df.columns:
        if column in blacklist:
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            numeric_columns.append(column)
    return numeric_columns


def load_tabular_bundle(build_run_dir: Path, experiment_name: str) -> TabularDataBundle:
    file_name_map = {
        "v0": "tabular_v0.csv",
        "v1": "tabular_v1.csv",
        "v2": "tabular_v2.csv",
        "v3": "tabular_v3.csv",
    }
    file_name = file_name_map[experiment_name]
    train_df = _load_split_frame(build_run_dir, "train", file_name)
    validation_df = _load_split_frame(build_run_dir, "validation", file_name)
    test_df = _load_split_frame(build_run_dir, "test", file_name)
    class_names = _class_names_from_manifest(build_run_dir)
    class_to_id = {name: index for index, name in enumerate(class_names)}

    feature_names = _tabular_feature_columns(train_df)
    train_features = train_df[feature_names].to_numpy(dtype=np.float32)
    validation_features = validation_df[feature_names].to_numpy(dtype=np.float32)
    test_features = test_df[feature_names].to_numpy(dtype=np.float32)
    train_labels = _encode_labels(train_df["context_label"], class_to_id)
    validation_labels = _encode_labels(validation_df["context_label"], class_to_id)
    test_labels = _encode_labels(test_df["context_label"], class_to_id)

    imputer = SimpleImputer(strategy="median")
    train_imputed = imputer.fit_transform(train_features)
    validation_imputed = imputer.transform(validation_features)
    test_imputed = imputer.transform(test_features)

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_imputed).astype(np.float32)
    validation_scaled = scaler.transform(validation_imputed).astype(np.float32)
    test_scaled = scaler.transform(test_imputed).astype(np.float32)

    return TabularDataBundle(
        feature_names=feature_names,
        class_names=list(class_names),
        train_features=train_scaled,
        validation_features=validation_scaled,
        test_features=test_scaled,
        train_labels=train_labels,
        validation_labels=validation_labels,
        test_labels=test_labels,
        scaler=scaler,
        imputer=imputer,
    )


def _sequence_feature_columns(df: pd.DataFrame) -> list[str]:
    blacklist = {
        "sequence_id",
        "step_index",
        "target_timestamp",
        "target_label",
        "sequence_origin",
        "split_name",
        "timestamp",
        "data_origin",
        "is_synthetic",
    }
    return [column for column in df.columns if column not in blacklist and pd.api.types.is_numeric_dtype(df[column])]


def _tensorize_sequences(
    df: pd.DataFrame,
    feature_names: list[str],
    class_to_id: dict[str, int],
) -> tuple[np.ndarray, np.ndarray]:
    sequences: list[np.ndarray] = []
    labels: list[int] = []
    for _, group in df.groupby("sequence_id", sort=True):
        ordered = group.sort_values("step_index")
        sequences.append(ordered[feature_names].to_numpy(dtype=np.float32))
        labels.append(class_to_id[str(ordered["target_label"].iloc[-1])])
    return np.stack(sequences).astype(np.float32), np.array(labels, dtype=np.int64)


def load_sequence_bundle(build_run_dir: Path) -> SequenceDataBundle:
    train_df = _load_split_frame(build_run_dir, "train", "sequence_long.csv")
    validation_df = _load_split_frame(build_run_dir, "validation", "sequence_long.csv")
    test_df = _load_split_frame(build_run_dir, "test", "sequence_long.csv")
    class_names = _class_names_from_manifest(build_run_dir)
    class_to_id = {name: index for index, name in enumerate(class_names)}

    feature_names = _sequence_feature_columns(train_df)
    train_x, train_y = _tensorize_sequences(train_df, feature_names, class_to_id)
    validation_x, validation_y = _tensorize_sequences(validation_df, feature_names, class_to_id)
    test_x, test_y = _tensorize_sequences(test_df, feature_names, class_to_id)

    flat_train = train_x.reshape(-1, train_x.shape[-1])
    mean = flat_train.mean(axis=0)
    std = flat_train.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)

    train_x = ((train_x - mean) / std).astype(np.float32)
    validation_x = ((validation_x - mean) / std).astype(np.float32)
    test_x = ((test_x - mean) / std).astype(np.float32)

    return SequenceDataBundle(
        feature_names=feature_names,
        class_names=list(class_names),
        train_features=train_x,
        validation_features=validation_x,
        test_features=test_x,
        train_labels=train_y,
        validation_labels=validation_y,
        test_labels=test_y,
        scaler_mean=mean.astype(np.float32),
        scaler_std=std.astype(np.float32),
    )


def load_build_manifest(build_run_dir: Path) -> dict[str, object]:
    manifest_path = build_run_dir / "dataset_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))
