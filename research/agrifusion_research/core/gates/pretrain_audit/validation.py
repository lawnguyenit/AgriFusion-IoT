from __future__ import annotations

import pandas as pd


def validate_keyed_inputs(
    *,
    feature_frame: pd.DataFrame,
    labels: pd.DataFrame,
    splits: pd.DataFrame,
    target_columns: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    for name, frame in (("features", feature_frame), ("labels", labels), ("splits", splits)):
        if "sample_id" not in frame.columns:
            raise ValueError(f"{name} artifact must contain sample_id.")
        frame["sample_id"] = frame["sample_id"].astype("string")
        if frame["sample_id"].isna().any():
            raise ValueError(f"{name} artifact contains missing sample_id values.")
    if feature_frame["sample_id"].duplicated().any():
        raise ValueError("Feature superset sample_id values must be unique.")
    if labels["sample_id"].duplicated().any():
        raise ValueError("Label artifact sample_id values must be unique for this audit.")
    split_keys = ["sample_id", *[key for key in ("fold_id", "partition") if key in splits.columns]]
    if splits.duplicated(split_keys).any():
        raise ValueError(f"Split artifact contains duplicate keys {split_keys}.")
    if "partition" not in splits.columns:
        raise ValueError("Split artifact must contain a partition column (train/validation/test).")
    allowed_partitions = {"train", "validation", "test"}
    invalid_partitions = sorted(set(splits["partition"].dropna().astype(str)) - allowed_partitions)
    if splits["partition"].isna().any() or invalid_partitions:
        raise ValueError(f"Split artifact has invalid partition values: {invalid_partitions}.")
    if "fold_id" not in splits.columns:
        splits["fold_id"] = "fold_0"
    if splits["fold_id"].isna().any():
        raise ValueError("Split artifact contains missing fold_id values.")
    partition_counts = splits.groupby(["fold_id", "sample_id"], dropna=False)["partition"].nunique()
    leaked = partition_counts[partition_counts > 1]
    if not leaked.empty:
        raise ValueError(
            "A sample appears in multiple partitions within the same fold; "
            f"examples={list(leaked.index[:5])}."
        )
    if not target_columns or any(column not in labels.columns for column in target_columns):
        missing = [column for column in target_columns if column not in labels.columns]
        raise ValueError(f"Select explicit target columns present in labels; missing: {missing}.")
    if len(set(target_columns)) != len(target_columns):
        raise ValueError("Target column selection contains duplicates.")

    feature_ids = set(feature_frame["sample_id"].dropna().tolist())
    label_ids = set(labels["sample_id"].dropna().tolist())
    split_ids = set(splits["sample_id"].dropna().tolist())
    missing_features = sorted(split_ids - feature_ids)
    missing_labels = sorted(split_ids - label_ids)
    if missing_features or missing_labels:
        raise ValueError(
            "Every protocol sample must have feature and label rows; "
            f"missing_features={len(missing_features)}, missing_labels={len(missing_labels)}."
        )
    selected_ids = set(split_ids)
    ordered_ids = splits["sample_id"].drop_duplicates().tolist()
    feature_aligned = feature_frame.set_index("sample_id", drop=False).loc[ordered_ids].reset_index(drop=True)
    label_aligned = labels.set_index("sample_id", drop=False).loc[ordered_ids].reset_index(drop=True)
    split_aligned = splits.loc[splits["sample_id"].isin(selected_ids)].copy().reset_index(drop=True)
    target_status: dict[str, dict[str, object]] = {}
    for column in target_columns:
        target = label_aligned[column]
        counts = target.value_counts(dropna=True).to_dict()
        target_by_id = label_aligned.set_index("sample_id")[column]
        partition_frame = split_aligned.loc[:, split_keys].copy()
        partition_frame[column] = partition_frame["sample_id"].map(target_by_id)
        group_keys = [key for key in ("fold_id", "partition") if key in partition_frame.columns]
        by_split: dict[str, dict[str, object]] = {}
        for group_values, group in partition_frame.groupby(group_keys, dropna=False, sort=True):
            if not isinstance(group_values, tuple):
                group_values = (group_values,)
            split_name = "/".join(str(value) for value in group_values)
            values = group[column]
            by_split[split_name] = {
                "fold_id": str(group_values[0]) if "fold_id" in group_keys else None,
                "partition": str(group_values[-1]),
                "known_count": int(values.notna().sum()),
                "missing_count": int(values.isna().sum()),
                "distinct_known_values": int(values.nunique(dropna=True)),
                "fit_estimable": bool(values.nunique(dropna=True) >= 2),
                "training_labels_complete": bool(values.notna().all()) if str(group_values[-1]) == "train" else None,
            }
        target_status[column] = {
            "known_count": int(target.notna().sum()),
            "missing_count": int(target.isna().sum()),
            "class_counts": {str(key): int(value) for key, value in counts.items()},
            "distinct_known_values": int(target.nunique(dropna=True)),
            "fit_estimable_on_full_input": bool(target.nunique(dropna=True) >= 2),
            "by_fold_partition": by_split,
            "train_estimable_in_all_folds": bool(
                [row for row in by_split.values() if row["partition"] == "train"]
                and all(row["fit_estimable"] for row in by_split.values() if row["partition"] == "train")
            ),
            "training_labels_complete_in_all_folds": bool(
                [row for row in by_split.values() if row["partition"] == "train"]
                and all(row["training_labels_complete"] for row in by_split.values() if row["partition"] == "train")
            ),
        }
    return feature_aligned, label_aligned, split_aligned, {
        "feature_sample_count": int(len(feature_ids)),
        "label_sample_count": int(len(label_ids)),
        "split_sample_count": int(len(split_ids)),
        "split_row_count": int(len(splits)),
        "audit_sample_count": int(len(ordered_ids)),
        "target_status": target_status,
    }
