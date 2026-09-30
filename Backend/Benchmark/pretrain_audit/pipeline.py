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
    if any(not row["training_labels_complete_in_all_folds"] for row in alignment["target_status"].values()):
        blocked_reasons.append("one_or_more_targets_have_missing_training_labels")
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
        },
        "upstream_lineage": {
            key: registry[key]
            for key in ("dataset_id", "intake_manifest_path", "intake_manifest_sha256", "canonical_path", "canonical_sha256")
            if key in registry
        },
        "selection": selection,
        "target_columns": list(config.target_columns),
        "alignment": alignment,
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
