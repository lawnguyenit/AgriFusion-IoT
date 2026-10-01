from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, hash_dataframe_rows, stable_hash_object

from .contracts import PretrainAuditConfig, PretrainAuditResult
from .persistence import create_audit_dir, sha256_file, write_audit_artifacts
from .reporting import render_audit_report
from .selection import resolve_feature_selection
from .validation import validate_keyed_inputs


def run_pretrain_audit(config: PretrainAuditConfig) -> PretrainAuditResult:
    if config.training_label_policy not in {"complete_case", "per_head_known"}:
        raise ValueError("training_label_policy must be 'complete_case' or 'per_head_known'.")
    if config.training_label_policy == "per_head_known" and config.exclude_unknown_targets:
        raise ValueError("per_head_known preserves the complete row set; do not combine it with exclude_unknown_targets.")
    if config.max_missing_fraction is not None and not 0.0 <= config.max_missing_fraction <= 1.0:
        raise ValueError("max_missing_fraction must be in [0, 1].")
    feature_matrix = pd.read_parquet(config.feature_matrix_path)
    registry = json.loads(config.feature_registry_path.read_text(encoding="utf-8"))
    if sha256_file(config.feature_matrix_path) != registry.get("matrix_sha256"):
        raise ValueError("Feature superset checksum does not match its registry.")
    if len(feature_matrix) != registry.get("row_count"):
        raise ValueError("Feature superset row count does not match its registry.")
    if dataframe_schema_hash(feature_matrix) != registry.get("matrix_schema_hash"):
        raise ValueError("Feature superset schema does not match its registry.")
    expected_matrix_columns = [
        *registry.get("identifier_columns", []),
        *registry.get("ordered_feature_columns", []),
    ]
    if list(feature_matrix.columns) != expected_matrix_columns:
        raise ValueError("Feature superset ordered columns do not match its registry.")
    if registry.get("ordered_feature_columns_hash") is not None and stable_hash_object(
        registry["ordered_feature_columns"]
    ) != registry["ordered_feature_columns_hash"]:
        raise ValueError("Feature superset ordered feature hash does not match its registry.")
    if registry.get("feature_rows_hash") is not None and hash_dataframe_rows(
        feature_matrix.loc[:, registry["ordered_feature_columns"]]
    ) != registry["feature_rows_hash"]:
        raise ValueError("Feature superset ordered feature values do not match its registry hash.")
    if registry.get("ordered_sample_id_hash") is not None and stable_hash_object(
        feature_matrix["sample_id"].astype("string").tolist()
    ) != registry["ordered_sample_id_hash"]:
        raise ValueError("Feature superset ordered sample IDs do not match its registry hash.")
    if registry.get("source_row_position_hash") is not None:
        if "source_row_position" not in feature_matrix:
            raise ValueError("Feature registry requires source_row_position but matrix omits it.")
        if stable_hash_object(feature_matrix["source_row_position"].tolist()) != registry["source_row_position_hash"]:
            raise ValueError("Feature superset source row positions do not match its registry hash.")
    if registry.get("record_id_hash") is not None:
        if hash_dataframe_rows(feature_matrix.loc[:, ["sample_id"]].astype("string")) != registry["record_id_hash"]:
            raise ValueError("Feature superset sample IDs do not match its dataset-view record ID hash.")
    if registry.get("row_index_hash") is not None:
        row_index_path = config.feature_matrix_path.parent / "row_index.parquet"
        if not row_index_path.is_file():
            raise ValueError("Dataset-view registry requires its shared row_index.parquet sidecar.")
        row_index = pd.read_parquet(row_index_path)
        if hash_dataframe_rows(row_index.astype("string")) != registry["row_index_hash"]:
            raise ValueError("Shared row index does not match its dataset-view registry hash.")
        if not {"record.id", "source_row_position"}.issubset(row_index.columns):
            raise ValueError("Shared row index lacks record.id or source_row_position.")
        if row_index["record.id"].astype("string").tolist() != feature_matrix["sample_id"].astype("string").tolist():
            raise ValueError("Shared row index sample ordering differs from the feature matrix.")
        if row_index["source_row_position"].tolist() != feature_matrix["source_row_position"].tolist():
            raise ValueError("Shared row index source positions differ from the feature matrix.")
    labels = _read_table(config.labels_path)
    splits = _read_table(config.splits_path)
    selected_columns, selection = resolve_feature_selection(
        registry_path=config.feature_registry_path,
        selected_groups=config.selected_groups,
        available_columns=list(feature_matrix.columns),
    )
    for group in config.selected_groups:
        group_columns = registry["feature_groups"][group]["columns"]
        if hash_dataframe_rows(feature_matrix.loc[:, group_columns]) != registry["feature_groups"][group].get("values_hash"):
            raise ValueError(f"Feature group {group!r} values do not match its registry hash.")
    features, aligned_labels, aligned_splits, alignment = validate_keyed_inputs(
        feature_frame=feature_matrix,
        labels=labels,
        splits=splits,
        target_columns=config.target_columns,
    )
    eligibility_audit, eligible_mask = _build_eligibility_audit(
        aligned_labels=aligned_labels,
        aligned_splits=aligned_splits,
        target_columns=config.target_columns,
        exclude_unknown_targets=config.exclude_unknown_targets,
    )
    input_alignment = alignment
    if config.training_label_policy == "per_head_known":
        eligibility_by_id = aligned_labels.set_index("sample_id")
        for target in config.target_columns:
            known_by_id = eligibility_by_id[target].notna()
            train_rows = aligned_splits["partition"].astype("string").eq("train")
            known = aligned_splits["sample_id"].astype("string").map(known_by_id).fillna(False).astype(bool)
            eligibility_audit[f"training_label_known::{target}"] = known.to_numpy()
            eligibility_audit[f"included_for_training::{target}"] = (train_rows & known).to_numpy()
        alignment["training_label_policy"] = "per_head_known"
        alignment["per_head_training_support"] = _per_head_training_support(
            aligned_labels, aligned_splits, config.target_columns
        )
    elif config.exclude_unknown_targets:
        complete_training_by_id = pd.Series(
            eligible_mask.to_numpy(dtype=bool),
            index=aligned_labels["sample_id"].astype("string"),
        )
        train_rows = aligned_splits["partition"].astype("string").eq("train")
        complete_training = aligned_splits["sample_id"].astype("string").map(complete_training_by_id).fillna(False)
        handoff_split_mask = ~train_rows | complete_training.astype(bool)
        aligned_splits = aligned_splits.loc[handoff_split_mask].reset_index(drop=True)
        eligible_ids = set(aligned_splits["sample_id"].astype("string"))
        features = features.loc[features["sample_id"].astype("string").isin(eligible_ids)].reset_index(drop=True)
        aligned_labels = aligned_labels.loc[aligned_labels["sample_id"].astype("string").isin(eligible_ids)].reset_index(drop=True)
        features, aligned_labels, aligned_splits, alignment = validate_keyed_inputs(
            feature_frame=features,
            labels=aligned_labels,
            splits=aligned_splits,
            target_columns=config.target_columns,
        )
        alignment["input_alignment"] = input_alignment
        alignment["eligible_training_sample_count"] = int((train_rows & complete_training).sum())
        alignment["excluded_unknown_training_row_count"] = int((train_rows & ~complete_training.astype(bool)).sum())
        alignment["retained_unknown_evaluation_row_count"] = int(
            (~train_rows & ~complete_training.astype(bool)).sum()
        )
    selected_features = features.loc[:, ["sample_id", *selected_columns]].copy()
    selected_labels = aligned_labels.loc[:, ["sample_id", *config.target_columns]].copy()
    feature_quality = _feature_quality(selected_features, selected_columns, aligned_splits)
    target_support = _target_support(selected_labels, aligned_splits, config.target_columns)
    train_quality = feature_quality.loc[feature_quality["partition"].eq("train")]
    all_missing_count = int(train_quality["all_missing"].sum())
    high_missing_count = 0
    if config.max_missing_fraction is not None:
        high_missing_count = int((train_quality["missing_fraction"] > config.max_missing_fraction).sum())
    blocked_reasons: list[str] = []
    if all_missing_count:
        blocked_reasons.append("selected_features_all_missing")
    if high_missing_count:
        blocked_reasons.append("selected_features_exceed_missing_fraction")
    if any(not row["train_estimable_in_all_folds"] for row in alignment["target_status"].values()):
        blocked_reasons.append("one_or_more_targets_are_not_estimable_in_every_train_fold")
    if config.training_label_policy == "complete_case" and any(
        not row["training_labels_complete_in_all_folds"] for row in alignment["target_status"].values()
    ):
        blocked_reasons.append("one_or_more_targets_have_missing_training_labels")
    support_gate = None
    if config.support_gate_path is not None:
        support_gate = _audit_external_support_gate(config.support_gate_path, config.target_columns)
        if not support_gate["all_selected_targets_pass"]:
            blocked_reasons.append("one_or_more_targets_fail_external_support_gate")
    status = "blocked" if blocked_reasons else "ready_for_model_policy_review"
    run_id, output_dir = create_audit_dir(config.output_root)
    selection.update({
        "feature_count": len(selected_columns),
        "ordered_feature_columns_hash": stable_hash_object(selected_columns),
    })
    manifest: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "audit_status": status,
        "blocked_reasons": blocked_reasons,
        "source_artifacts": {
            "feature_matrix_path": str(config.feature_matrix_path.resolve()),
            "feature_matrix_sha256": sha256_file(config.feature_matrix_path),
            "feature_registry_path": str(config.feature_registry_path.resolve()),
            "feature_registry_sha256": sha256_file(config.feature_registry_path),
            "labels_path": str(config.labels_path.resolve()),
            "labels_sha256": sha256_file(config.labels_path),
            "splits_path": str(config.splits_path.resolve()),
            "splits_sha256": sha256_file(config.splits_path),
            **({
                "support_gate_path": str(config.support_gate_path.resolve()),
                "support_gate_sha256": sha256_file(config.support_gate_path),
            } if config.support_gate_path is not None else {}),
        },
        "upstream_lineage": {
            key: registry[key]
            for key in ("dataset_id", "intake_manifest_path", "intake_manifest_sha256", "canonical_path", "canonical_sha256")
            if key in registry
        },
        "selection": selection,
        "target_columns": list(config.target_columns),
        "training_label_policy": config.training_label_policy,
        "alignment": alignment,
        "support_gate": support_gate,
        "feature_quality": {
            "all_missing_count": all_missing_count,
            "max_missing_fraction_gate": config.max_missing_fraction,
            "high_missing_count": high_missing_count,
            "feature_quality_hash": stable_hash_object(feature_quality.to_dict(orient="records")),
        },
        "model_fit_performed": False,
    }
    write_audit_artifacts(
        output_dir=output_dir,
        selected_features=selected_features,
        labels=selected_labels,
        splits=aligned_splits,
        feature_quality=feature_quality,
        target_support=target_support,
        eligibility_audit=eligibility_audit,
        manifest=manifest,
    )
    (output_dir / "report.md").write_text(render_audit_report(manifest), encoding="utf-8")
    return PretrainAuditResult(
        run_id=run_id,
        output_dir=output_dir,
        row_count=int(len(selected_features)),
        feature_count=len(selected_columns),
        target_count=len(config.target_columns),
        status=status,
    )


def _per_head_training_support(
    labels: pd.DataFrame, splits: pd.DataFrame, targets: tuple[str, ...]
) -> dict[str, dict[str, object]]:
    labels_by_id = labels.set_index("sample_id")
    output: dict[str, dict[str, object]] = {}
    for target in targets:
        output[target] = {}
        for fold_id, rows in splits.groupby("fold_id", sort=True):
            train_ids = rows.loc[rows["partition"].astype("string").eq("train"), "sample_id"].astype("string")
            values = labels_by_id.loc[train_ids, target].dropna()
            counts = values.value_counts().to_dict()
            output[target][str(fold_id)] = {
                "known_training_count": int(len(values)),
                "unknown_training_count": int(len(train_ids) - len(values)),
                "class_counts": {str(key): int(value) for key, value in counts.items()},
                "estimable": bool(values.nunique() == 2),
            }
    return output


def _build_eligibility_audit(
    *,
    aligned_labels: pd.DataFrame,
    aligned_splits: pd.DataFrame,
    target_columns: tuple[str, ...],
    exclude_unknown_targets: bool,
) -> tuple[pd.DataFrame, pd.Series]:
    eligible = aligned_labels.loc[:, list(target_columns)].notna().all(axis=1)
    rows = aligned_splits.loc[:, [column for column in ("sample_id", "fold_id", "partition") if column in aligned_splits]].copy()
    eligibility_by_id = pd.Series(
        eligible.to_numpy(dtype=bool),
        index=aligned_labels["sample_id"].astype("string"),
    )
    rows["sample_id"] = rows["sample_id"].astype("string")
    rows["training_labels_complete"] = rows["sample_id"].map(eligibility_by_id).astype("boolean")
    if rows["training_labels_complete"].isna().any():
        raise ValueError("Could not resolve eligibility for every split sample.")
    is_train = rows["partition"].astype("string").eq("train") if "partition" in rows else pd.Series(False, index=rows.index)
    rows["included_in_handoff"] = (~is_train | rows["training_labels_complete"].astype(bool)) if exclude_unknown_targets else True
    if target_columns:
        reason_parts: list[pd.Series] = []
        for target in target_columns:
            status_column = target.replace("label_", "status_", 1) if target.startswith("label_") else f"status.{target}"
            if status_column in aligned_labels.columns:
                status_by_id = pd.Series(
                    aligned_labels[status_column].astype("string").fillna("UNKNOWN_STATUS").to_numpy(),
                    index=aligned_labels["sample_id"].astype("string"),
                )
                reason_parts.append(rows["sample_id"].map(status_by_id).astype("string"))
            else:
                known_by_id = pd.Series(
                    aligned_labels[target].notna().to_numpy(),
                    index=aligned_labels["sample_id"].astype("string"),
                )
                reason_parts.append(rows["sample_id"].map(known_by_id).map({True: "KNOWN_TARGET", False: "UNKNOWN_TARGET"}).astype("string"))
        combined = pd.concat(reason_parts, axis=1)
        rows["eligibility_reason"] = combined.apply(lambda values: "|".join(values.astype(str)), axis=1)
    else:
        rows["eligibility_reason"] = "NO_TARGET_SELECTED"
    rows["cohort_policy"] = "exclude_unknown_training_rows_keep_evaluation" if exclude_unknown_targets else "retain_all_rows"
    return rows, eligible if exclude_unknown_targets else pd.Series(True, index=aligned_labels.index, dtype=bool)
def _audit_external_support_gate(path: Path, target_columns: tuple[str, ...]) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"External support gate artifact does not exist: {path}")
    support = pd.read_csv(path)
    required = {"label_column", "partition", "support_gate_pass"}
    if not required.issubset(support.columns):
        raise ValueError(f"External support gate artifact is missing columns: {sorted(required - set(support.columns))}")
    per_target: dict[str, dict[str, object]] = {}
    for target in target_columns:
        rows = support.loc[support["label_column"].astype("string").eq(target)]
        expected_partitions = {"train", "validation", "test"}
        observed_partitions = set(rows["partition"].astype("string"))
        passes = (
            observed_partitions == expected_partitions
            and len(rows) == 3
            and rows["support_gate_pass"].astype("boolean").fillna(False).all()
        )
        per_target[target] = {
            "status": "PASS" if passes else "FAIL_OR_MISSING",
            "partition_status": {
                str(row.partition): bool(row.support_gate_pass)
                for row in rows.itertuples(index=False)
            },
        }
    return {
        "profile_id": "SUPPORT_PROFILE_OBSERVED_MIN_7D_V1_TEMPORAL_EXTERNAL_MAPPING",
        "all_selected_targets_pass": all(item["status"] == "PASS" for item in per_target.values()),
        "targets": per_target,
    }


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path).convert_dtypes()
    raise ValueError(f"Unsupported table format: {path.suffix}; use parquet or CSV.")


def _feature_quality(features: pd.DataFrame, columns: list[str], splits: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    scopes: list[tuple[str, pd.DataFrame]] = [("ALL", features)]
    split_keys = [key for key in ("fold_id", "partition") if key in splits.columns]
    for key_values, split_rows in splits.groupby(split_keys, dropna=False, sort=True):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        scope_id = "/".join(str(value) for value in key_values)
        sample_ids = split_rows["sample_id"].astype("string").drop_duplicates().tolist()
        scopes.append((scope_id, features.loc[features["sample_id"].isin(sample_ids)]))
    for scope_id, scoped_features in scopes:
        for column in columns:
            series = scoped_features[column]
            known = series.dropna()
            parts = scope_id.split("/")
            partition = parts[-1] if scope_id != "ALL" else "ALL"
            fold_id = parts[0] if scope_id != "ALL" and len(parts) > 1 else "ALL"
            rows.append(
                {
                    "scope_id": scope_id,
                    "fold_id": fold_id,
                    "partition": partition,
                    "feature": column,
                    "dtype": str(series.dtype),
                    "row_count": int(len(series)),
                    "missing_count": int(series.isna().sum()),
                    "missing_fraction": float(series.isna().mean()) if len(series) else 0.0,
                    "distinct_non_null_values": int(known.nunique()),
                    "all_missing": bool(known.empty),
                    "constant_non_null": bool(len(known) > 0 and known.nunique() <= 1),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def _target_support(labels: pd.DataFrame, splits: pd.DataFrame, targets: tuple[str, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    labels_by_id = labels.set_index("sample_id")
    for column in targets:
        split_values = splits.loc[:, [name for name in ("fold_id", "partition", "sample_id") if name in splits.columns]].copy()
        split_values[column] = split_values["sample_id"].map(labels_by_id[column])
        grouping = [name for name in ("fold_id", "partition") if name in split_values.columns]
        for keys, part in split_values.groupby(grouping, dropna=False, sort=True):
            if not isinstance(keys, tuple):
                keys = (keys,)
            for value, count in part[column].value_counts(dropna=True).items():
                rows.append({"fold_id": keys[0] if "fold_id" in grouping else pd.NA, "partition": keys[-1], "target": column, "value": str(value), "count": int(count)})
            missing_count = int(part[column].isna().sum())
            if missing_count:
                rows.append({"fold_id": keys[0] if "fold_id" in grouping else pd.NA, "partition": keys[-1], "target": column, "value": "<MISSING>", "count": missing_count})
    return pd.DataFrame(rows).convert_dtypes()
