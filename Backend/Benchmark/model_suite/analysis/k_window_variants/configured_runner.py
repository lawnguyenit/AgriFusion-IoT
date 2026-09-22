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
from .representations import RepresentationBundle
from .runner import LOW_LABEL, REF_LABEL, REPORT_LABELS, UNRES_LABEL
from .semantic_runner import _depth_bin, _provenance_stratum


@dataclass(frozen=True)
class ConfiguredVariant:
    variant_id: str
    representation_id: str
    target_view_id: str
    target_semantics: str
    k: int
    label_column: str
    representation: RepresentationBundle


def build_configured_variants(
    *,
    representations: dict[str, RepresentationBundle],
) -> tuple[ConfiguredVariant, ...]:
    """Build the exact schedule from the R/K design.

    K=1 keeps R00 as the primary baseline and R11 as the optional control.
    K>1 evaluates every R representation separately for online and event
    targets. The target views remain separate throughout training and output.
    """

    r00 = representations["R00"]
    r10 = representations["R10"]
    r01 = representations["R01"]
    r11 = representations["R11"]
    variants: list[ConfiguredVariant] = [
        ConfiguredVariant("k1_R00", "R00", "temporal_k1", "K1_ADDITIVE_TEMPORAL", 1, "label_k1", r00),
        ConfiguredVariant("k1_R11", "R11", "temporal_k1", "K1_ADDITIVE_TEMPORAL", 1, "label_k1", r11),
    ]
    for target_view_id, target_semantics, label_column in (
        ("temporal_online_3h", "K3_ONLINE_CAUSAL", "label_online"),
        ("temporal_event_3h", "K3_EVENT_RETROSPECTIVE", "label_event"),
    ):
        for representation in (r00, r10, r01, r11):
            variants.append(
                ConfiguredVariant(
                    f"k3_{target_view_id.removeprefix('temporal_')}_{representation.representation_id}",
                    representation.representation_id,
                    target_view_id,
                    target_semantics,
                    3,
                    label_column,
                    representation,
                )
            )
    return tuple(variants)


def run_configured_variants(
    *,
    variants: tuple[ConfiguredVariant, ...],
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
        bundle = variant.representation.feature_bundle
        joined = target_frame.merge(bundle.frame, on="sample_id", how="inner", validate="one_to_one")
        if len(joined) != len(target_frame):
            raise ValueError(f"Feature representation does not cover the target universe: {variant.variant_id}")
        trainable = joined["final_trainability"].fillna(False).astype(bool)
        trainable &= joined[variant.label_column].notna()
        joined = joined.loc[trainable].copy()
        partitions = {
            name: joined.loc[joined["partition"].astype("string").eq(name)].copy()
            for name in ("train", "validation", "test")
        }
        train_labels = partitions["train"][variant.label_column].astype("string")
        if sorted(train_labels.unique().tolist()) != sorted(REPORT_LABELS):
            raise ValueError(f"Training labels are incomplete for {variant.variant_id}: {sorted(train_labels.unique().tolist())}")
        feature_lookup = bundle.frame.set_index("sample_id", drop=False)
        train_ids = partitions["train"]["sample_id"].astype("string").tolist()
        feature_names = bundle.feature_names
        result = train_tabular_classifier(
            profile=profile,
            train_features=_feature_matrix(feature_lookup, train_ids, feature_names),
            evaluation_features={
                name: _feature_matrix(feature_lookup, frame["sample_id"].astype("string").tolist(), feature_names)
                for name, frame in partitions.items() if name != "train"
            },
            train_labels=train_labels,
            allowed_feature_columns=feature_names,
            train_sample_ids=train_ids,
            output_dir=output_dir / "jobs" / variant.variant_id,
            random_seed=random_seed,
            thread_count=thread_count,
            task_metadata={
                "variant_id": variant.variant_id,
                "representation_id": variant.representation_id,
                "target_view_id": variant.target_view_id,
                "target_semantics": variant.target_semantics,
                "k": variant.k,
                "feature_count": len(feature_names),
                "feature_metadata": bundle.metadata,
            },
        )
        class_names = result.class_names
        class_lookup = {name: index for index, name in enumerate(class_names)}
        variant_metrics: dict[str, dict[str, object]] = {}
        for partition in ("validation", "test"):
            partition_frame = partitions[partition]
            y_true = partition_frame[variant.label_column].map(class_lookup).to_numpy(dtype=np.int64)
            y_pred = np.asarray(result.evaluation_predictions[partition], dtype=np.int64)
            probabilities = result.evaluation_probabilities.get(partition)
            metrics = summarize_protocol_classification(y_true, y_pred, class_names)
            metrics.update(_probability_metrics(y_true, probabilities, class_names))
            variant_metrics[partition] = metrics
            for class_name, class_metrics in metrics["class_metrics"].items():
                per_class_rows.append({
                    "variant_id": variant.variant_id,
                    "representation_id": variant.representation_id,
                    "target_view_id": variant.target_view_id,
                    "k": variant.k,
                    "partition": partition,
                    "class_name": class_name,
                    **class_metrics,
                })
            for true_index, true_name in enumerate(class_names):
                for pred_index, pred_name in enumerate(class_names):
                    confusion_rows.append({
                        "variant_id": variant.variant_id,
                        "representation_id": variant.representation_id,
                        "target_view_id": variant.target_view_id,
                        "k": variant.k,
                        "partition": partition,
                        "true_label": true_name,
                        "predicted_label": pred_name,
                        "count": int(metrics["confusion_matrix"][true_index][pred_index]),
                    })
            for index, row in enumerate(partition_frame.to_dict(orient="records")):
                probability_map = {}
                if probabilities is not None:
                    probability_map = {
                        name: float(value)
                        for name, value in zip(class_names, probabilities[index], strict=True)
                    }
                prediction_rows.append({
                    "variant_id": variant.variant_id,
                    "representation_id": variant.representation_id,
                    "target_view_id": variant.target_view_id,
                    "target_semantics": variant.target_semantics,
                    "k": variant.k,
                    "partition": partition,
                    "sample_id": str(row["sample_id"]),
                    "label_true": str(row[variant.label_column]),
                    "label_online": _optional_string(row.get("label_online")),
                    "label_event": _optional_string(row.get("label_event")),
                    "label_pred": class_names[int(y_pred[index])],
                    "provenance_stratum": _provenance_stratum(row) if variant.k > 1 else "NOT_APPLICABLE",
                    "depth_bin": _depth_bin(int(row.get("support_depth_at_anchor") or 0)),
                    "support_depth_at_anchor": row.get("support_depth_at_anchor"),
                    "eventual_run_length": row.get("eventual_run_length"),
                    "p_low": probability_map.get(LOW_LABEL, np.nan),
                    "p_unres": probability_map.get(UNRES_LABEL, np.nan),
                    "p_ref": probability_map.get(REF_LABEL, np.nan),
                })
            metrics_rows.append({
                "variant_id": variant.variant_id,
                "representation_id": variant.representation_id,
                "representation": variant.representation.display_name,
                "target_view_id": variant.target_view_id,
                "target_semantics": variant.target_semantics,
                "k": variant.k,
                "feature_count": len(feature_names),
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
                "low_support": metrics["class_metrics"].get(LOW_LABEL, {}).get("support"),
                "unres_support": metrics["class_metrics"].get(UNRES_LABEL, {}).get("support"),
                "ref_support": metrics["class_metrics"].get(REF_LABEL, {}).get("support"),
            })
        job_dir = output_dir / "jobs" / variant.variant_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "variant_metrics.json").write_text(
            json.dumps(variant_metrics, ensure_ascii=True, indent=2, allow_nan=True),
            encoding="utf-8",
        )

    predictions = pd.DataFrame(prediction_rows).convert_dtypes()
    strata = _build_strata(predictions)
    return (
        pd.DataFrame(metrics_rows).convert_dtypes(),
        pd.DataFrame(per_class_rows).convert_dtypes(),
        pd.DataFrame(confusion_rows).convert_dtypes(),
        predictions,
        strata,
    )


def _build_strata(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    working = predictions.loc[predictions["k"].astype("Int64").eq(3)].copy()
    if working.empty:
        return pd.DataFrame()
    working["is_low_pred"] = working["label_pred"].astype("string").eq(LOW_LABEL)
    working["online_correct"] = working["label_pred"].astype("string").eq(working["label_online"].astype("string"))
    working["event_correct"] = working["label_pred"].astype("string").eq(working["label_event"].astype("string"))
    return (
        working.groupby(
            ["variant_id", "representation_id", "target_view_id", "partition", "provenance_stratum", "depth_bin"],
            dropna=False,
            sort=True,
        )
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            hard_low_rate=("is_low_pred", "mean"),
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


def _optional_string(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)
