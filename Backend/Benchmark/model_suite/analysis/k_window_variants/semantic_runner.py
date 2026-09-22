from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification
from Backend.Benchmark.model_suite.pipeline.training_job import train_tabular_classifier
from Backend.Benchmark.model_suite.registries import resolve_model_profile

from .history import FeatureBundle
from .runner import LOW_LABEL, REF_LABEL, REPORT_LABELS, UNRES_LABEL
from .semantic_targets import Y_EVENT, Y_ONLINE


@dataclass(frozen=True)
class SemanticVariant:
    variant_id: str
    representation: str
    target_view_id: str
    label_column: str
    feature_bundle: FeatureBundle


def build_semantic_variants(*, snapshot_bundle: FeatureBundle, history_bundle: FeatureBundle) -> tuple[SemanticVariant, ...]:
    return (
        SemanticVariant("snapshot_9_online_k3", "snapshot_9", Y_ONLINE, "label_online", snapshot_bundle),
        SemanticVariant("history_enriched_3h_online_k3", "causal_history_enriched_3h", Y_ONLINE, "label_online", history_bundle),
        SemanticVariant("snapshot_9_event_k3", "snapshot_9", Y_EVENT, "label_event", snapshot_bundle),
        SemanticVariant("history_enriched_3h_event_k3", "causal_history_enriched_3h", Y_EVENT, "label_event", history_bundle),
    )


def run_semantic_variants(
    *,
    variants: tuple[SemanticVariant, ...],
    target_frame: pd.DataFrame,
    output_dir: Path,
    random_seed: int,
    thread_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    profile = resolve_model_profile("xgboost")
    metrics_rows: list[dict[str, object]] = []
    per_class_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []

    for variant in variants:
        joined = target_frame.merge(variant.feature_bundle.frame, on="sample_id", how="inner", validate="one_to_one")
        trainable = (
            joined["final_trainability"].fillna(False).astype(bool)
            & joined["label_status_online"].astype("string").eq("LABELED")
            & joined["label_status_event"].astype("string").eq("LABELED")
        )
        joined = joined.loc[trainable].copy()
        partitions = {
            name: joined.loc[joined["partition"].astype("string").eq(name)].copy()
            for name in ("train", "validation", "test")
        }
        train_labels = partitions["train"][variant.label_column].astype("string")
        if sorted(train_labels.unique().tolist()) != sorted(REPORT_LABELS):
            raise ValueError(f"Training labels are incomplete for {variant.variant_id}: {sorted(train_labels.unique().tolist())}")
        feature_lookup = variant.feature_bundle.frame.set_index("sample_id", drop=False)
        train_ids = partitions["train"]["sample_id"].astype("string").tolist()
        train_features = _feature_matrix(feature_lookup, train_ids, variant.feature_bundle.feature_names)
        evaluation_features = {
            name: _feature_matrix(feature_lookup, frame["sample_id"].astype("string").tolist(), variant.feature_bundle.feature_names)
            for name, frame in partitions.items() if name != "train"
        }
        job_dir = output_dir / "jobs" / variant.variant_id
        result = train_tabular_classifier(
            profile=profile,
            train_features=train_features,
            evaluation_features=evaluation_features,
            train_labels=train_labels,
            allowed_feature_columns=variant.feature_bundle.feature_names,
            train_sample_ids=train_ids,
            output_dir=job_dir,
            random_seed=random_seed,
            thread_count=thread_count,
            task_metadata={
                "variant_id": variant.variant_id,
                "representation": variant.representation,
                "target_view_id": variant.target_view_id,
                "target_semantics": "ONLINE_CAUSAL_CONFIRMATION" if variant.target_view_id == Y_ONLINE else "EVENT_RETROSPECTIVE",
                "feature_count": len(variant.feature_bundle.feature_names),
                "feature_metadata": variant.feature_bundle.metadata,
            },
        )
        class_names = result.class_names
        class_lookup = {name: index for index, name in enumerate(class_names)}
        for partition in ("validation", "test"):
            partition_frame = partitions[partition]
            y_true = partition_frame[variant.label_column].map(class_lookup).to_numpy(dtype=np.int64)
            y_pred = np.asarray(result.evaluation_predictions[partition], dtype=np.int64)
            probabilities = result.evaluation_probabilities.get(partition)
            metrics = summarize_protocol_classification(y_true, y_pred, class_names)
            metrics.update(_probability_metrics(y_true, probabilities, class_names))
            for class_name, class_metrics in metrics["class_metrics"].items():
                per_class_rows.append({
                    "variant_id": variant.variant_id,
                    "representation": variant.representation,
                    "target_view_id": variant.target_view_id,
                    "partition": partition,
                    "class_name": class_name,
                    **class_metrics,
                })
            for true_index, true_name in enumerate(class_names):
                for pred_index, pred_name in enumerate(class_names):
                    confusion_rows.append({
                        "variant_id": variant.variant_id,
                        "representation": variant.representation,
                        "target_view_id": variant.target_view_id,
                        "partition": partition,
                        "true_label": true_name,
                        "predicted_label": pred_name,
                        "count": int(metrics["confusion_matrix"][true_index][pred_index]),
                    })
            metrics_rows.append({
                "variant_id": variant.variant_id,
                "representation": variant.representation,
                "target_view_id": variant.target_view_id,
                "feature_count": len(variant.feature_bundle.feature_names),
                "model_key": "xgboost",
                "partition": partition,
                "train_count": len(partitions["train"]),
                "evaluation_count": len(partition_frame),
                "accuracy": metrics["accuracy"],
                "balanced_accuracy": metrics["supported_class_balanced_accuracy"],
                "macro_f1": metrics["supported_class_macro_f1"],
                "weighted_f1": metrics["weighted_f1"],
                "macro_pr_auc_ovr": metrics["macro_pr_auc_ovr"],
                "macro_roc_auc_ovr": metrics["macro_roc_auc_ovr"],
                "low_recall": metrics["class_metrics"].get(LOW_LABEL, {}).get("recall"),
                "unres_recall": metrics["class_metrics"].get(UNRES_LABEL, {}).get("recall"),
                "ref_recall": metrics["class_metrics"].get(REF_LABEL, {}).get("recall"),
            })
            for index, row in enumerate(partition_frame.to_dict(orient="records")):
                prediction = {
                    "variant_id": variant.variant_id,
                    "representation": variant.representation,
                    "target_view_id": variant.target_view_id,
                    "partition": partition,
                    "sample_id": str(row["sample_id"]),
                    "label_true": str(row[variant.label_column]),
                    "label_online": str(row["label_online"]),
                    "label_event": str(row["label_event"]),
                    "label_pred": class_names[int(y_pred[index])],
                    "provenance_stratum": _provenance_stratum(row),
                    "depth_bin": _depth_bin(int(row["support_depth_at_anchor"])),
                    "support_depth_at_anchor": int(row["support_depth_at_anchor"]),
                    "eventual_run_length": row["eventual_run_length"],
                    "event_vs_online_changed": bool(row["event_vs_online_changed"]),
                }
                if probabilities is not None:
                    probability_map = {name: float(value) for name, value in zip(class_names, probabilities[index], strict=True)}
                    prediction.update({
                        "p_low": probability_map.get(LOW_LABEL, np.nan),
                        "p_unres": probability_map.get(UNRES_LABEL, np.nan),
                        "p_ref": probability_map.get(REF_LABEL, np.nan),
                    })
                prediction_rows.append(prediction)

    predictions = pd.DataFrame(prediction_rows).convert_dtypes()
    strata = build_stratum_metrics(predictions)
    return (
        pd.DataFrame(metrics_rows).convert_dtypes(),
        pd.DataFrame(per_class_rows).convert_dtypes(),
        pd.DataFrame(confusion_rows).convert_dtypes(),
        predictions,
        strata,
    )


def build_stratum_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    working = predictions.copy()
    working["is_low_pred"] = working["label_pred"].astype("string").eq(LOW_LABEL)
    working["is_unres_pred"] = working["label_pred"].astype("string").eq(UNRES_LABEL)
    working["is_ref_pred"] = working["label_pred"].astype("string").eq(REF_LABEL)
    working["online_correct"] = working["label_pred"].astype("string").eq(working["label_online"].astype("string"))
    working["event_correct"] = working["label_pred"].astype("string").eq(working["label_event"].astype("string"))
    return (
        working.groupby(
            ["variant_id", "representation", "target_view_id", "partition", "provenance_stratum", "depth_bin"],
            dropna=False,
            sort=True,
        )
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            hard_low_rate=("is_low_pred", "mean"),
            hard_unres_rate=("is_unres_pred", "mean"),
            hard_ref_rate=("is_ref_pred", "mean"),
            mean_p_low=("p_low", "mean"),
            mean_p_unres=("p_unres", "mean"),
            mean_p_ref=("p_ref", "mean"),
            online_accuracy=("online_correct", "mean"),
            event_accuracy=("event_correct", "mean"),
        )
        .reset_index()
        .convert_dtypes()
    )


def _feature_matrix(feature_lookup: pd.DataFrame, sample_ids: list[str], feature_names: list[str]) -> np.ndarray:
    return feature_lookup.loc[sample_ids, feature_names].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)


def _probability_metrics(y_true: np.ndarray, probabilities: list[list[float]] | None, class_names: list[str]) -> dict[str, float]:
    if probabilities is None:
        return {"macro_pr_auc_ovr": float("nan"), "macro_roc_auc_ovr": float("nan")}
    scores = np.asarray(probabilities, dtype=float)
    one_hot = np.eye(len(class_names), dtype=float)[y_true]
    try:
        macro_pr_auc = float(average_precision_score(one_hot, scores, average="macro"))
    except ValueError:
        macro_pr_auc = float("nan")
    try:
        macro_roc_auc = float(roc_auc_score(y_true, scores, multi_class="ovr", average="macro"))
    except ValueError:
        macro_roc_auc = float("nan")
    return {"macro_pr_auc_ovr": macro_pr_auc, "macro_roc_auc_ovr": macro_roc_auc}


def _provenance_stratum(row: dict[str, object]) -> str:
    online_label = str(row.get("label_online", ""))
    origin = str(row.get("unres_origin", ""))
    depth = int(row.get("support_depth_at_anchor") or 0)
    eventual = row.get("eventual_run_length")
    if online_label == LOW_LABEL:
        return "LOW"
    if origin == "UNRES_K":
        eventual_value = pd.to_numeric(pd.Series([eventual]), errors="coerce").iloc[0]
        if pd.notna(eventual_value) and float(eventual_value) >= 3:
            return "U_K_succ"
        return "U_K_fail"
    if origin == "UNRES_A":
        return "U_A"
    if online_label == REF_LABEL:
        return "REF"
    return "OTHER"


def _depth_bin(depth: int) -> str:
    if depth >= 3:
        return "d>=3"
    if depth in (1, 2):
        return f"d={depth}"
    return "d=0_or_other"
