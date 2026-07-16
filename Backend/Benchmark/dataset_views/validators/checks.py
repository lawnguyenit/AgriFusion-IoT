from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.contracts import ViewSelectionResult


def ensure_parquet_engine() -> str:
    if importlib.util.find_spec("pyarrow") is not None:
        return "pyarrow"
    if importlib.util.find_spec("fastparquet") is not None:
        return "fastparquet"
    raise RuntimeError(
        "Parquet engine is required for dataset_views. Install 'pyarrow' or 'fastparquet' before running this pipeline."
    )


def validate_unique_record_ids(dataframe: pd.DataFrame, key_column: str = "record.id") -> None:
    if key_column not in dataframe.columns:
        raise ValueError(f"Required key column '{key_column}' is missing.")
    if dataframe[key_column].isna().any():
        raise ValueError(f"Required key column '{key_column}' contains missing values.")
    if dataframe[key_column].duplicated().any():
        raise ValueError(f"Required key column '{key_column}' must be unique.")


def validate_selection_result(selection: ViewSelectionResult) -> None:
    if selection.missing_from_canonical:
        missing = ", ".join(selection.missing_from_canonical)
        raise ValueError(
            f"Configured features for view '{selection.view_definition.view_id}' are missing from canonical history: {missing}"
        )
    if selection.missing_from_catalog:
        missing = ", ".join(selection.missing_from_catalog)
        raise ValueError(
            f"Features selected for view '{selection.view_definition.view_id}' are missing from the Layer1 feature catalog: {missing}"
        )
    if selection.excluded_by_blacklist and selection.view_definition.selection_mode == "explicit":
        blocked = ", ".join(selection.excluded_by_blacklist)
        raise ValueError(
            f"View '{selection.view_definition.view_id}' attempted to include globally forbidden fields: {blocked}"
        )
    if selection.unresolved_risks:
        raise ValueError(
            f"View '{selection.view_definition.view_id}' has unresolved feature-governance risks: "
            + "; ".join(selection.unresolved_risks)
        )
    if not selection.ordered_features:
        raise ValueError(f"View '{selection.view_definition.view_id}' resolved to zero features.")


def validate_metadata_separation(metadata_columns: list[str], feature_columns: list[str], label_columns: list[str] | None = None) -> None:
    feature_set = set(feature_columns)
    metadata_overlap = sorted(feature_set.intersection(metadata_columns))
    if metadata_overlap:
        raise ValueError("Metadata columns overlap feature matrix columns: " + ", ".join(metadata_overlap))
    if label_columns is None:
        return
    label_overlap = sorted(feature_set.intersection(label_columns))
    if label_overlap:
        raise ValueError("Label columns overlap feature matrix columns: " + ", ".join(label_overlap))


def validate_row_alignment(reference_length: int, candidate_length: int, artifact_name: str) -> None:
    if reference_length != candidate_length:
        raise ValueError(
            f"Row alignment failure for {artifact_name}: expected {reference_length} rows, got {candidate_length}."
        )


def validate_label_join(row_index_df: pd.DataFrame, labels_df: pd.DataFrame, key_column: str) -> pd.DataFrame:
    validate_unique_record_ids(labels_df, key_column=key_column)
    canonical_keys = set(row_index_df[key_column].tolist())
    label_keys = set(labels_df[key_column].tolist())
    extra_keys = sorted(label_keys.difference(canonical_keys))
    if extra_keys:
        raise ValueError(
            f"Label artifact contains keys that do not exist in canonical history for '{key_column}'. "
            f"Unexpected keys: {', '.join(extra_keys[:5])}"
        )
    merged = row_index_df[[key_column]].merge(labels_df, on=key_column, how="left", sort=False)
    if merged.isna().any(axis=None):
        missing_count = int(merged.isna().any(axis=1).sum())
        raise ValueError(
            f"Label artifact does not cover every canonical row by '{key_column}'. Missing joined rows: {missing_count}."
        )
    return merged


def validate_v6_proxy_exclusion(selected_features: list[str], dependency_registry: dict[str, object]) -> None:
    blocked_types = {"DIRECT_RULE_SOURCE", "DERIVED_RULE_PROXY", "CORRELATED_SURROGATE", "IDENTIFIER", "SPLIT_ONLY", "AUDIT_ONLY"}
    leaking_features = sorted(
        feature_name
        for feature_name in selected_features
        if getattr(dependency_registry.get(feature_name), "dependency_type", None) in blocked_types
    )
    if leaking_features:
        raise ValueError(
            "v6_proxy_reduced still contains blocked proxy-bearing features: " + ", ".join(leaking_features)
        )


def validate_episode_artifact_contract(artifact_path: Path | None, required_columns: tuple[str, ...]) -> None:
    if artifact_path is None or not artifact_path.exists():
        raise ValueError(
            "v6_event_level requires an explicit episode artifact with columns: "
            + ", ".join(required_columns)
        )

    suffix = artifact_path.suffix.lower()
    if suffix == ".parquet":
        dataframe = pd.read_parquet(artifact_path)
    elif suffix == ".csv":
        dataframe = pd.read_csv(artifact_path)
    else:
        raise ValueError(
            f"Unsupported episode artifact format '{artifact_path.suffix}'. Use .parquet or .csv."
        )

    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            "v6_event_level episode artifact is missing required columns: "
            + ", ".join(missing_columns)
        )
    if "episode_id" in dataframe.columns and "record.segment_id" in dataframe.columns:
        raise ValueError("Episode artifacts must not use 'record.segment_id' as the episode identifier.")


def validate_no_infinite_values(dataframe: pd.DataFrame, artifact_name: str) -> None:
    numeric = dataframe.select_dtypes(include=["number", "floating", "integer"])
    if numeric.empty:
        return
    array = numeric.to_numpy(dtype="float64", copy=False)
    if np.isinf(array).any():
        raise ValueError(f"{artifact_name} contains inf or -inf values.")
