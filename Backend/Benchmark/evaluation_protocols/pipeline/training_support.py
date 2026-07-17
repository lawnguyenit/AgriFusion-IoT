from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from sklearn import __version__ as sklearn_version

from Backend.Benchmark.evaluation_protocols.pipeline.metrics import summarize_protocol_classification
from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import build_prediction_rows

try:
    import xgboost as xgb  # type: ignore
except Exception as exc:  # pragma: no cover
    xgb = None
    XGBOOST_IMPORT_ERROR = exc
else:  # pragma: no cover
    XGBOOST_IMPORT_ERROR = None


def run_xgboost_training_job(
    *,
    stage_id: str,
    run_scope: str,
    comparison_id: str | None,
    comparison_side: str | None,
    feature_view_id: str,
    fold_id: str,
    registry_row: pd.Series,
    task_rows: pd.DataFrame,
    feature_cache: dict[str, pd.DataFrame],
    output_dir: Path,
    random_seed: int,
    thread_count: int,
    n_estimators: int,
    max_depth: int,
    learning_rate: float,
    use_balanced_sample_weight: bool,
) -> dict[str, object]:
    feature_source_view_id = str(registry_row["feature_source_view_id"])
    if "record_id_order" in task_rows.columns:
        task_rows = task_rows.sort_values(["partition", "record_id_order", "sample_id"], kind="stable").reset_index(drop=True)
    partitions = {
        partition: task_rows.loc[
            (task_rows["partition"].astype("string") == partition)
            & task_rows["final_trainability"].fillna(False).astype(bool)
        ].copy()
        for partition in ("train", "validation", "test")
    }
    validation_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []

    for partition, frame in partitions.items():
        validation_rows.append(
            {
                "stage_id": stage_id,
                "scope": build_scope_id(
                    run_scope=run_scope,
                    comparison_id=comparison_id,
                    feature_view_id=feature_view_id,
                    fold_id=fold_id,
                    partition=partition,
                ),
                "passed": not frame.empty,
                "details": json.dumps({"row_count": int(len(frame))}, ensure_ascii=True, separators=(",", ":")),
            }
        )
        if run_scope == "comparison":
            comparison_validation = validate_comparison_partition(frame)
            validation_rows.append(
                {
                    "stage_id": stage_id,
                    "scope": build_scope_id(
                        run_scope=run_scope,
                        comparison_id=comparison_id,
                        feature_view_id=feature_view_id,
                        fold_id=fold_id,
                        partition=f"{partition}::matched_cohort",
                    ),
                    "passed": comparison_validation["passed"],
                    "details": comparison_validation["details"],
                }
            )
    if any(frame.empty for frame in partitions.values()):
        return {
            "summary": summary_row(
                stage_id=stage_id,
                run_scope=run_scope,
                comparison_id=comparison_id,
                comparison_side=comparison_side,
                feature_view_id=feature_view_id,
                feature_source_view_id=feature_source_view_id,
                fold_id=fold_id,
                status="insufficient_partition_rows",
                note="One or more partitions are empty after final_trainability filtering.",
            ),
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    train_labels = partitions["train"]["label_name"].astype("string")
    validation_labels = partitions["validation"]["label_name"].astype("string")
    test_labels = partitions["test"]["label_name"].astype("string")
    train_class_names = sorted(train_labels.dropna().unique().tolist())
    validation_only_classes = sorted(set(validation_labels.dropna().unique()) - set(train_class_names))
    test_only_classes = sorted(set(test_labels.dropna().unique()) - set(train_class_names))
    eval_only_classes = sorted(set(validation_only_classes) | set(test_only_classes))
    validation_rows.append(
        {
            "stage_id": stage_id,
            "scope": build_scope_id(
                run_scope=run_scope,
                comparison_id=comparison_id,
                feature_view_id=feature_view_id,
                fold_id=fold_id,
                partition="class_support",
            ),
            "passed": len(train_class_names) >= 2,
            "details": json.dumps(
                {
                    "train_classes": train_class_names,
                    "validation_only_classes": validation_only_classes,
                    "test_only_classes": test_only_classes,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        }
    )
    if len(train_class_names) < 2:
        return {
            "summary": summary_row(
                stage_id=stage_id,
                run_scope=run_scope,
                comparison_id=comparison_id,
                comparison_side=comparison_side,
                feature_view_id=feature_view_id,
                feature_source_view_id=feature_source_view_id,
                fold_id=fold_id,
                status="unsupported_train_class_support",
                note="Train partition does not contain at least two supported classes.",
                extra={
                    "train_classes_json": json.dumps(train_class_names, ensure_ascii=True, separators=(",", ":")),
                    "unsupported_classes_json": json.dumps(eval_only_classes, ensure_ascii=True, separators=(",", ":")),
                },
            ),
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    feature_frame = load_feature_frame(registry_row, feature_cache)
    allowed_feature_columns = json.loads(str(registry_row["allowed_feature_columns_json"]))
    train_bundle = extract_partition_matrix(feature_frame, partitions["train"], allowed_feature_columns)
    validation_bundle = extract_partition_matrix(feature_frame, partitions["validation"], allowed_feature_columns)
    test_bundle = extract_partition_matrix(feature_frame, partitions["test"], allowed_feature_columns)

    train_sample_ids = partitions["train"]["sample_id"].astype("string").tolist()
    train_sample_hash = hash_sample_ids(train_sample_ids)
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    selector = VarianceThreshold()
    train_imputed = imputer.fit_transform(train_bundle["features"])
    validation_imputed = imputer.transform(validation_bundle["features"])
    test_imputed = imputer.transform(test_bundle["features"])
    train_scaled = scaler.fit_transform(train_imputed)
    validation_scaled = scaler.transform(validation_imputed)
    test_scaled = scaler.transform(test_imputed)
    train_selected = selector.fit_transform(train_scaled)
    validation_selected = selector.transform(validation_scaled)
    test_selected = selector.transform(test_scaled)

    if train_selected.shape[1] == 0:
        return {
            "summary": summary_row(
                stage_id=stage_id,
                run_scope=run_scope,
                comparison_id=comparison_id,
                comparison_side=comparison_side,
                feature_view_id=feature_view_id,
                feature_source_view_id=feature_source_view_id,
                fold_id=fold_id,
                status="zero_selected_features",
                note="VarianceThreshold removed every column.",
            ),
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    class_names = train_class_names
    class_lookup = {label_name: index for index, label_name in enumerate(class_names)}
    y_train = train_bundle["labels"].map(class_lookup).to_numpy(dtype=np.int64)
    y_validation = validation_bundle["labels"].map(class_lookup).to_numpy(dtype=np.int64)
    y_test = test_bundle["labels"].map(class_lookup).to_numpy(dtype=np.int64)

    if xgb is None:
        return {
            "summary": summary_row(
                stage_id=stage_id,
                run_scope=run_scope,
                comparison_id=comparison_id,
                comparison_side=comparison_side,
                feature_view_id=feature_view_id,
                feature_source_view_id=feature_source_view_id,
                fold_id=fold_id,
                status="xgboost_unavailable",
                note=f"{type(XGBOOST_IMPORT_ERROR).__name__}: {XGBOOST_IMPORT_ERROR}" if XGBOOST_IMPORT_ERROR is not None else "xgboost unavailable",
            ),
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    objective = "binary:logistic" if len(class_names) == 2 else "multi:softprob"
    model_kwargs = {
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "learning_rate": learning_rate,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "reg_lambda": 1.0,
        "random_state": random_seed,
        "eval_metric": "logloss" if len(class_names) == 2 else "mlogloss",
        "objective": objective,
        "n_jobs": thread_count,
    }
    if len(class_names) > 2:
        model_kwargs["num_class"] = len(class_names)
    model = xgb.XGBClassifier(**model_kwargs)
    if use_balanced_sample_weight:
        sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
        model.fit(train_selected, y_train, sample_weight=sample_weight)
    else:
        model.fit(train_selected, y_train)

    validation_pred = model.predict(validation_selected)
    test_pred = model.predict(test_selected)
    validation_proba = normalize_prediction_probabilities(model.predict_proba(validation_selected))
    test_proba = normalize_prediction_probabilities(model.predict_proba(test_selected))
    validation_metrics = summarize_protocol_classification(y_validation, validation_pred, class_names)
    test_metrics = summarize_protocol_classification(y_test, test_pred, class_names)

    selected_mask = selector.get_support()
    selected_feature_names = [name for name, keep in zip(allowed_feature_columns, selected_mask, strict=True) if keep]
    preprocessing_metadata = {
        "imputer_fit_sample_hash": train_sample_hash,
        "scaler_fit_sample_hash": train_sample_hash,
        "selector_fit_sample_hash": train_sample_hash,
        "model_fit_sample_hash": train_sample_hash,
        "random_seed": random_seed,
        "model_library_version": xgb.__version__,
        "preprocessing_library_version": sklearn_version,
        "thread_count": thread_count,
        "selected_feature_count": int(len(selected_feature_names)),
        "selected_feature_names": selected_feature_names,
        "use_balanced_sample_weight": bool(use_balanced_sample_weight),
    }
    joblib.dump(model, output_dir / "xgboost.joblib")
    (output_dir / "preprocessing_metadata.json").write_text(
        json.dumps(preprocessing_metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(
            {
                "validation": validation_metrics,
                "test": test_metrics,
                "class_names": class_names,
                "run_scope": run_scope,
                "comparison_id": comparison_id,
                "comparison_side": comparison_side,
            },
            ensure_ascii=True,
            indent=2,
            allow_nan=True,
        ),
        encoding="utf-8",
    )

    prediction_rows.extend(
        build_prediction_rows(
            stage_id=stage_id,
            run_scope=run_scope,
            comparison_id=comparison_id,
            comparison_side=comparison_side,
            feature_view_id=feature_view_id,
            feature_source_view_id=feature_source_view_id,
            fold_id=fold_id,
            partition="validation",
            partition_rows=partitions["validation"],
            y_true=y_validation.tolist(),
            y_pred=validation_pred.tolist(),
            y_proba=validation_proba,
            class_names=class_names,
        )
    )
    prediction_rows.extend(
        build_prediction_rows(
            stage_id=stage_id,
            run_scope=run_scope,
            comparison_id=comparison_id,
            comparison_side=comparison_side,
            feature_view_id=feature_view_id,
            feature_source_view_id=feature_source_view_id,
            fold_id=fold_id,
            partition="test",
            partition_rows=partitions["test"],
            y_true=y_test.tolist(),
            y_pred=test_pred.tolist(),
            y_proba=test_proba,
            class_names=class_names,
        )
    )

    return {
        "summary": summary_row(
            stage_id=stage_id,
            run_scope=run_scope,
            comparison_id=comparison_id,
            comparison_side=comparison_side,
            feature_view_id=feature_view_id,
            feature_source_view_id=feature_source_view_id,
            fold_id=fold_id,
            status="trained",
            note="Training completed.",
            extra={
                "train_count": int(len(partitions["train"])),
                "validation_count": int(len(partitions["validation"])),
                "test_count": int(len(partitions["test"])),
                "selected_feature_count": int(len(selected_feature_names)),
                "validation_supported_class_macro_f1": float(validation_metrics["supported_class_macro_f1"]),
                "validation_fixed_ontology_macro_f1": float(validation_metrics["fixed_ontology_macro_f1"]),
                "validation_supported_class_balanced_accuracy": float(validation_metrics["supported_class_balanced_accuracy"]),
                "test_supported_class_macro_f1": float(test_metrics["supported_class_macro_f1"]),
                "test_fixed_ontology_macro_f1": float(test_metrics["fixed_ontology_macro_f1"]),
                "test_supported_class_balanced_accuracy": float(test_metrics["supported_class_balanced_accuracy"]),
                "test_unsupported_classes_json": json.dumps(test_metrics["unsupported_classes"], ensure_ascii=True, separators=(",", ":")),
                "imputer_fit_sample_hash": train_sample_hash,
                "scaler_fit_sample_hash": train_sample_hash,
                "selector_fit_sample_hash": train_sample_hash,
                "model_fit_sample_hash": train_sample_hash,
                "random_seed": random_seed,
                "thread_count": thread_count,
                "model_library_version": xgb.__version__,
                "preprocessing_library_version": sklearn_version,
            },
        ),
        "validation_rows": validation_rows,
        "prediction_rows": prediction_rows,
    }


def load_feature_frame(registry_row: pd.Series, feature_cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    feature_source_view_id = str(registry_row["feature_source_view_id"])
    cached = feature_cache.get(feature_source_view_id)
    if cached is not None:
        return cached
    x_path = Path(str(registry_row["feature_artifact_path"]))
    row_index_path = Path(str(registry_row["row_index_path"]))
    x_frame = pd.read_parquet(x_path)
    row_index = pd.read_parquet(row_index_path, columns=["record.id"]).convert_dtypes()
    if len(x_frame) != len(row_index):
        raise ValueError(
            f"Feature artifact row count does not match row_index for {feature_source_view_id}: "
            f"{len(x_frame)} != {len(row_index)}."
        )
    feature_frame = x_frame.copy()
    feature_frame.insert(0, "sample_id", row_index["record.id"].astype("string"))
    feature_cache[feature_source_view_id] = feature_frame
    return feature_frame


def extract_partition_matrix(
    feature_frame: pd.DataFrame,
    partition_rows: pd.DataFrame,
    allowed_feature_columns: list[str],
) -> dict[str, object]:
    ordered_sample_ids = partition_rows["sample_id"].astype("string").tolist()
    indexed = feature_frame.set_index("sample_id", drop=False)
    subset = indexed.loc[ordered_sample_ids].copy().reset_index(drop=True)
    return {
        "features": subset.loc[:, allowed_feature_columns].to_numpy(dtype=np.float32),
        "labels": partition_rows["label_name"].astype("string").reset_index(drop=True),
    }


def hash_sample_ids(sample_ids: list[str]) -> str:
    payload = json.dumps(sample_ids, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def summary_row(
    *,
    stage_id: str,
    run_scope: str,
    comparison_id: str | None,
    comparison_side: str | None,
    feature_view_id: str,
    feature_source_view_id: str,
    fold_id: str,
    status: str,
    note: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    row = {
        "stage_id": stage_id,
        "run_scope": run_scope,
        "comparison_id": comparison_id if comparison_id is not None else pd.NA,
        "comparison_side": comparison_side if comparison_side is not None else pd.NA,
        "feature_view_id": feature_view_id,
        "feature_source_view_id": feature_source_view_id,
        "fold_id": fold_id,
        "status": status,
        "note": note,
    }
    if extra:
        row.update(extra)
    return row


def build_scope_id(
    *,
    run_scope: str,
    comparison_id: str | None,
    feature_view_id: str,
    fold_id: str,
    partition: str,
) -> str:
    if run_scope == "comparison" and comparison_id is not None:
        return f"{comparison_id}::{feature_view_id}::{fold_id}::{partition}"
    return f"{feature_view_id}::{fold_id}::{partition}"


def validate_comparison_partition(partition_rows: pd.DataFrame) -> dict[str, object]:
    if partition_rows.empty:
        return {
            "passed": False,
            "details": json.dumps({"reason": "empty_partition"}, ensure_ascii=True, separators=(",", ":")),
        }
    if "record_set_hash" not in partition_rows.columns or "record_id_order" not in partition_rows.columns:
        return {
            "passed": False,
            "details": json.dumps({"reason": "missing_comparison_columns"}, ensure_ascii=True, separators=(",", ":")),
        }
    hashes = partition_rows["record_set_hash"].astype("string").dropna().unique().tolist()
    ordered_rows = partition_rows.sort_values(["record_id_order", "sample_id"], kind="stable")
    sample_ids = ordered_rows["sample_id"].astype("string").tolist()
    computed_hash = hash_sample_ids(sample_ids)
    passed = len(hashes) == 1 and computed_hash == hashes[0]
    return {
        "passed": passed,
        "details": json.dumps(
            {
                "manifest_hashes": hashes,
                "computed_hash": computed_hash,
                "row_count": int(len(partition_rows)),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    }


def normalize_prediction_probabilities(probabilities: np.ndarray | None) -> list[list[float]] | None:
    if probabilities is None:
        return None
    if probabilities.ndim == 1:
        return [[float(value)] for value in probabilities.tolist()]
    return [[float(value) for value in row] for row in probabilities.tolist()]
