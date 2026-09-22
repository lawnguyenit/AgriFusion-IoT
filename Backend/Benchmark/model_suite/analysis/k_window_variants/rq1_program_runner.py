from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification
from Backend.Benchmark.model_suite.pipeline.training_job import train_tabular_classifier
from Backend.Benchmark.model_suite.registries import resolve_model_profile

from .history import FeatureBundle
from .representations import RepresentationBundle
from .configured_runner import _feature_matrix as _base_feature_matrix


@dataclass(frozen=True)
class ProbeVariant:
    variant_id: str
    representation_id: str
    representation: RepresentationBundle
    label_column: str
    class_names: tuple[str, ...]


def run_probe_temporal_cv(
    *,
    variants: tuple[ProbeVariant, ...],
    fold_frames: dict[str, pd.DataFrame],
    output_dir: Path,
    random_seed: int,
    thread_count: int,
) -> dict[str, pd.DataFrame]:
    metric_rows: list[dict[str, object]] = []
    per_class_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    profile = resolve_model_profile("xgboost")
    for fold_id, target_frame in fold_frames.items():
        for variant in variants:
            joined = target_frame.merge(variant.representation.feature_bundle.frame, on="sample_id", how="inner", validate="one_to_one")
            trainable = joined["final_trainability"].fillna(False).astype(bool) & joined[variant.label_column].notna()
            joined = joined.loc[trainable].copy()
            partitions = {name: joined.loc[joined["partition"].astype("string").eq(name)].copy() for name in ("train", "validation", "test")}
            train_labels = partitions["train"][variant.label_column].astype("string")
            if sorted(train_labels.unique().tolist()) != sorted(variant.class_names):
                raise ValueError(f"Persistence probe training labels are incomplete for {variant.variant_id}: {sorted(train_labels.unique().tolist())}")
            feature_lookup = variant.representation.feature_bundle.frame.set_index("sample_id", drop=False)
            feature_names = variant.representation.feature_bundle.feature_names
            train_ids = partitions["train"]["sample_id"].astype("string").tolist()
            result = train_tabular_classifier(
                profile=profile,
                train_features=_base_feature_matrix(feature_lookup, train_ids, feature_names),
                evaluation_features={name: _base_feature_matrix(feature_lookup, frame["sample_id"].astype("string").tolist(), feature_names) for name, frame in partitions.items() if name != "train"},
                train_labels=train_labels,
                allowed_feature_columns=feature_names,
                train_sample_ids=train_ids,
                output_dir=output_dir / fold_id / "jobs" / variant.variant_id,
                random_seed=random_seed,
                thread_count=thread_count,
                task_metadata={
                    "variant_id": variant.variant_id,
                    "representation_id": variant.representation_id,
                    "probe_target": variant.label_column,
                    "probe_class_names": list(variant.class_names),
                    "fold_id": fold_id,
                },
            )
            class_names = result.class_names
            class_lookup = {name: index for index, name in enumerate(class_names)}
            for partition in ("validation", "test"):
                frame = partitions[partition]
                y_true = frame[variant.label_column].map(class_lookup).to_numpy(dtype=np.int64)
                y_pred = np.asarray(result.evaluation_predictions[partition], dtype=np.int64)
                probabilities = result.evaluation_probabilities.get(partition)
                metrics = summarize_protocol_classification(y_true, y_pred, class_names)
                metrics.update(_probability_metrics(y_true, probabilities, class_names))
                for class_name, class_metrics in metrics["class_metrics"].items():
                    per_class_rows.append({"fold_id": fold_id, "variant_id": variant.variant_id, "representation_id": variant.representation_id, "partition": partition, "class_name": class_name, **class_metrics})
                matrix = metrics["confusion_matrix"]
                for true_index, true_name in enumerate(class_names):
                    for pred_index, pred_name in enumerate(class_names):
                        confusion_rows.append({"fold_id": fold_id, "variant_id": variant.variant_id, "representation_id": variant.representation_id, "partition": partition, "true_label": true_name, "predicted_label": pred_name, "count": int(matrix[true_index][pred_index])})
                for index, row in enumerate(frame.to_dict(orient="records")):
                    probability_map = {name: float(value) for name, value in zip(class_names, probabilities[index], strict=True)} if probabilities is not None else {}
                    prediction_rows.append({"fold_id": fold_id, "variant_id": variant.variant_id, "representation_id": variant.representation_id, "partition": partition, "sample_id": str(row["sample_id"]), "label_true": str(row[variant.label_column]), "label_pred": class_names[int(y_pred[index])], "probability_json": probability_map})
                metric_rows.append({"fold_id": fold_id, "variant_id": variant.variant_id, "representation_id": variant.representation_id, "partition": partition, "feature_count": len(feature_names), "train_count": len(partitions["train"]), "evaluation_count": len(frame), "accuracy": metrics["accuracy"], "balanced_accuracy": metrics["supported_class_balanced_accuracy"], "macro_f1": metrics["supported_class_macro_f1"], "weighted_f1": metrics["weighted_f1"], "macro_pr_auc_ovr": metrics["macro_pr_auc_ovr"], "macro_roc_auc_ovr": metrics["macro_roc_auc_ovr"], "class_names": list(class_names)})
    return {"metrics": pd.DataFrame(metric_rows).convert_dtypes(), "per_class": pd.DataFrame(per_class_rows).convert_dtypes(), "confusion": pd.DataFrame(confusion_rows).convert_dtypes(), "predictions": pd.DataFrame(prediction_rows).convert_dtypes()}


def summarize_probe_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    return metrics.groupby(["variant_id", "representation_id", "partition"], sort=True).agg(
        fold_count=("fold_id", "nunique"),
        evaluation_count_mean=("evaluation_count", "mean"),
        balanced_accuracy_mean=("balanced_accuracy", "mean"),
        balanced_accuracy_std=("balanced_accuracy", "std"),
        macro_f1_mean=("macro_f1", "mean"),
        macro_f1_std=("macro_f1", "std"),
        macro_pr_auc_mean=("macro_pr_auc_ovr", "mean"),
        macro_pr_auc_std=("macro_pr_auc_ovr", "std"),
    ).reset_index().convert_dtypes()


def _probability_metrics(y_true: np.ndarray, probabilities: list[list[float]] | None, class_names: list[str]) -> dict[str, float]:
    if probabilities is None:
        return {"macro_pr_auc_ovr": float("nan"), "macro_roc_auc_ovr": float("nan")}
    scores = np.asarray(probabilities, dtype=float)
    one_hot = np.eye(len(class_names), dtype=float)[y_true]
    try:
        ap = float(average_precision_score(one_hot, scores, average="macro"))
    except ValueError:
        ap = float("nan")
    try:
        roc = float(roc_auc_score(y_true, scores, multi_class="ovr", average="macro"))
    except ValueError:
        roc = float("nan")
    return {"macro_pr_auc_ovr": ap, "macro_roc_auc_ovr": roc}
