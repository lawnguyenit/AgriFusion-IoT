from __future__ import annotations

import json
import math
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import f1_score, hamming_loss, precision_score, recall_score
from sklearn.utils.class_weight import compute_sample_weight

from Backend.Benchmark.model_suite.pipeline.training_job import _normalize_prediction_probabilities
from Backend.Benchmark.model_suite.registries import build_estimator, resolve_model_profile
from Backend.Benchmark.model_suite.reporting.plots import write_classification_plots
from Backend.Benchmark.model_suite.utils.preprocessing import fit_preprocessing_bundle, hash_sample_ids
from Backend.Benchmark.model_suite.utils.output_control import capture_python_output

from .contracts import MultiLabelRunConfig, MultiLabelRunResult
from .entity_metrics import build_entity_metrics
from .temporal_bootstrap import build_temporal_bootstrap_metrics
from .inputs import load_reviewed_audit, sha256_file
from .metrics import binary_metrics


def run_independent_binary_heads(config: MultiLabelRunConfig) -> MultiLabelRunResult:
    if not config.target_columns:
        raise ValueError("The binary-head runner requires at least one target.")
    if not 0.0 < config.probability_threshold < 1.0:
        raise ValueError("probability_threshold must be strictly between 0 and 1.")
    if not config.evaluation_partitions or "train" in config.evaluation_partitions:
        raise ValueError("Choose one or more evaluation partitions other than train.")
    features, labels, splits, lineage = load_reviewed_audit(config.audit_dir, config.target_columns)
    feature_columns = lineage["feature_columns"]
    try:
        feature_values = features.loc[:, feature_columns].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Selected model features must be numeric and convertible to float.") from exc
    if not np.isfinite(feature_values[~np.isnan(feature_values)]).all():
        raise ValueError("Selected model features contain infinite values.")
    feature_observable = pd.Series(
        np.isfinite(feature_values).any(axis=1),
        index=features["sample_id"].astype("string"),
        dtype="boolean",
    )
    profile = resolve_model_profile(
        config.model_key,
        hyperparameter_overrides=config.hyperparameter_overrides,
        use_balanced_sample_weight=config.use_balanced_sample_weight,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_prefix = "binary_head" if len(config.target_columns) == 1 else "multilabel"
    run_id = f"{run_prefix}_{config.model_key}_{stamp}"
    output_dir = (config.output_root / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "running",
        "model_key": profile.model_key,
        "target_columns": list(config.target_columns),
        "head_architecture": "single_binary_estimator" if len(config.target_columns) == 1 else "independent_binary_estimators",
        "positive_probability_threshold": config.probability_threshold,
        "threshold_policy": "fixed_configured_threshold; this is separate from weak-label rule parameters",
        "joint_state_policy": "REF only when every selected head predicts 0; otherwise the positive target set; joint state is abstain/unknown when any selected head has no observable X",
        "unknown_truth_policy": "missing labels remain unknown and are excluded only from the affected metric; never coerced to 0",
        "training_cohort_policy": lineage.get("training_label_policy", "complete_case"),
        "per_head_training_masks": True,
        "learner_observability_policy": (
            "require_at_least_one_selected_feature_observed; no-X rows abstain and are excluded from primary fitting/evaluation"
            if config.require_observable_features
            else "diagnostic_only; all rows predicted after train-fitted imputation"
        ),
        "require_observable_features": config.require_observable_features,
        "evaluation_partitions": list(config.evaluation_partitions),
        "random_seed": config.random_seed,
        "thread_count": config.thread_count,
        "hyperparameter_overrides": config.hyperparameter_overrides or {},
        "balanced_sample_weight_override": config.use_balanced_sample_weight,
        "model_profile": {
            "family": profile.family,
            "library": profile.library,
            "hyperparameters": profile.hyperparameters,
            "enable_scaling": profile.enable_scaling,
            "enable_variance_threshold": profile.enable_variance_threshold,
            "use_balanced_sample_weight": profile.use_balanced_sample_weight,
        },
        "libraries": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__},
        "lineage": lineage,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "heads": {},
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    all_predictions: list[pd.DataFrame] = []
    all_metrics: dict[str, object] = {}
    try:
        labels_by_id = labels.set_index("sample_id")
        features_by_id = features.set_index("sample_id")
        for fold_id, fold_rows in splits.groupby("fold_id", sort=True):
            train_rows = fold_rows.loc[fold_rows["partition"].astype("string").eq("train")]
            if train_rows.empty:
                raise ValueError(f"Fold {fold_id!r} contains no training samples.")
            evaluation_rows = {
                partition: fold_rows.loc[fold_rows["partition"].astype("string").eq(partition)]
                for partition in config.evaluation_partitions
            }
            evaluation_rows = {key: value for key, value in evaluation_rows.items() if not value.empty}
            if not evaluation_rows:
                raise ValueError(f"Fold {fold_id!r} has no requested evaluation partitions.")
            evaluation_x = {
                partition: features_by_id.loc[rows["sample_id"].astype("string").tolist(), feature_columns].to_numpy(dtype=float)
                for partition, rows in evaluation_rows.items()
            }
            fold_dir = output_dir / str(fold_id)
            fold_dir.mkdir(parents=True, exist_ok=True)
            fold_started = time.perf_counter()
            for target in config.target_columns:
                train_row_ids = train_rows["sample_id"].astype("string").tolist()
                target_known = labels_by_id.loc[train_row_ids, target].notna().to_numpy()
                train_observable = feature_observable.loc[train_row_ids].fillna(False).to_numpy(dtype=bool)
                fit_mask = target_known & (train_observable if config.require_observable_features else True)
                train_ids = train_rows.loc[fit_mask, "sample_id"].astype("string").tolist()
                known_no_x_excluded = int((target_known & ~train_observable).sum()) if config.require_observable_features else 0
                if not train_ids:
                    raise ValueError(f"Fold {fold_id!r}, target {target!r} has no known training labels.")
                train_x = features_by_id.loc[train_ids, feature_columns].to_numpy(dtype=float)
                preprocessing = fit_preprocessing_bundle(
                    train_features=train_x,
                    evaluation_features=evaluation_x,
                    feature_names=feature_columns,
                    enable_scaling=profile.enable_scaling,
                    enable_variance_threshold=profile.enable_variance_threshold,
                )
                if not preprocessing["selected_feature_names"]:
                    raise ValueError(f"Fold {fold_id!r}, target {target!r} has no non-constant selected features.")
                train_hash = hash_sample_ids(train_ids)
                target_dir = fold_dir / _safe_name(target)
                target_dir.mkdir(parents=True, exist_ok=False)
                preprocessing_path = target_dir / "preprocessing.joblib"
                joblib.dump(
                    {key: preprocessing[key] for key in ("imputer", "scaler", "selector", "selected_feature_names")},
                    preprocessing_path,
                )
                y_train = labels_by_id.loc[train_ids, target].astype(int).to_numpy()
                support = {str(value): int(count) for value, count in pd.Series(y_train).value_counts().sort_index().items()}
                if set(np.unique(y_train)) != {0, 1}:
                    raise ValueError(f"Fold {fold_id!r}, target {target!r} needs both binary classes; found {support}.")
                estimator, library_version = build_estimator(
                    profile=profile,
                    random_seed=config.random_seed,
                    thread_count=config.thread_count,
                    class_count=2,
                )
                fit_started = time.perf_counter()
                with capture_python_output(target_dir / "training_console.log"):
                    if profile.use_balanced_sample_weight:
                        estimator.fit(preprocessing["train_features"], y_train, sample_weight=compute_sample_weight("balanced", y_train))
                    else:
                        estimator.fit(preprocessing["train_features"], y_train)
                fit_seconds = time.perf_counter() - fit_started
                classes = list(estimator.classes_)
                if classes != [0, 1]:
                    raise ValueError(f"Binary estimator class ordering is unexpected for {target!r}: {classes}.")
                bundle = {
                    "model": estimator,
                    "imputer": preprocessing["imputer"],
                    "scaler": preprocessing["scaler"],
                    "selector": preprocessing["selector"],
                    "selected_feature_names": preprocessing["selected_feature_names"],
                    "target_column": target,
                    "class_names": [0, 1],
                    "probability_threshold": config.probability_threshold,
                    "train_sample_hash": train_hash,
                    "feature_columns_hash": lineage["feature_columns_hash"],
                    "preprocessing_path": str(preprocessing_path.resolve()),
                    "preprocessing_sha256": sha256_file(preprocessing_path),
                }
                model_path = target_dir / "model_bundle.joblib"
                joblib.dump(bundle, model_path)
                manifest["heads"][f"{fold_id}/{target}"] = {
                    "target_column": target,
                    "status": "fitted_model_persisted",
                    "model_bundle_path": str(model_path.resolve()),
                    "model_bundle_sha256": sha256_file(model_path),
                    "train_sample_hash": train_hash,
                    "train_sample_count": len(train_ids),
                    "train_unknown_excluded_count": int((~target_known).sum()),
                    "train_known_no_x_excluded_count": known_no_x_excluded,
                    "train_total_excluded_count": int(len(train_rows) - len(train_ids)),
                    "fit_seconds": fit_seconds,
                }
                _write_json(output_dir / "run_manifest.json", manifest)
                _write_catalog(output_dir)
                head_predictions: list[pd.DataFrame] = []
                head_metrics: dict[str, object] = {}
                for partition, rows in evaluation_rows.items():
                    sample_ids = rows["sample_id"].astype("string").tolist()
                    truth_series = labels_by_id.loc[sample_ids, target]
                    observable = feature_observable.loc[sample_ids].fillna(False).to_numpy(dtype=bool)
                    prediction_mask = observable if config.require_observable_features else np.ones(len(sample_ids), dtype=bool)
                    score = np.full(len(sample_ids), np.nan, dtype=float)
                    predicted = pd.array([pd.NA] * len(sample_ids), dtype="Int64")
                    if prediction_mask.any():
                        probabilities = _normalize_prediction_probabilities(
                            estimator.predict_proba(preprocessing["evaluation_features"][partition][prediction_mask])
                        )
                        if probabilities is None:
                            raise ValueError(f"Model {config.model_key!r} did not return probabilities for {target!r}.")
                        observed_score = np.asarray(probabilities, dtype=float)[:, 1]
                        score[prediction_mask] = observed_score
                        predicted[prediction_mask] = (observed_score >= config.probability_threshold).astype(int)
                    target_known_mask = truth_series.notna().to_numpy()
                    known = target_known_mask & prediction_mask
                    row_frame = pd.DataFrame({
                        "fold_id": str(fold_id),
                        "partition": partition,
                        "sample_id": sample_ids,
                        "target": target,
                        "y_true": truth_series.astype("Int64").array,
                        "y_pred": predicted,
                        "positive_probability": score,
                        "probability_threshold": config.probability_threshold,
                        "target_known": target_known_mask,
                        "x_observable": observable,
                        "prediction_status": np.where(prediction_mask, "PREDICTED", "MODEL_ABSTAIN_NO_X"),
                    })
                    head_predictions.append(row_frame)
                    if known.any():
                        head_metrics[partition] = binary_metrics(
                            truth_series[known].astype(int).to_numpy(), predicted[known], score[known]
                        )
                    else:
                        head_metrics[partition] = {"sample_count": 0, "status": "no_known_truth_rows"}
                    head_metrics[partition].update({
                        "partition_row_count": int(len(rows)),
                        "target_known_count": int(target_known_mask.sum()),
                        "target_unknown_count": int((~target_known_mask).sum()),
                        "x_observable_count": int(observable.sum()),
                        "no_x_abstention_count": int((~prediction_mask).sum()),
                        "known_truth_no_x_count": int((target_known_mask & ~prediction_mask).sum()),
                        "metric_evaluation_count": int(known.sum()),
                    })
                    _write_json(target_dir / f"metrics_{partition}.json", head_metrics[partition])
                    if known.any():
                        write_classification_plots(
                            y_true=truth_series[known].astype(int).to_numpy(),
                            y_pred=predicted[known],
                            probabilities=np.column_stack([1.0 - score[known], score[known]]),
                            class_names=["NEGATIVE", "POSITIVE"],
                            output_dir=target_dir / "plots",
                            partition=partition,
                        )
                prediction_frame = pd.concat(head_predictions, ignore_index=True).convert_dtypes()
                prediction_frame.to_parquet(target_dir / "predictions.parquet", index=False)
                metadata = {
                    "target_column": target,
                    "model_key": config.model_key,
                    "class_support_train": support,
                    "train_sample_count": len(train_ids),
                    "train_unknown_excluded_count": int((~target_known).sum()),
                    "train_known_no_x_excluded_count": known_no_x_excluded,
                    "train_total_excluded_count": int(len(train_rows) - len(train_ids)),
                    "train_sample_hash": train_hash,
                    "selected_features": preprocessing["selected_feature_names"],
                    "preprocessing_path": str(preprocessing_path.resolve()),
                    "preprocessing_sha256": sha256_file(preprocessing_path),
                    "feature_columns_hash": lineage["feature_columns_hash"],
                    "fit_seconds": fit_seconds,
                    "model_library_version": library_version,
                    "evaluation_metrics": head_metrics,
                }
                _write_json(target_dir / "head_manifest.json", metadata)
                manifest["heads"][f"{fold_id}/{target}"] = {
                    **metadata,
                    "model_bundle_path": str(model_path.resolve()),
                    "model_bundle_sha256": sha256_file(model_path),
                    "status": "complete",
                }
                _write_json(output_dir / "run_manifest.json", manifest)
                _write_catalog(output_dir)
                all_predictions.append(prediction_frame)
                all_metrics[f"{fold_id}/{target}"] = head_metrics
            manifest.setdefault("fold_runtime_seconds", {})[str(fold_id)] = time.perf_counter() - fold_started
            _write_json(output_dir / "run_manifest.json", manifest)
        predictions = pd.concat(all_predictions, ignore_index=True).convert_dtypes()
        joint = _derive_joint_predictions(predictions, config.target_columns)
        source_labels_path = lineage.get("source_artifacts", {}).get("labels_path")
        if source_labels_path:
            bootstrap_metrics = build_temporal_bootstrap_metrics(
                predictions, Path(str(source_labels_path)), repetitions=1000, seed=config.random_seed
            )
            if not bootstrap_metrics.empty:
                bootstrap_metrics.to_csv(output_dir / "temporal_bootstrap_metrics.csv", index=False)
                manifest["temporal_bootstrap_metrics_path"] = str((output_dir / "temporal_bootstrap_metrics.csv").resolve())
            entity_metrics = build_entity_metrics(predictions, Path(str(source_labels_path)))
            if not entity_metrics.empty:
                entity_metrics.to_csv(output_dir / "per_entity_metrics.csv", index=False)
                manifest["per_entity_metrics_path"] = str((output_dir / "per_entity_metrics.csv").resolve())
        predictions_path = output_dir / "predictions.parquet"
        joint.to_parquet(predictions_path, index=False)
        predictions_path_csv = output_dir / "predictions.csv"
        joint.to_csv(predictions_path_csv, index=False)
        joint_metrics = _joint_metrics(joint, config.target_columns)
        metrics_payload = {"head_metrics": all_metrics, "joint_metrics": joint_metrics}
        _write_json(output_dir / "metrics.json", metrics_payload)
        _write_joint_plots(joint, config.target_columns, output_dir / "plots")
        manifest.update({
            "status": "complete",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "metrics_path": str((output_dir / "metrics.json").resolve()),
            "predictions_path": str(predictions_path.resolve()),
            "head_count": len(manifest["heads"]),
        })
        _write_json(output_dir / "run_manifest.json", manifest)
        _write_catalog(output_dir)
        report = _render_report(manifest, metrics_payload)
        (output_dir / "report.md").write_text(report, encoding="utf-8")
        _write_catalog(output_dir)
        return MultiLabelRunResult(run_id, output_dir, "complete", int(splits["fold_id"].nunique()), len(config.target_columns))
    except Exception as exc:
        manifest.update({
            "status": "failed_partial_outputs_preserved",
            "failed_at_utc": datetime.now(timezone.utc).isoformat(),
            "failure": {"type": type(exc).__name__, "message": str(exc)},
            "completed_head_count": sum(row.get("status") == "complete" for row in manifest["heads"].values()),
        })
        _write_json(output_dir / "run_manifest.json", manifest)
        _write_catalog(output_dir)
        raise


def _derive_joint_predictions(predictions: pd.DataFrame, targets: tuple[str, ...]) -> pd.DataFrame:
    keys = ["fold_id", "partition", "sample_id"]
    truth = predictions.pivot(index=keys, columns="target", values="y_true")
    predicted = predictions.pivot(index=keys, columns="target", values="y_pred")
    probabilities = predictions.pivot(index=keys, columns="target", values="positive_probability")
    if "x_observable" in predictions:
        observable = predictions.pivot(index=keys, columns="target", values="x_observable")
    else:
        observable = predicted.notna()
    if "prediction_status" in predictions:
        prediction_status = predictions.pivot(index=keys, columns="target", values="prediction_status")
    else:
        prediction_status = predicted.notna().replace({True: "PREDICTED", False: "MODEL_ABSTAIN_NO_X"})
    if "target_known" in predictions:
        target_known = predictions.pivot(index=keys, columns="target", values="target_known")
    else:
        target_known = truth.notna()
    frame = truth.rename(columns={target: f"y_true::{target}" for target in targets})
    for target in targets:
        frame[f"y_pred::{target}"] = predicted[target]
        frame[f"probability::{target}"] = probabilities[target]
        frame[f"prediction_status::{target}"] = prediction_status[target]
        frame[f"x_observable::{target}"] = observable[target]
        frame[f"target_known::{target}"] = target_known[target]
    frame["joint_x_observable"] = observable.loc[:, list(targets)].fillna(False).astype(bool).all(axis=1)
    frame = frame.reset_index()
    frame["joint_true_state"] = frame.apply(lambda row: _state_from_row(row, targets, "y_true"), axis=1).astype("string")
    frame["joint_pred_state"] = frame.apply(lambda row: _state_from_row(row, targets, "y_pred"), axis=1).astype("string")
    return frame.convert_dtypes()


def _state_from_row(row: pd.Series, targets: tuple[str, ...], prefix: str) -> str | pd._libs.missing.NAType:
    values = [row.get(f"{prefix}::{target}") for target in targets]
    if any(pd.isna(value) for value in values):
        return pd.NA
    positives = [_short_target_name(target) for target, value in zip(targets, values, strict=True) if int(value) == 1]
    return "+".join(positives) if positives else "REF"


def _joint_metrics(frame: pd.DataFrame, targets: tuple[str, ...]) -> dict[str, object]:
    result: dict[str, object] = {}
    for (fold, partition), group in frame.groupby(["fold_id", "partition"], sort=True):
        target_known = group["joint_true_state"].notna()
        predicted = group["joint_pred_state"].notna()
        known = target_known & predicted
        evaluated = group.loc[known]
        truth_matrix = evaluated[[f"y_true::{target}" for target in targets]].astype(int).to_numpy() if len(evaluated) else np.empty((0, len(targets)), dtype=int)
        prediction_matrix = evaluated[[f"y_pred::{target}" for target in targets]].astype(int).to_numpy() if len(evaluated) else np.empty((0, len(targets)), dtype=int)
        result[f"{fold}/{partition}"] = {
            "known_joint_truth_count": int(target_known.sum()),
            "unknown_joint_truth_count": int((~target_known).sum()),
            "joint_x_observable_count": int(group["joint_x_observable"].sum()),
            "joint_no_x_abstention_count": int((~group["joint_x_observable"]).sum()),
            "known_truth_no_x_count": int((target_known & ~group["joint_x_observable"]).sum()),
            "joint_metric_evaluation_count": int(known.sum()),
            "subset_accuracy": float(evaluated["joint_true_state"].eq(evaluated["joint_pred_state"]).mean()) if len(evaluated) else math.nan,
            "hamming_loss": float(hamming_loss(truth_matrix, prediction_matrix)) if len(evaluated) else math.nan,
            "micro_precision": float(precision_score(truth_matrix, prediction_matrix, average="micro", zero_division=0)) if len(evaluated) else math.nan,
            "micro_recall": float(recall_score(truth_matrix, prediction_matrix, average="micro", zero_division=0)) if len(evaluated) else math.nan,
            "micro_f1": float(f1_score(truth_matrix, prediction_matrix, average="micro", zero_division=0)) if len(evaluated) else math.nan,
            "macro_f1": float(f1_score(truth_matrix, prediction_matrix, average="macro", zero_division=0)) if len(evaluated) else math.nan,
            "joint_confusion_matrix": _joint_confusion(evaluated, targets),
            "joint_class_order": _joint_class_order(targets),
        }
    return result


def _joint_confusion(frame: pd.DataFrame, targets: tuple[str, ...]) -> list[list[int]]:
    classes = _joint_class_order(targets)
    lookup = {name: index for index, name in enumerate(classes)}
    counts = [[0 for _ in classes] for _ in classes]
    for truth, predicted in zip(frame["joint_true_state"], frame["joint_pred_state"], strict=True):
        counts[lookup[str(truth)]][lookup[str(predicted)]] += 1
    return counts


def _write_joint_plots(frame: pd.DataFrame, targets: tuple[str, ...], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    class_names = _joint_class_order(targets)
    lookup = {name: index for index, name in enumerate(class_names)}
    for (fold, partition), group in frame.groupby(["fold_id", "partition"], sort=True):
        evaluable = group.loc[group["joint_true_state"].notna() & group["joint_pred_state"].notna()]
        if evaluable.empty:
            continue
        write_classification_plots(
            y_true=[lookup[str(value)] for value in evaluable["joint_true_state"]],
            y_pred=[lookup[str(value)] for value in evaluable["joint_pred_state"]],
            probabilities=None,
            class_names=class_names,
            output_dir=output_dir / _safe_name(str(fold)),
            partition=f"joint_{partition}",
        )


def _joint_class_order(targets: tuple[str, ...]) -> list[str]:
    names = [_short_target_name(target) for target in targets]
    if len(names) == 1:
        return ["REF", names[0]]
    return ["REF", *names, "+".join(names)]


def _short_target_name(target: str) -> str:
    return target.rsplit(".", 1)[-1].upper()


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True), encoding="utf-8")


def _write_catalog(output_dir: Path) -> None:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "artifact_catalog.json":
            rows.append({"path": str(path.relative_to(output_dir)), "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    (output_dir / "artifact_catalog.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_report(manifest: dict[str, object], metrics: dict[str, object]) -> str:
    title = "Binary target run" if len(manifest["target_columns"]) == 1 else "Multi-label run"
    lines = [
        f"# {title}: {manifest['run_id']}",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Model: `{manifest['model_key']}`",
        f"- Target(s): `{', '.join(manifest['target_columns'])}`",
        f"- Probability threshold: `{manifest['positive_probability_threshold']}`",
        "- REF means all head predictions are negative; unknown truth remains unknown.",
        f"- Training cohort policy: `{manifest.get('training_cohort_policy', 'complete_case')}`; each head has its own known-label mask and preprocessing fit.",
        f"- Learner observability policy: `{manifest.get('learner_observability_policy', 'not recorded')}`.",
        "",
        "## Joint metrics",
        "",
        "| Fold / partition | Known joint rows | Unknown joint rows | Subset accuracy |",
        "|---|---:|---:|---:|",
    ]
    for scope, row in metrics["joint_metrics"].items():
        lines.append(f"| `{scope}` | {row['known_joint_truth_count']} | {row['unknown_joint_truth_count']} | {row['subset_accuracy']} |")
    lines.extend([
        "",
        "## Per-head metrics",
        "",
        "| Fold / target / partition | Fit rows | Unknown train excluded | Known no-X train excluded | Partition rows | Metric rows | No-X abstentions | Positive prevalence | Log loss | AP | ROC-AUC | Brier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for fold_target, partitions in metrics["head_metrics"].items():
        fold_id, target = fold_target.split("/", 1)
        head = manifest.get("heads", {}).get(fold_target, {})
        for partition, metric in partitions.items():
            lines.append(
                f"| `{fold_id}/{target}/{partition}` | {head.get('train_sample_count', '')} | "
                f"{head.get('train_unknown_excluded_count', '')} | {head.get('train_known_no_x_excluded_count', 0)} | "
                f"{metric.get('partition_row_count', '')} | {metric.get('metric_evaluation_count', metric.get('sample_count', ''))} | "
                f"{metric.get('no_x_abstention_count', 0)} | "
                f"{metric.get('positive_prevalence', '')} | {metric.get('log_loss', '')} | "
                f"{metric.get('average_precision', '')} | {metric.get('roc_auc', '')} | {metric.get('brier_score', '')} |"
            )
    if manifest.get("per_entity_metrics_path"):
        lines.extend([
            "",
        "Per-entity metrics distinguish discrimination estimability from probabilistic-loss estimability; Brier/log-loss remain defined when known truth contains one class. No-X rows are recorded as abstentions when the observability gate is enabled.",
        ])
    if manifest.get("temporal_bootstrap_metrics_path"):
        lines.extend([
            "",
            "Calendar-day cluster bootstrap intervals for log loss, Brier score, AP, and ROC-AUC are in `temporal_bootstrap_metrics.csv`. AP is reported with positive prevalence.",
        ])
    lines.append("")
    return "\n".join(lines)
