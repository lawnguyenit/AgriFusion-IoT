from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from Backend.Benchmark.model_suite.registries import build_estimator, resolve_model_profile
from .inputs import load_reviewed_audit, sha256_file
from .metrics import binary_metrics
from .stuard_controls import _paired_day_log_loss_contrast


SOIL_FEATURES = ("soil_temperature_c", "soil_ec_us_cm")
ENVIRONMENT_FEATURES = ("air_temperature_c", "air_humidity_pct", "air_co2_ppm", "air_pressure_hpa")


def run_stuard_acquisition_controls(
    *,
    audit_dir: Path,
    target_column: str,
    output_dir: Path,
    model_key: str = "xgboost",
    random_seed: int = 20261001,
    thread_count: int = 1,
    bootstrap_repetitions: int = 1000,
) -> Path:
    """Separate sensor-value gains from sensor-availability-pattern gains."""
    features, labels, splits, lineage = load_reviewed_audit(audit_dir, (target_column,))
    source_labels_path = Path(str(lineage.get("source_artifacts", {}).get("labels_path", "")))
    if not source_labels_path.is_file():
        raise ValueError("The reviewed audit does not retain source entity/timestamp metadata.")
    metadata = pd.read_parquet(source_labels_path)
    if not {"sample_id", "entity_id", "timestamp"}.issubset(metadata.columns):
        raise ValueError("Stuard acquisition controls require sample, entity, and timestamp metadata.")

    sensor_features = [*SOIL_FEATURES, *ENVIRONMENT_FEATURES]
    missing_features = [name for name in sensor_features if name not in lineage["feature_columns"]]
    if missing_features:
        raise ValueError(f"The reviewed feature selection lacks Stuard sensor columns: {missing_features}")
    source_features = features.loc[:, ["sample_id", *sensor_features]].copy()
    for column in sensor_features:
        source_features[column] = pd.to_numeric(source_features[column], errors="coerce")
    values = source_features.loc[:, sensor_features].to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise ValueError("Stuard source features contain infinite values.")

    frame = (
        source_features.merge(labels, on="sample_id", how="inner", validate="one_to_one")
        .merge(splits.loc[:, ["sample_id", "fold_id", "partition"]], on="sample_id", how="inner", validate="one_to_one")
        .merge(metadata.loc[:, ["sample_id", "entity_id", "timestamp"]], on="sample_id", how="left", validate="one_to_one")
    )
    if frame["entity_id"].isna().any() or frame["timestamp"].isna().any():
        raise ValueError("Every control sample must resolve to an entity and timestamp.")
    frame["_y"] = pd.to_numeric(frame[target_column], errors="coerce")
    frame["_x_observable"] = frame.loc[:, sensor_features].notna().any(axis=1)

    folds = frame["fold_id"].astype("string").unique().tolist()
    if len(folds) != 1:
        raise ValueError("Acquisition controls require the approved single 70/15/15 holdout.")
    fold_id = folds[0]
    train = frame.loc[frame["partition"].astype("string").eq("train")]
    train_fit = train.loc[train["_y"].notna() & train["_x_observable"]].copy()
    if train_fit["_y"].nunique() != 2:
        raise ValueError("Known, observable Stuard training rows must contain both target classes.")
    evaluation = frame.loc[
        frame["partition"].astype("string").isin(["validation", "test"])
        & frame["_y"].notna()
        & frame["_x_observable"]
    ].copy()
    if evaluation.empty:
        raise ValueError("No known, observable held-out rows are available for acquisition controls.")

    all_entities = sorted(train_fit["entity_id"].astype("string").unique().tolist())
    if set(frame["entity_id"].astype("string").unique()) - set(all_entities):
        raise ValueError("Held-out entity categories must be present in training for linked Stuard controls.")
    profile = resolve_model_profile(model_key, use_balanced_sample_weight=False)
    # Nested acquisition experiment: every arm retains the same six availability
    # indicators and line identity. Only the measured-value groups change.
    arm_features = {
        "B_line_plus_all_availability": ((), sensor_features),
        "B_plus_soil_values": (list(SOIL_FEATURES), sensor_features),
        "B_plus_environment_values": (list(ENVIRONMENT_FEATURES), sensor_features),
        "B_plus_all_values": (sensor_features, sensor_features),
    }
    arm_dimensions: dict[str, dict[str, object]] = {}
    prediction_rows: list[dict[str, object]] = []
    model_dir = output_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=False)

    y_train = train_fit["_y"].astype(int).to_numpy()
    train_entities = train_fit["entity_id"].astype("string").to_numpy()
    train_onehot = _one_hot(train_entities, all_entities)
    for arm, (value_columns, availability_columns) in arm_features.items():
        train_matrix, feature_names = _arm_matrix(train_fit, value_columns, availability_columns)
        eval_matrix, _ = _arm_matrix(evaluation, value_columns, availability_columns)
        medians = np.nanmedian(train_matrix, axis=0)
        medians = np.where(np.isfinite(medians), medians, 0.0)
        train_matrix = np.where(np.isnan(train_matrix), medians, train_matrix)
        eval_matrix = np.where(np.isnan(eval_matrix), medians, eval_matrix)
        train_x = np.column_stack([train_matrix, train_onehot])
        estimator, library_version = build_estimator(
            profile=profile,
            random_seed=random_seed,
            thread_count=thread_count,
            class_count=2,
        )
        estimator.fit(train_x, y_train)
        joblib.dump({
            "model": estimator,
            "value_and_availability_features": feature_names,
            "line_categories_fit_on_train": all_entities,
            "training_sample_ids": train_fit["sample_id"].astype("string").tolist(),
        }, model_dir / f"{arm}.joblib")
        entity_dimension = int(train_onehot.shape[1])
        arm_dimensions[arm] = {
            "sensor_feature_count": len(value_columns),
            "availability_indicator_count": len(availability_columns),
            "availability_features": [f"{column}__available" for column in availability_columns],
            "group_context_columns": ["entity_id"],
            "group_context_count": 1,
            "entity_one_hot_dimension": entity_dimension,
            "transformed_model_dimension": int(train_x.shape[1]),
            "uses_entity_identity": True,
            "input_features": [*feature_names, *[f"entity_id=={category}" for category in all_entities]],
        }
        eval_entities = evaluation["entity_id"].astype("string").to_numpy()
        probabilities = estimator.predict_proba(np.column_stack([eval_matrix, _one_hot(eval_entities, all_entities)]))[:, 1]
        prediction_rows.extend(_prediction_records(evaluation, probabilities, arm, arm_dimensions[arm]))

    predictions = pd.DataFrame(prediction_rows)
    expected_arms = set(arm_features)
    if set(predictions["arm"].astype("string").unique()) != expected_arms:
        raise RuntimeError("The nested Stuard control did not emit exactly the four approved arms.")
    for partition, part in predictions.groupby("partition", sort=False):
        expected_ids = None
        for arm, arm_part in part.groupby("arm", sort=False):
            current_ids = set(arm_part["sample_id"].astype("string"))
            if expected_ids is None:
                expected_ids = current_ids
            elif current_ids != expected_ids:
                raise RuntimeError(f"Nested arms do not share evaluation sample IDs in {partition}.")
            dimensions = arm_dimensions[arm]
            if dimensions["availability_indicator_count"] != len(sensor_features):
                raise RuntimeError(f"Arm {arm} does not retain all six availability indicators.")

    predictions_path = output_dir / "control_predictions.csv"
    predictions.to_csv(predictions_path, index=False)
    metric_rows: list[dict[str, object]] = []
    for (partition, arm), part in predictions.groupby(["partition", "arm"], sort=True):
        metric = binary_metrics(part["y_true"].astype(int).to_numpy(), part["y_pred"].astype(int).to_numpy(), part["positive_probability"].astype(float).to_numpy())
        dimensions = json.loads(part["arm_dimensions_json"].iloc[0])
        metric_rows.append({
            "fold_id": str(fold_id),
            "partition": str(partition),
            "target": target_column,
            "arm": arm,
            "metric_evaluation_count": metric["sample_count"],
            "positive_prevalence": metric["positive_prevalence"],
            "balanced_accuracy": metric["supported_class_balanced_accuracy"],
            "f1_positive": metric["f1_positive"],
            "roc_auc": metric["roc_auc"],
            "average_precision": metric["average_precision"],
            "brier_score": metric["brier_score"],
            "log_loss": metric["log_loss"],
            **{
                **dimensions,
                "input_features": json.dumps(dimensions["input_features"], ensure_ascii=False),
                "availability_features": json.dumps(dimensions["availability_features"], ensure_ascii=False),
            },
        })
    metrics_path = output_dir / "control_metrics.csv"
    pd.DataFrame(metric_rows).to_csv(metrics_path, index=False)

    contrasts: list[dict[str, object]] = []
    comparisons = [
        ("B_line_plus_all_availability", "B_plus_soil_values"),
        ("B_line_plus_all_availability", "B_plus_environment_values"),
        ("B_line_plus_all_availability", "B_plus_all_values"),
    ]
    for partition in ("validation", "test"):
        part = predictions.loc[predictions["partition"].astype("string").eq(partition)]
        for baseline, augmented in comparisons:
            point, low, high, cluster_count = _paired_day_log_loss_contrast(
                part,
                metadata,
                baseline_arm=baseline,
                augmented_arm=augmented,
                repetitions=bootstrap_repetitions,
                seed=random_seed,
            )
            contrasts.append({
                "fold_id": str(fold_id),
                "partition": partition,
                "target": target_column,
                "baseline_arm": baseline,
                "augmented_arm": augmented,
                "delta_log_loss_baseline_minus_augmented": point,
                "delta_log_loss_ci_low": low,
                "delta_log_loss_ci_high": high,
                "cluster_count": cluster_count,
                "bootstrap_repetitions": bootstrap_repetitions,
                "bootstrap_unit": "UTC calendar day",
            })
    contrasts_path = output_dir / "control_contrasts.csv"
    pd.DataFrame(contrasts).to_csv(contrasts_path, index=False)
    manifest = {
        "schema_version": 1,
        "status": "complete",
        "target": target_column,
        "fold_id": str(fold_id),
        "design": "nested Stuard acquisition control; B=line_id+all-six-sensor-availability; augmented arms retain B and add value groups",
        "arms": list(arm_features),
        "comparison_population": "same target-known and any-sensor-observable sample IDs for all four arms; six availability flags retained in every arm",
        "train_fit_count": int(len(train_fit)),
        "train_unknown_excluded_count": int(train["_y"].isna().sum()),
        "train_known_no_x_excluded_count": int((train["_y"].notna() & ~train["_x_observable"]).sum()),
        "evaluation_count_by_partition": {
            str(key): int(len(value)) for key, value in evaluation.groupby("partition", sort=True)
        },
        "evaluation_sample_id_sha256_by_partition": {
            str(partition): hashlib.sha256(
                "\n".join(sorted(part["sample_id"].astype("string").tolist())).encode("utf-8")
            ).hexdigest()
            for partition, part in evaluation.groupby("partition", sort=True)
        },
        "training_fit_sample_id_sha256": hashlib.sha256(
            "\n".join(sorted(train_fit["sample_id"].astype("string").tolist())).encode("utf-8")
        ).hexdigest(),
        "preprocessing": {
            "sensor_value_missingness": "all six availability flags are explicit in every arm",
            "value_imputation": "per-arm medians fit on training rows only; all-missing columns fall back to 0",
            "line_identity": "one-hot categories fit on training rows only",
            "probability_threshold": 0.5,
        },
        "paired_contrast_definition": "log_loss(B)-log_loss(B+S); 95% percentile CI via paired UTC-calendar-day block bootstrap",
        "model_key": profile.model_key,
        "model_hyperparameters": profile.hyperparameters,
        "balanced_sample_weight": False,
        "random_seed": random_seed,
        "thread_count": thread_count,
        "model_library_version": library_version,
        "audit_manifest_path": str((audit_dir / "audit_manifest.json").resolve()),
        "audit_manifest_sha256": sha256_file(audit_dir / "audit_manifest.json"),
        "source_labels_path": str(source_labels_path.resolve()),
        "source_labels_sha256": sha256_file(source_labels_path),
        "arm_dimensions": arm_dimensions,
        "control_metrics_path": metrics_path.name,
        "control_contrasts_path": contrasts_path.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    catalog_paths = [*model_dir.glob("*.joblib"), predictions_path, metrics_path, contrasts_path, manifest_path]
    (output_dir / "artifact_catalog.json").write_text(json.dumps([
        {"path": path.relative_to(output_dir).as_posix(), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for path in catalog_paths
    ], ensure_ascii=False, indent=2), encoding="utf-8")
    return output_dir


def _arm_matrix(frame: pd.DataFrame, value_columns: list[str] | tuple[str, ...], availability_columns: list[str] | tuple[str, ...]) -> tuple[np.ndarray, list[str]]:
    columns: list[str] = []
    arrays: list[np.ndarray] = []
    for column in value_columns:
        columns.append(f"{column}__value")
        arrays.append(pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan))
    for column in availability_columns:
        columns.append(f"{column}__available")
        arrays.append(frame[column].notna().to_numpy(dtype=float))
    if not arrays:
        return np.empty((len(frame), 0)), columns
    return np.column_stack(arrays), columns


def _one_hot(entities: np.ndarray, categories: list[str]) -> np.ndarray:
    values = np.asarray(entities, dtype=str)
    return np.column_stack([values == category for category in categories]).astype(float)


def _prediction_records(part: pd.DataFrame, probabilities: np.ndarray, arm: str, dimensions: dict[str, object]) -> list[dict[str, object]]:
    values = part["_y"].astype(int).to_numpy()
    return [{
        "sample_id": str(sample_id),
        "partition": str(partition),
        "timestamp": str(timestamp),
        "entity_id": str(entity),
        "arm": arm,
        "y_true": int(y),
        "positive_probability": float(probability),
        "y_pred": int(probability >= 0.5),
        "arm_dimensions_json": json.dumps(dimensions, ensure_ascii=False, default=_json_default),
    } for sample_id, partition, timestamp, entity, y, probability in zip(
        part["sample_id"], part["partition"], part["timestamp"], part["entity_id"], values, probabilities, strict=True
    )]


def _json_default(value: object) -> object:
    if value is pd.NA:
        return None
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Value is not JSON serializable: {type(value).__name__}")
