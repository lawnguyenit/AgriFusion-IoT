from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.model_suite.contracts import ModelUnavailableError
from Backend.Benchmark.model_suite.data import extract_partition_matrix, load_feature_frame, parse_allowed_feature_columns
from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification
from Backend.Benchmark.model_suite.pipeline.training_job import train_tabular_classifier
from Backend.Benchmark.model_suite.persistence.model_bundle import write_metrics_payload
from Backend.Benchmark.model_suite.registries import resolve_model_profile
from Backend.Benchmark.model_suite.utils.preprocessing import hash_sample_ids
from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import build_prediction_rows


def run_protocol_model_job(
    *,
    model_key: str,
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
    hyperparameter_overrides: dict[str, object] | None = None,
    use_balanced_sample_weight: bool | None = None,
    evaluation_partitions: tuple[str, ...] = ("validation", "test"),
) -> dict[str, object]:
    feature_source_view_id = str(registry_row["feature_source_view_id"])
    if "record_id_order" in task_rows.columns:
        task_rows = task_rows.sort_values(["partition", "record_id_order", "sample_id"], kind="stable").reset_index(drop=True)
    required_partitions = ("train",) + tuple(evaluation_partitions)
    partitions = {
        partition: task_rows.loc[
            (task_rows["partition"].astype("string") == partition)
            & task_rows["final_trainability"].fillna(False).astype(bool)
        ].copy()
        for partition in required_partitions
    }
    validation_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    artifact_rows: list[dict[str, object]] = []
    for partition, frame in partitions.items():
        validation_rows.append(
            {
                "stage_id": stage_id,
                "model_key": model_key,
                "scope": _build_scope_id(
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
            comparison_validation = _validate_comparison_partition(frame)
            validation_rows.append(
                {
                    "stage_id": stage_id,
                    "model_key": model_key,
                    "scope": _build_scope_id(
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
            "summary": _summary_row(
                model_key=model_key,
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
            "artifact_rows": artifact_rows,
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    train_labels = partitions["train"]["label_name"].astype("string")
    train_class_names = sorted(train_labels.dropna().unique().tolist())
    eval_only_classes_by_partition = {
        partition: sorted(
            set(partitions[partition]["label_name"].astype("string").dropna().unique()) - set(train_class_names)
        )
        for partition in evaluation_partitions
    }
    eval_only_classes = sorted(
        {
            class_name
            for classes in eval_only_classes_by_partition.values()
            for class_name in classes
        }
    )
    validation_rows.append(
        {
            "stage_id": stage_id,
            "model_key": model_key,
            "scope": _build_scope_id(
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
                    "evaluation_only_classes_by_partition": eval_only_classes_by_partition,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        }
    )
    if len(train_class_names) < 2:
        return {
            "summary": _summary_row(
                model_key=model_key,
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
            "artifact_rows": artifact_rows,
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    feature_frame = load_feature_frame(registry_row, feature_cache)
    allowed_feature_columns = parse_allowed_feature_columns(registry_row)
    train_bundle = extract_partition_matrix(feature_frame, partitions["train"], allowed_feature_columns)
    evaluation_bundles = {
        partition: extract_partition_matrix(feature_frame, partitions[partition], allowed_feature_columns)
        for partition in evaluation_partitions
    }
    train_sample_ids = partitions["train"]["sample_id"].astype("string").tolist()
    profile = resolve_model_profile(
        model_key,
        hyperparameter_overrides=dict(hyperparameter_overrides or {}),
        use_balanced_sample_weight=use_balanced_sample_weight,
    )
    try:
        training_result = train_tabular_classifier(
            profile=profile,
            train_features=train_bundle["features"],
            evaluation_features={partition: bundle["features"] for partition, bundle in evaluation_bundles.items()},
            train_labels=train_bundle["labels"],
            allowed_feature_columns=allowed_feature_columns,
            train_sample_ids=train_sample_ids,
            output_dir=output_dir,
            random_seed=random_seed,
            thread_count=thread_count,
            task_metadata={
                "stage_id": stage_id,
                "run_scope": run_scope,
                "comparison_id": comparison_id,
                "comparison_side": comparison_side,
                "feature_view_id": feature_view_id,
                "feature_source_view_id": feature_source_view_id,
                "fold_id": fold_id,
            },
        )
    except ModelUnavailableError as exc:
        return {
            "summary": _summary_row(
                model_key=model_key,
                stage_id=stage_id,
                run_scope=run_scope,
                comparison_id=comparison_id,
                comparison_side=comparison_side,
                feature_view_id=feature_view_id,
                feature_source_view_id=feature_source_view_id,
                fold_id=fold_id,
                status="model_unavailable",
                note=str(exc),
            ),
            "artifact_rows": artifact_rows,
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }
    except ValueError as exc:
        if str(exc) != "zero_selected_features":
            raise
        return {
            "summary": _summary_row(
                model_key=model_key,
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
            "artifact_rows": artifact_rows,
            "validation_rows": validation_rows,
            "prediction_rows": prediction_rows,
        }

    class_names = training_result.class_names
    class_lookup = {label_name: index for index, label_name in enumerate(class_names)}
    evaluation_metrics: dict[str, dict[str, object]] = {}
    for partition in evaluation_partitions:
        y_true = evaluation_bundles[partition]["labels"].map(class_lookup).to_numpy(dtype="int64")
        evaluation_metrics[partition] = summarize_protocol_classification(
            y_true,
            training_result.evaluation_predictions[partition],
            class_names,
        )
    metrics_payload = {
        "evaluation_metrics": evaluation_metrics,
        "class_names": class_names,
        "run_scope": run_scope,
        "comparison_id": comparison_id,
        "comparison_side": comparison_side,
        "model_key": model_key,
    }
    for partition, metrics in evaluation_metrics.items():
        metrics_payload[partition] = metrics
    write_metrics_payload(
        output_dir / "metrics.json",
        metrics_payload,
    )
    artifact_rows.extend(
        _build_job_artifact_rows(
            model_key=model_key,
            stage_id=stage_id,
            feature_view_id=feature_view_id,
            fold_id=fold_id,
            output_dir=output_dir,
            artifact_paths=training_result.artifact_paths,
        )
    )
    for partition in evaluation_partitions:
        y_true = evaluation_bundles[partition]["labels"].map(class_lookup).to_numpy(dtype="int64")
        prediction_rows.extend(
            build_prediction_rows(
                stage_id=stage_id,
                run_scope=run_scope,
                comparison_id=comparison_id,
                comparison_side=comparison_side,
                feature_view_id=feature_view_id,
                feature_source_view_id=feature_source_view_id,
                fold_id=fold_id,
                partition=partition,
                partition_rows=partitions[partition],
                y_true=y_true.tolist(),
                y_pred=training_result.evaluation_predictions[partition],
                y_proba=training_result.evaluation_probabilities.get(partition),
                class_names=class_names,
            )
        )
    for row in prediction_rows:
        row["model_key"] = model_key
    summary_extra = {
        "job_output_dir": str(output_dir),
        "train_count": int(len(partitions["train"])),
        "selected_feature_count": int(len(training_result.selected_feature_names)),
        "evaluation_partitions_json": json.dumps(list(evaluation_partitions), ensure_ascii=True, separators=(",", ":")),
        "imputer_fit_sample_hash": training_result.preprocessing_metadata["imputer_fit_sample_hash"],
        "scaler_fit_sample_hash": training_result.preprocessing_metadata["scaler_fit_sample_hash"],
        "selector_fit_sample_hash": training_result.preprocessing_metadata["selector_fit_sample_hash"],
        "model_fit_sample_hash": training_result.preprocessing_metadata["model_fit_sample_hash"],
        "random_seed": random_seed,
        "thread_count": thread_count,
        "model_library_version": training_result.model_metadata["model_library_version"],
        "preprocessing_library_version": training_result.preprocessing_metadata["preprocessing_library_version"],
    }
    for partition in evaluation_partitions:
        metrics = evaluation_metrics[partition]
        summary_extra[f"{partition}_count"] = int(len(partitions[partition]))
        summary_extra[f"{partition}_supported_class_macro_f1"] = float(metrics["supported_class_macro_f1"])
        summary_extra[f"{partition}_fixed_ontology_macro_f1"] = float(metrics["fixed_ontology_macro_f1"])
        summary_extra[f"{partition}_supported_class_balanced_accuracy"] = float(metrics["supported_class_balanced_accuracy"])
        summary_extra[f"{partition}_unsupported_classes_json"] = json.dumps(
            metrics["unsupported_classes"],
            ensure_ascii=True,
            separators=(",", ":"),
        )
    return {
        "summary": _summary_row(
            model_key=model_key,
            stage_id=stage_id,
            run_scope=run_scope,
            comparison_id=comparison_id,
            comparison_side=comparison_side,
            feature_view_id=feature_view_id,
            feature_source_view_id=feature_source_view_id,
            fold_id=fold_id,
            status="trained",
            note="Training completed.",
            extra=summary_extra,
        ),
        "artifact_rows": artifact_rows,
        "validation_rows": validation_rows,
        "prediction_rows": prediction_rows,
    }


def _summary_row(
    *,
    model_key: str,
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
        "model_key": model_key,
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


def _build_scope_id(
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


def _validate_comparison_partition(partition_rows: pd.DataFrame) -> dict[str, object]:
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
    return {
        "passed": len(hashes) == 1 and computed_hash == hashes[0],
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


def _build_job_artifact_rows(
    *,
    model_key: str,
    stage_id: str,
    feature_view_id: str,
    fold_id: str,
    output_dir: Path,
    artifact_paths: dict[str, str],
) -> list[dict[str, object]]:
    scope_slug = f"{model_key} {stage_id}/{feature_view_id}/{fold_id}"
    rows = [
        {
            "artifact_group": "model_job",
            "path": str(output_dir),
            "role": "job_directory",
            "usage": f"{scope_slug} directory",
        },
        {
            "artifact_group": "model_job",
            "path": str(output_dir / "metrics.json"),
            "role": "job_metrics",
            "usage": f"{scope_slug} held-out metrics",
        },
    ]
    role_map = {
        "model_path": "trained_estimator",
        "bundle_path": "model_bundle",
        "preprocessing_metadata_path": "preprocessing_metadata",
        "model_manifest_path": "model_manifest",
        "training_console_log_path": "training_console_log",
    }
    for key, role in role_map.items():
        artifact_path = artifact_paths.get(key)
        if artifact_path is None:
            continue
        rows.append(
            {
                "artifact_group": "model_job",
                "path": artifact_path,
                "role": role,
                "usage": f"{scope_slug} {role}",
            }
        )
    return rows
