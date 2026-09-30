from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification
from Backend.Benchmark.model_suite.pipeline.training_job import train_tabular_classifier
from Backend.Benchmark.model_suite.registries import resolve_model_profile

from .representations import CalibrationRepresentation
from .worlds import CLASS_NAMES, WorldDataset


def run_world_calibration(
    *,
    dataset: WorldDataset,
    representations: dict[str, CalibrationRepresentation],
    seeds: tuple[int, ...],
    output_dir: Path,
    thread_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train the registered XGBoost path and return metrics, losses, and oracle rows."""

    profile = resolve_model_profile("xgboost")
    metric_rows: list[dict[str, object]] = []
    loss_rows: list[dict[str, object]] = []
    oracle_rows: list[dict[str, object]] = []
    source = dataset.frame
    for seed in seeds:
        for representation_id, representation in representations.items():
            joined = source.merge(representation.frame, on="sample_id", how="inner", validate="one_to_one")
            partitions = {
                name: joined.loc[joined["partition"].astype("string").eq(name)].copy()
                for name in ("train", "validation", "test")
            }
            feature_lookup = representation.frame.set_index("sample_id", drop=False)
            train_ids = partitions["train"]["sample_id"].astype("string").tolist()
            train_labels = partitions["train"]["label"].astype("string")
            if sorted(train_labels.unique().tolist()) != sorted(CLASS_NAMES):
                raise ValueError(f"Training labels are incomplete for {dataset.world_id}/{representation_id}")
            job_dir = output_dir / "jobs" / dataset.world_id / f"seed_{seed}" / representation_id
            result = train_tabular_classifier(
                profile=profile,
                train_features=_feature_matrix(feature_lookup, train_ids, representation.feature_names),
                evaluation_features={
                    partition: _feature_matrix(feature_lookup, frame["sample_id"].astype("string").tolist(), representation.feature_names)
                    for partition, frame in partitions.items()
                    if partition != "train"
                },
                train_labels=train_labels,
                allowed_feature_columns=list(representation.feature_names),
                train_sample_ids=train_ids,
                output_dir=job_dir,
                random_seed=seed,
                thread_count=thread_count,
                task_metadata={
                    "calibration_world": dataset.world_id,
                    "representation_id": representation_id,
                    "mechanism": dataset.metadata["mechanism"],
                },
            )
            class_names = tuple(result.class_names)
            class_lookup = {name: index for index, name in enumerate(class_names)}
            for partition in ("validation", "test"):
                frame = partitions[partition]
                y_true = frame["label"].map(class_lookup).to_numpy(dtype=np.int64)
                y_pred = np.asarray(result.evaluation_predictions[partition], dtype=np.int64)
                probabilities = np.asarray(result.evaluation_probabilities[partition], dtype=float)
                probabilities = np.clip(probabilities, 1e-15, None)
                probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
                classification = summarize_protocol_classification(y_true, y_pred, list(class_names))
                loss = _multiclass_log_loss(y_true, probabilities)
                brier = _multiclass_brier(y_true, probabilities)
                metric_rows.append(
                    {
                        "world_id": dataset.world_id,
                        "seed": seed,
                        "representation_id": representation_id,
                        "partition": partition,
                        "feature_count": len(representation.feature_names),
                        "evaluation_count": len(frame),
                        "log_loss": loss,
                        "brier_loss": brier,
                        "macro_f1": classification["supported_class_macro_f1"],
                        "balanced_accuracy": classification["supported_class_balanced_accuracy"],
                        "weighted_f1": classification["weighted_f1"],
                        "class_names": list(class_names),
                    }
                )
                if partition == "test":
                    loss_rows.extend(
                        _loss_rows(
                            frame=frame,
                            world_id=dataset.world_id,
                            seed=seed,
                            representation_id=representation_id,
                            y_true=y_true,
                            probabilities=probabilities,
                            class_names=class_names,
                        )
                    )

            oracle = _oracle_metrics(dataset=dataset, partitions=partitions, class_names=class_names)
            if representation_id == "R_full" and seed == seeds[0]:
                oracle_rows.extend(oracle)

    return (
        pd.DataFrame(metric_rows).convert_dtypes(),
        pd.DataFrame(loss_rows).convert_dtypes(),
        pd.DataFrame(oracle_rows).convert_dtypes(),
    )


def _loss_rows(
    *,
    frame: pd.DataFrame,
    world_id: str,
    seed: int,
    representation_id: str,
    y_true: np.ndarray,
    probabilities: np.ndarray,
    class_names: tuple[str, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, row in enumerate(frame.to_dict(orient="records")):
        true_probability = max(float(probabilities[index, y_true[index]]), 1e-15)
        one_hot = np.eye(len(class_names), dtype=float)[y_true[index]]
        rows.append(
            {
                "world_id": world_id,
                "seed": seed,
                "representation_id": representation_id,
                "sample_id": str(row["sample_id"]),
                "sequence_id": int(row["sequence_id"]),
                "time_index": int(row["time_index"]),
                "log_loss": float(-np.log(true_probability)),
                "brier_loss": float(np.sum((probabilities[index] - one_hot) ** 2)),
            }
        )
    return rows


def _oracle_metrics(*, dataset: WorldDataset, partitions: dict[str, pd.DataFrame], class_names: tuple[str, ...]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    lookup = {name: index for index, name in enumerate(class_names)}
    for partition, frame in partitions.items():
        if partition == "train":
            continue
        y_true = frame["label"].map(lookup).to_numpy(dtype=np.int64)
        y_oracle = frame["oracle_label"].map(lookup).to_numpy(dtype=np.int64)
        metrics = summarize_protocol_classification(y_true, y_oracle, list(class_names))
        rows.append(
            {
                "world_id": dataset.world_id,
                "partition": partition,
                "oracle_accuracy": metrics["accuracy"],
                "oracle_macro_f1": metrics["supported_class_macro_f1"],
                "oracle_balanced_accuracy": metrics["supported_class_balanced_accuracy"],
                "oracle_disagreement_rate": float(np.mean(y_true != y_oracle)),
            }
        )
    return rows


def _feature_matrix(feature_lookup: pd.DataFrame, sample_ids: list[str], feature_names: tuple[str, ...]) -> np.ndarray:
    return feature_lookup.loc[sample_ids, list(feature_names)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)


def _multiclass_log_loss(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    return float(log_loss(y_true, probabilities, labels=list(range(probabilities.shape[1]))))


def _multiclass_brier(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    one_hot = np.eye(probabilities.shape[1], dtype=float)[y_true]
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))
