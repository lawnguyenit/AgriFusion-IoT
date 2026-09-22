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


LOW_LABEL = "persistent_low_relative_moisture_at_anchor"
UNRES_LABEL = "unresolved_environmental_evidence_at_anchor"
REF_LABEL = "reference_context_at_anchor"
REPORT_LABELS = (LOW_LABEL, UNRES_LABEL, REF_LABEL)


@dataclass(frozen=True)
class VariantDefinition:
    variant_id: str
    representation: str
    k: int
    feature_view_id: str
    feature_run_dir: Path
    label_column: str


def load_feature_matrix(*, run_dir: Path, view_id: str) -> tuple[pd.DataFrame, list[str], dict[str, object]]:
    view_dir = run_dir.resolve() / "views" / view_id
    manifest_path = view_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Feature view manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row_index = pd.read_parquet(run_dir.resolve() / "shared" / "row_index.parquet").convert_dtypes()
    features = pd.read_parquet(view_dir / "X.parquet").convert_dtypes()
    feature_names = [str(value) for value in manifest["ordered_feature_list"]]
    if len(features) != len(row_index) or list(features.columns) != feature_names:
        raise ValueError(f"Feature view is not aligned with its manifest: {view_id}")
    frame = features.copy()
    frame.insert(0, "sample_id", row_index["record.id"].astype("string"))
    if frame["sample_id"].duplicated().any():
        raise ValueError(f"Feature view has duplicate sample IDs: {view_id}")
    return frame, feature_names, manifest


def build_variant_definitions(*, snapshot_run_dir: Path, window_run_dir: Path) -> tuple[VariantDefinition, ...]:
    return (
        VariantDefinition("snapshot_9_k1", "snapshot_9", 1, "v0_minimal_sensor", snapshot_run_dir, "label_k1"),
        VariantDefinition("snapshot_9_k3", "snapshot_9", 3, "v0_minimal_sensor", snapshot_run_dir, "label_k3"),
        VariantDefinition("window_3h_9_k1", "window_3h_9", 1, "v2_sensor_row_window_3h", window_run_dir, "label_k1"),
        VariantDefinition("window_3h_9_k3", "window_3h_9", 3, "v2_sensor_row_window_3h", window_run_dir, "label_k3"),
    )


def run_variants(
    *,
    variants: tuple[VariantDefinition, ...],
    target_frame: pd.DataFrame,
    output_dir: Path,
    random_seed: int,
    thread_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    profile = resolve_model_profile("xgboost")
    metrics_rows: list[dict[str, object]] = []
    per_class_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    matrix_cache: dict[tuple[str, str], tuple[pd.DataFrame, list[str], dict[str, object]]] = {}

    for variant in variants:
        cache_key = (str(variant.feature_run_dir.resolve()), variant.feature_view_id)
        if cache_key not in matrix_cache:
            matrix_cache[cache_key] = load_feature_matrix(
                run_dir=variant.feature_run_dir,
                view_id=variant.feature_view_id,
            )
        feature_frame, feature_names, manifest = matrix_cache[cache_key]
        joined = target_frame.merge(
            feature_frame,
            on="sample_id",
            how="inner",
            validate="one_to_one",
        )
        if len(joined) != len(target_frame):
            raise ValueError(f"Feature view does not cover the target universe: {variant.variant_id}")
        trainable = joined["final_trainability"].fillna(False).astype(bool)
        joined = joined.loc[trainable].copy()
        if set(joined["partition"].astype("string")) != {"train", "validation", "test"}:
            raise ValueError(f"Variant does not have all three partitions: {variant.variant_id}")

        partition_frames = {
            partition: joined.loc[joined["partition"].astype("string").eq(partition)].copy()
            for partition in ("train", "validation", "test")
        }
        train_labels = partition_frames["train"][variant.label_column].astype("string")
        if sorted(train_labels.unique().tolist()) != sorted(REPORT_LABELS):
            raise ValueError(f"Training labels are incomplete for {variant.variant_id}: {sorted(train_labels.unique().tolist())}")

        feature_lookup = feature_frame.set_index("sample_id", drop=False)
        train_ids = partition_frames["train"]["sample_id"].astype("string").tolist()
        train_features = _feature_matrix(feature_lookup, train_ids, feature_names)
        evaluation_features = {
            partition: _feature_matrix(
                feature_lookup,
                partition_frames[partition]["sample_id"].astype("string").tolist(),
                feature_names,
            )
            for partition in ("validation", "test")
        }
        job_dir = output_dir / "jobs" / variant.variant_id
        result = train_tabular_classifier(
            profile=profile,
            train_features=train_features,
            evaluation_features=evaluation_features,
            train_labels=train_labels,
            allowed_feature_columns=feature_names,
            train_sample_ids=train_ids,
            output_dir=job_dir,
            random_seed=random_seed,
            thread_count=thread_count,
            task_metadata={
                "variant_id": variant.variant_id,
                "representation": variant.representation,
                "k": variant.k,
                "feature_view_id": variant.feature_view_id,
                "feature_source_run_dir": str(variant.feature_run_dir.resolve()),
                "feature_list_hash": manifest.get("ordered_feature_list_hash"),
                "source_feature_artifact_hash": manifest.get("feature_artifact_hash"),
            },
        )

        variant_metrics: dict[str, dict[str, object]] = {}
        class_names = result.class_names
        class_lookup = {name: index for index, name in enumerate(class_names)}
        for partition in ("validation", "test"):
            partition_frame = partition_frames[partition]
            y_true = partition_frame[variant.label_column].map(class_lookup).to_numpy(dtype=np.int64)
            y_pred = np.asarray(result.evaluation_predictions[partition], dtype=np.int64)
            probabilities = result.evaluation_probabilities.get(partition)
            metrics = summarize_protocol_classification(y_true, y_pred, class_names)
            metrics.update(_probability_metrics(y_true, probabilities, class_names))
            variant_metrics[partition] = metrics
            for class_name, class_metrics in metrics["class_metrics"].items():
                per_class_rows.append(
                    {
                        "variant_id": variant.variant_id,
                        "representation": variant.representation,
                        "k": variant.k,
                        "partition": partition,
                        "class_name": class_name,
                        **class_metrics,
                    }
                )
            for true_index, true_name in enumerate(class_names):
                for pred_index, pred_name in enumerate(class_names):
                    confusion_rows.append(
                        {
                            "variant_id": variant.variant_id,
                            "representation": variant.representation,
                            "k": variant.k,
                            "partition": partition,
                            "true_label": true_name,
                            "predicted_label": pred_name,
                            "count": int(metrics["confusion_matrix"][true_index][pred_index]),
                        }
                    )
            for index, row in enumerate(partition_frame.to_dict(orient="records")):
                prediction = {
                    "variant_id": variant.variant_id,
                    "representation": variant.representation,
                    "k": variant.k,
                    "partition": partition,
                    "sample_id": str(row["sample_id"]),
                    "label_true": str(row[variant.label_column]),
                    "label_pred": class_names[int(y_pred[index])],
                }
                if probabilities is not None:
                    prediction["probability_json"] = json.dumps(
                        {name: float(value) for name, value in zip(class_names, probabilities[index], strict=True)},
                        ensure_ascii=True,
                        separators=(",", ":"),
                    )
                prediction_rows.append(prediction)

            (job_dir / f"{partition}_metrics.json").write_text(
                json.dumps(metrics, ensure_ascii=True, indent=2, allow_nan=True),
                encoding="utf-8",
            )

            metrics_rows.append(
                {
                    "variant_id": variant.variant_id,
                    "representation": variant.representation,
                    "k": variant.k,
                    "feature_view_id": variant.feature_view_id,
                    "feature_count": len(feature_names),
                    "model_key": "xgboost",
                    "partition": partition,
                    "train_count": len(partition_frames["train"]),
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
                    "class_names_json": json.dumps(class_names, ensure_ascii=True, separators=(",", ":")),
                }
            )

        (job_dir / "variant_metrics.json").write_text(
            json.dumps(variant_metrics, ensure_ascii=True, indent=2, allow_nan=True),
            encoding="utf-8",
        )

    return (
        pd.DataFrame(metrics_rows).convert_dtypes(),
        pd.DataFrame(per_class_rows).convert_dtypes(),
        pd.DataFrame(confusion_rows).convert_dtypes(),
        pd.DataFrame(prediction_rows).convert_dtypes(),
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
