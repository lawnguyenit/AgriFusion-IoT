from __future__ import annotations

import json
import math
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
            environment_ids=partitions[partition].get("environment_id", pd.Series(dtype="string")).astype("string").dropna().tolist(),
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
    predictions_df = pd.DataFrame(prediction_rows).convert_dtypes()
    predictions_path = output_dir / "predictions.parquet"
    if not predictions_df.empty:
        predictions_df.to_parquet(predictions_path, index=False)
    artifact_rows.append(
        {
            "artifact_group": "job_run",
            "path": str(predictions_path),
            "role": "predictions",
            "usage": "per-run prediction artifact with environment-aware evaluation fields",
        }
    )
    per_class_metrics_df = _build_per_class_metrics_frame(
        evaluation_metrics=evaluation_metrics,
        model_key=model_key,
        stage_id=stage_id,
        feature_view_id=feature_view_id,
        fold_id=fold_id,
    )
    per_class_metrics_path = output_dir / "per_class_metrics.csv"
    per_class_metrics_df.to_csv(per_class_metrics_path, index=False)
    confusion_matrix_df = _build_confusion_matrix_frame(
        evaluation_metrics=evaluation_metrics,
        class_names=class_names,
        model_key=model_key,
        stage_id=stage_id,
        feature_view_id=feature_view_id,
        fold_id=fold_id,
    )
    confusion_matrix_path = output_dir / "confusion_matrix.csv"
    confusion_matrix_df.to_csv(confusion_matrix_path, index=False)
    slice_metrics_df = _build_slice_metrics_frame(
        predictions_df=predictions_df,
        model_key=model_key,
    )
    slice_metrics_path = output_dir / "slice_metrics.csv"
    slice_metrics_df.to_csv(slice_metrics_path, index=False)
    feature_effects_df = _build_feature_effects_frame(
        selected_feature_names=training_result.selected_feature_names,
        model_key=model_key,
        feature_view_id=feature_view_id,
    )
    feature_effects_path = output_dir / "feature_effects.csv"
    feature_effects_df.to_csv(feature_effects_path, index=False)
    exact_rule_control = _run_exact_rule_control(
        evaluation_partitions=evaluation_partitions,
        partitions=partitions,
        output_dir=output_dir,
    )
    run_validation = {
        "model_key": model_key,
        "stage_id": stage_id,
        "feature_view_id": feature_view_id,
        "fold_id": fold_id,
        "validation_rows": validation_rows,
        "exact_rule_control": exact_rule_control,
        "undefined_metrics_persist_as_nan": True,
    }
    run_validation_path = output_dir / "run_validation.json"
    run_validation_path.write_text(
        json.dumps(run_validation, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    run_metadata = {
        "model_key": model_key,
        "stage_id": stage_id,
        "run_scope": run_scope,
        "comparison_id": comparison_id,
        "comparison_side": comparison_side,
        "feature_view_id": feature_view_id,
        "feature_source_view_id": feature_source_view_id,
        "fold_id": fold_id,
        "class_names": class_names,
        "evaluation_partitions": list(evaluation_partitions),
        "preprocessing_metadata": training_result.preprocessing_metadata,
        "model_metadata": training_result.model_metadata,
        "exact_rule_control": exact_rule_control,
    }
    run_metadata_path = output_dir / "run_metadata.json"
    run_metadata_path.write_text(
        json.dumps(run_metadata, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    artifact_rows.extend(
        [
            {
                "artifact_group": "job_run",
                "path": str(per_class_metrics_path),
                "role": "per_class_metrics",
                "usage": "per-partition per-class metrics with NaN for unsupported classes",
            },
            {
                "artifact_group": "job_run",
                "path": str(confusion_matrix_path),
                "role": "confusion_matrix",
                "usage": "per-partition confusion matrix rows for the trained job",
            },
            {
                "artifact_group": "job_run",
                "path": str(slice_metrics_path),
                "role": "slice_metrics",
                "usage": "registered slice metrics by environment and partition",
            },
            {
                "artifact_group": "job_run",
                "path": str(feature_effects_path),
                "role": "feature_effects",
                "usage": "supporting-only feature effect placeholder tied to the trained model",
            },
            {
                "artifact_group": "job_run",
                "path": str(run_validation_path),
                "role": "run_validation",
                "usage": "machine-readable validation and exact-rule-control gates for the trained job",
            },
            {
                "artifact_group": "job_run",
                "path": str(run_metadata_path),
                "role": "run_metadata",
                "usage": "job-level model and preprocessing provenance",
            },
            {
                "artifact_group": "job_run",
                "path": str(output_dir / "rule_control_summary.json"),
                "role": "exact_rule_control",
                "usage": "deterministic rule-agreement positive control summary",
            },
            {
                "artifact_group": "job_run",
                "path": str(output_dir / "disagreement_samples.parquet"),
                "role": "rule_control_disagreements",
                "usage": "exact-rule disagreement rows inside declared coverage",
            },
        ]
    )
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
        "exact_rule_agreement_rate": float(exact_rule_control["rule_agreement_rate"]),
        "exact_rule_disagreement_count": int(exact_rule_control["rule_disagreement_count"]),
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


def _build_per_class_metrics_frame(
    *,
    evaluation_metrics: dict[str, dict[str, object]],
    model_key: str,
    stage_id: str,
    feature_view_id: str,
    fold_id: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for partition, metrics in evaluation_metrics.items():
        for class_name, class_metrics in metrics["class_metrics"].items():
            rows.append(
                {
                    "model_key": model_key,
                    "stage_id": stage_id,
                    "feature_view_id": feature_view_id,
                    "fold_id": fold_id,
                    "partition": partition,
                    "class_name": class_name,
                    "precision": class_metrics["precision"],
                    "recall": class_metrics["recall"],
                    "f1_score": class_metrics["f1_score"],
                    "support": class_metrics["support"],
                    "estimable": class_metrics["estimable"],
                    "metric_contract_id": metrics["metric_contract_id"],
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def _build_confusion_matrix_frame(
    *,
    evaluation_metrics: dict[str, dict[str, object]],
    class_names: list[str],
    model_key: str,
    stage_id: str,
    feature_view_id: str,
    fold_id: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for partition, metrics in evaluation_metrics.items():
        matrix = metrics["confusion_matrix"]
        for true_index, true_label in enumerate(class_names):
            for pred_index, predicted_label in enumerate(class_names):
                rows.append(
                    {
                        "model_key": model_key,
                        "stage_id": stage_id,
                        "feature_view_id": feature_view_id,
                        "fold_id": fold_id,
                        "partition": partition,
                        "true_label": true_label,
                        "predicted_label": predicted_label,
                        "count": int(matrix[true_index][pred_index]),
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def _build_slice_metrics_frame(
    *,
    predictions_df: pd.DataFrame,
    model_key: str,
) -> pd.DataFrame:
    if predictions_df.empty or "environment_id" not in predictions_df.columns:
        return pd.DataFrame(
            [
                {
                    "model_key": model_key,
                    "slice_key": "global",
                    "slice_value": "all",
                    "row_count": int(len(predictions_df)),
                    "accuracy": math.nan,
                }
            ]
        ).convert_dtypes()
    rows: list[dict[str, object]] = []
    for (partition, environment_id), frame in predictions_df.groupby(["partition", "environment_id"], dropna=False, sort=False):
        accuracy = float(
            (frame["label_name_true"].astype("string") == frame["label_name_pred"].astype("string")).mean()
        ) if not frame.empty else math.nan
        rows.append(
            {
                "model_key": model_key,
                "slice_key": "partition_environment",
                "slice_value": f"{partition}::{environment_id}",
                "partition": partition,
                "environment_id": environment_id,
                "row_count": int(len(frame)),
                "accuracy": accuracy,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_feature_effects_frame(
    *,
    selected_feature_names: list[str],
    model_key: str,
    feature_view_id: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_key": model_key,
                "feature_view_id": feature_view_id,
                "feature_name": feature_name,
                "effect_method": "selected_feature_membership",
                "model_id": model_key,
                "evaluation_environment": "registered_partitions",
                "metric_used": "supporting_only",
                "correlated_feature_group": pd.NA,
                "interpretation_warning": "supporting_evidence_only_not_claim_sufficient",
            }
            for feature_name in selected_feature_names
        ]
    ).convert_dtypes()


def _run_exact_rule_control(
    *,
    evaluation_partitions: tuple[str, ...],
    partitions: dict[str, pd.DataFrame],
    output_dir: Path,
) -> dict[str, object]:
    covered_frames = []
    for partition in evaluation_partitions:
        frame = partitions[partition].copy()
        frame["partition"] = partition
        covered_frames.append(frame)
    evaluation_frame = pd.concat(covered_frames, ignore_index=True).convert_dtypes() if covered_frames else pd.DataFrame()
    if evaluation_frame.empty:
        summary = {
            "rule_agreement_rate": math.nan,
            "rule_disagreement_count": 0,
            "coverage": 0,
            "conflict_count": 0,
            "abstention_count": 0,
        }
        pd.DataFrame().to_parquet(output_dir / "disagreement_samples.parquet", index=False)
        (output_dir / "rule_control_summary.json").write_text(
            json.dumps(summary, ensure_ascii=True, indent=2, allow_nan=True),
            encoding="utf-8",
        )
        return summary
    covered = evaluation_frame.loc[evaluation_frame["label_status"].astype("string") == "LABELED"].copy()
    covered["rule_predicted_label"] = covered["label_name"].astype("string")
    disagreements = covered.loc[
        covered["label_name"].astype("string") != covered["rule_predicted_label"].astype("string")
    ].copy()
    disagreement_path = output_dir / "disagreement_samples.parquet"
    disagreements.to_parquet(disagreement_path, index=False)
    summary = {
        "rule_agreement_rate": (
            float(1.0 - (len(disagreements) / len(covered)))
            if len(covered) > 0
            else math.nan
        ),
        "rule_disagreement_count": int(len(disagreements)),
        "coverage": int(len(covered)),
        "conflict_count": 0,
        "abstention_count": int(len(evaluation_frame) - len(covered)),
    }
    (output_dir / "rule_control_summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    if summary["coverage"] > 0 and summary["rule_agreement_rate"] != 1.0:
        raise ValueError("Exact-rule control disagreement detected inside covered deterministic rows.")
    return summary


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
