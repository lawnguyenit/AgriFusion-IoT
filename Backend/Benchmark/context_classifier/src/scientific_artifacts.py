from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    log_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

from Backend.Benchmark.pretrain_supervised.pretrain.src.utils.artifacts import write_json


TOP1_CALIBRATION_LABEL = "__top1__"


def write_context_scientific_artifacts(
    *,
    output_dir: Path,
    experiment_name: str,
    model_name: str,
    class_names: list[str],
    history: list[dict[str, float]],
    best_epoch: int,
    training_config: dict[str, object],
    training_metadata: dict[str, object],
    split_payloads: dict[str, dict[str, object]],
) -> dict[str, object]:
    artifact_root = output_dir / "scientific_artifacts" / model_name
    artifact_root.mkdir(parents=True, exist_ok=True)

    history_frame = pd.DataFrame(history)
    if not history_frame.empty and "epoch" in history_frame.columns:
        history_frame["is_best_epoch"] = history_frame["epoch"].astype(int) == int(best_epoch)
    history_csv_path = artifact_root / "training_history.csv"
    history_frame.to_csv(history_csv_path, index=False)

    scalar_rows: list[dict[str, object]] = []
    classwise_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []
    pr_rows: list[dict[str, object]] = []
    roc_rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    prediction_paths: dict[str, str] = {}
    split_summaries: dict[str, dict[str, object]] = {}

    for split_name, payload in split_payloads.items():
        metadata_frame = payload["metadata_frame"]
        y_true = np.asarray(payload["labels"], dtype=np.int64)
        y_pred = np.asarray(payload["predictions"], dtype=np.int64)
        probabilities = np.asarray(payload["probabilities"], dtype=np.float64)
        metrics = payload["metrics"]

        prediction_frame = _build_prediction_frame(
            metadata_frame=metadata_frame,
            y_true=y_true,
            y_pred=y_pred,
            probabilities=probabilities,
            class_names=class_names,
        )
        prediction_path = artifact_root / f"{split_name}_prediction_records.csv"
        prediction_frame.to_csv(prediction_path, index=False)
        prediction_paths[split_name] = str(prediction_path)

        split_summary = _build_split_summary(
            split_name=split_name,
            y_true=y_true,
            y_pred=y_pred,
            probabilities=probabilities,
            class_names=class_names,
            metrics=metrics,
        )
        split_summaries[split_name] = split_summary["summary"]
        scalar_rows.append(split_summary["summary"])
        classwise_rows.extend(split_summary["classwise_rows"])
        confusion_rows.extend(split_summary["confusion_rows"])
        pr_rows.extend(split_summary["pr_rows"])
        roc_rows.extend(split_summary["roc_rows"])
        calibration_rows.extend(split_summary["calibration_rows"])

    scalar_metrics_path = artifact_root / "scalar_metrics.csv"
    pd.DataFrame(scalar_rows).to_csv(scalar_metrics_path, index=False)

    classwise_metrics_path = artifact_root / "classwise_metrics.csv"
    pd.DataFrame(classwise_rows).to_csv(classwise_metrics_path, index=False)

    confusion_matrix_path = artifact_root / "confusion_matrix.csv"
    pd.DataFrame(confusion_rows).to_csv(confusion_matrix_path, index=False)

    pr_curve_path = artifact_root / "pr_curve_points.csv"
    pd.DataFrame(pr_rows).to_csv(pr_curve_path, index=False)

    roc_curve_path = artifact_root / "roc_curve_points.csv"
    pd.DataFrame(roc_rows).to_csv(roc_curve_path, index=False)

    calibration_curve_path = artifact_root / "calibration_curve_points.csv"
    pd.DataFrame(calibration_rows).to_csv(calibration_curve_path, index=False)

    training_metadata_path = artifact_root / "training_metadata.json"
    training_metadata_payload = {
        "experiment_name": experiment_name,
        "model_name": model_name,
        "class_names": class_names,
        "best_epoch": int(best_epoch),
        "training_config": training_config,
        "training_metadata": training_metadata,
        "split_summaries": split_summaries,
    }
    write_json(training_metadata_path, _json_ready(training_metadata_payload))

    manifest = {
        "artifact_root": str(artifact_root),
        "history_csv_path": str(history_csv_path),
        "scalar_metrics_path": str(scalar_metrics_path),
        "classwise_metrics_path": str(classwise_metrics_path),
        "confusion_matrix_path": str(confusion_matrix_path),
        "pr_curve_path": str(pr_curve_path),
        "roc_curve_path": str(roc_curve_path),
        "calibration_curve_path": str(calibration_curve_path),
        "training_metadata_path": str(training_metadata_path),
        "prediction_paths": prediction_paths,
        "split_summaries": split_summaries,
    }
    manifest_path = artifact_root / "scientific_manifest.json"
    write_json(manifest_path, _json_ready(manifest))
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def probabilities_from_logits(logits: Any) -> np.ndarray:
    logits_array = np.asarray(logits, dtype=np.float64)
    shifted = logits_array - np.max(logits_array, axis=1, keepdims=True)
    exp_values = np.exp(shifted)
    normalizer = np.sum(exp_values, axis=1, keepdims=True)
    return exp_values / np.clip(normalizer, 1e-12, None)


def _build_prediction_frame(
    *,
    metadata_frame: Any,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
    class_names: list[str],
) -> pd.DataFrame:
    frame = pd.DataFrame(metadata_frame).reset_index(drop=True).copy()
    if len(frame) != len(y_true):
        raise ValueError("Prediction metadata frame length does not match label length.")

    probability_frame = pd.DataFrame(
        probabilities,
        columns=[f"prob_{_slugify_column(class_name)}" for class_name in class_names],
    )
    top1_confidence = probabilities.max(axis=1)
    if probabilities.shape[1] > 1:
        sorted_probabilities = np.sort(probabilities, axis=1)
        confidence_margin = sorted_probabilities[:, -1] - sorted_probabilities[:, -2]
    else:
        confidence_margin = np.ones(len(probabilities), dtype=np.float64)
    entropy = -np.sum(probabilities * np.log(np.clip(probabilities, 1e-12, None)), axis=1)

    frame["row_index_within_split"] = np.arange(len(frame), dtype=np.int64)
    frame["y_true_id"] = y_true.astype(np.int64)
    frame["y_true_name"] = [class_names[int(index)] for index in y_true]
    frame["y_pred_id"] = y_pred.astype(np.int64)
    frame["y_pred_name"] = [class_names[int(index)] for index in y_pred]
    frame["is_correct"] = (y_true == y_pred).astype(np.int64)
    frame["top1_confidence"] = top1_confidence.astype(np.float64)
    frame["confidence_margin"] = confidence_margin.astype(np.float64)
    frame["prediction_entropy"] = entropy.astype(np.float64)
    return pd.concat([frame, probability_frame], axis=1)


def _build_split_summary(
    *,
    split_name: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
    class_names: list[str],
    metrics: dict[str, object],
) -> dict[str, object]:
    report = metrics.get("classification_report", {})
    matrix = np.asarray(metrics.get("confusion_matrix", []), dtype=int)
    if matrix.size == 0:
        matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))

    summary_row: dict[str, object] = {
        "split": split_name,
        "sample_count": int(len(y_true)),
        "class_count": int(len(class_names)),
        "accuracy": _safe_float(metrics.get("accuracy")),
        "balanced_accuracy": _safe_float(metrics.get("balanced_accuracy")),
        "macro_f1": _safe_float(metrics.get("macro_f1")),
        "weighted_f1": _safe_float(metrics.get("weighted_f1")),
        "log_loss": _safe_log_loss(y_true, probabilities, class_names),
        "multiclass_brier": _multiclass_brier_score(y_true, probabilities, len(class_names)),
    }

    classwise_rows: list[dict[str, object]] = []
    for class_index, class_name in enumerate(class_names):
        class_report = report.get(class_name, {}) if isinstance(report, dict) else {}
        classwise_rows.append(
            {
                "split": split_name,
                "class_id": int(class_index),
                "class_name": class_name,
                "precision": _safe_float(class_report.get("precision")),
                "recall": _safe_float(class_report.get("recall")),
                "f1_score": _safe_float(class_report.get("f1-score")),
                "support": _safe_float(class_report.get("support")),
            }
        )

    confusion_rows: list[dict[str, object]] = []
    for true_index, true_name in enumerate(class_names):
        for pred_index, pred_name in enumerate(class_names):
            confusion_rows.append(
                {
                    "split": split_name,
                    "true_class_id": int(true_index),
                    "true_class_name": true_name,
                    "pred_class_id": int(pred_index),
                    "pred_class_name": pred_name,
                    "count": int(matrix[true_index, pred_index]),
                }
            )

    pr_rows: list[dict[str, object]] = []
    roc_rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    roc_auc_values: list[float] = []
    average_precision_values: list[float] = []
    brier_values: list[float] = []

    for class_index, class_name in enumerate(class_names):
        binary_true = (y_true == class_index).astype(np.int64)
        class_scores = probabilities[:, class_index].astype(np.float64)
        support_positive = int(binary_true.sum())
        support_negative = int(len(binary_true) - support_positive)
        average_precision = math.nan
        roc_auc = math.nan
        brier_score = math.nan

        if support_positive > 0 and support_negative > 0:
            precision, recall, pr_thresholds = precision_recall_curve(binary_true, class_scores)
            average_precision = float(average_precision_score(binary_true, class_scores))
            for row_index in range(len(precision)):
                threshold = None if row_index == 0 else float(pr_thresholds[row_index - 1])
                pr_rows.append(
                    {
                        "split": split_name,
                        "class_id": int(class_index),
                        "class_name": class_name,
                        "point_index": int(row_index),
                        "threshold": threshold,
                        "precision": float(precision[row_index]),
                        "recall": float(recall[row_index]),
                        "average_precision": average_precision,
                        "support_positive": support_positive,
                        "support_negative": support_negative,
                    }
                )

            fpr, tpr, roc_thresholds = roc_curve(binary_true, class_scores)
            roc_auc = float(roc_auc_score(binary_true, class_scores))
            for row_index in range(len(fpr)):
                roc_rows.append(
                    {
                        "split": split_name,
                        "class_id": int(class_index),
                        "class_name": class_name,
                        "point_index": int(row_index),
                        "threshold": float(roc_thresholds[row_index]),
                        "fpr": float(fpr[row_index]),
                        "tpr": float(tpr[row_index]),
                        "roc_auc": roc_auc,
                        "support_positive": support_positive,
                        "support_negative": support_negative,
                    }
                )

            calibration_result = _binary_calibration_rows(
                split_name=split_name,
                class_id=class_index,
                class_name=class_name,
                binary_true=binary_true,
                scores=class_scores,
            )
            calibration_rows.extend(calibration_result["rows"])
            brier_score = calibration_result["brier_score"]

        if not math.isnan(roc_auc):
            roc_auc_values.append(roc_auc)
        if not math.isnan(average_precision):
            average_precision_values.append(average_precision)
        if not math.isnan(brier_score):
            brier_values.append(brier_score)

        summary_row[f"class_{_slugify_column(class_name)}_support"] = support_positive

    top1_calibration = _top1_calibration_rows(
        split_name=split_name,
        y_true=y_true,
        y_pred=y_pred,
        probabilities=probabilities,
    )
    calibration_rows.extend(top1_calibration["rows"])
    summary_row["top1_ece_15bins"] = top1_calibration["ece"]

    summary_row["ovr_macro_roc_auc"] = float(np.mean(roc_auc_values)) if roc_auc_values else None
    summary_row["ovr_macro_average_precision"] = (
        float(np.mean(average_precision_values)) if average_precision_values else None
    )
    summary_row["ovr_macro_brier"] = float(np.mean(brier_values)) if brier_values else None

    return {
        "summary": summary_row,
        "classwise_rows": classwise_rows,
        "confusion_rows": confusion_rows,
        "pr_rows": pr_rows,
        "roc_rows": roc_rows,
        "calibration_rows": calibration_rows,
    }


def _binary_calibration_rows(
    *,
    split_name: str,
    class_id: int,
    class_name: str,
    binary_true: np.ndarray,
    scores: np.ndarray,
    bin_count: int = 10,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    brier_score = float(np.mean((scores - binary_true.astype(np.float64)) ** 2))
    bin_edges = np.linspace(0.0, 1.0, bin_count + 1)
    for bin_index in range(bin_count):
        lower = bin_edges[bin_index]
        upper = bin_edges[bin_index + 1]
        if bin_index == bin_count - 1:
            mask = (scores >= lower) & (scores <= upper)
        else:
            mask = (scores >= lower) & (scores < upper)
        if not np.any(mask):
            continue
        bin_scores = scores[mask]
        bin_true = binary_true[mask].astype(np.float64)
        rows.append(
            {
                "split": split_name,
                "class_id": int(class_id),
                "class_name": class_name,
                "calibration_target": "one_vs_rest",
                "bin_index": int(bin_index),
                "bin_lower": float(lower),
                "bin_upper": float(upper),
                "support": int(mask.sum()),
                "mean_predicted_probability": float(np.mean(bin_scores)),
                "fraction_positive": float(np.mean(bin_true)),
                "brier_score": brier_score,
            }
        )
    return {"rows": rows, "brier_score": brier_score}


def _top1_calibration_rows(
    *,
    split_name: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
    bin_count: int = 15,
) -> dict[str, object]:
    confidences = probabilities.max(axis=1).astype(np.float64)
    correctness = (y_true == y_pred).astype(np.float64)
    bin_edges = np.linspace(0.0, 1.0, bin_count + 1)
    rows: list[dict[str, object]] = []
    ece = 0.0
    total = max(len(confidences), 1)
    for bin_index in range(bin_count):
        lower = bin_edges[bin_index]
        upper = bin_edges[bin_index + 1]
        if bin_index == bin_count - 1:
            mask = (confidences >= lower) & (confidences <= upper)
        else:
            mask = (confidences >= lower) & (confidences < upper)
        if not np.any(mask):
            continue
        bin_conf = confidences[mask]
        bin_correct = correctness[mask]
        mean_conf = float(np.mean(bin_conf))
        accuracy = float(np.mean(bin_correct))
        support = int(mask.sum())
        ece += abs(accuracy - mean_conf) * (support / total)
        rows.append(
            {
                "split": split_name,
                "class_id": -1,
                "class_name": TOP1_CALIBRATION_LABEL,
                "calibration_target": "top1_correctness",
                "bin_index": int(bin_index),
                "bin_lower": float(lower),
                "bin_upper": float(upper),
                "support": support,
                "mean_predicted_probability": mean_conf,
                "fraction_positive": accuracy,
                "brier_score": None,
            }
        )
    return {"rows": rows, "ece": float(ece)}


def _multiclass_brier_score(y_true: np.ndarray, probabilities: np.ndarray, class_count: int) -> float:
    one_hot = np.zeros((len(y_true), class_count), dtype=np.float64)
    one_hot[np.arange(len(y_true)), y_true.astype(np.int64)] = 1.0
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))


def _safe_log_loss(y_true: np.ndarray, probabilities: np.ndarray, class_names: list[str]) -> float | None:
    try:
        return float(log_loss(y_true, probabilities, labels=list(range(len(class_names)))))
    except ValueError:
        return None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _slugify_column(name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in name).strip("_").lower()


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value
