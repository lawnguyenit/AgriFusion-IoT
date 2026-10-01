from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from Backend.Benchmark.model_suite.registries import build_estimator, resolve_model_profile
from Backend.Benchmark.model_suite.utils.preprocessing import fit_preprocessing_bundle, hash_sample_ids

from .inputs import load_reviewed_audit, sha256_file
from .metrics import binary_metrics


@dataclass(frozen=True)
class StuardControlConfig:
    audit_dir: Path
    target_column: str
    sensor_predictions_path: Path
    output_root: Path
    model_key: str = "xgboost"
    random_seed: int = 20261001
    thread_count: int = 1


def run_stuard_control_arms(config: StuardControlConfig) -> Path:
    """Compare priors, sensors, and line-plus-sensor controls on one fixed cohort."""
    features, labels, splits, lineage = load_reviewed_audit(config.audit_dir, (config.target_column,))
    labels_source = Path(str(lineage.get("source_artifacts", {}).get("labels_path", "")))
    if not labels_source.is_file():
        raise ValueError("The audit does not retain a readable source-label artifact for entity metadata.")
    source_metadata = pd.read_parquet(labels_source)
    source_columns = ["sample_id", "entity_id", *(["timestamp"] if "timestamp" in source_metadata.columns else [])]
    source = source_metadata.loc[:, source_columns].copy()
    source["sample_id"] = source["sample_id"].astype("string")
    feature_columns = list(lineage["feature_columns"])
    feature_values = features.loc[:, feature_columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(feature_values).any():
        raise ValueError("Stuard control features contain infinite values.")
    frame = (
        features.merge(labels, on="sample_id", how="inner", validate="one_to_one")
        .merge(splits.loc[:, ["sample_id", "fold_id", "partition"]], on="sample_id", how="inner", validate="one_to_one")
        .merge(source, on="sample_id", how="left", validate="one_to_one")
    )
    if frame["entity_id"].isna().any():
        raise ValueError("Stuard source entity IDs must align with every audit sample.")
    frame["_x_observable"] = np.isfinite(feature_values).any(axis=1)
    frame["_y"] = pd.to_numeric(frame[config.target_column], errors="coerce")
    profile = resolve_model_profile(config.model_key, use_balanced_sample_weight=False)
    fold_ids = frame["fold_id"].astype("string").unique().tolist()
    if len(fold_ids) != 1:
        raise ValueError("Stuard controls currently require the approved single 70/15/15 holdout.")
    fold_id = fold_ids[0]
    train = frame.loc[frame["partition"].astype("string").eq("train")]
    fit_mask = train["_y"].notna() & train["_x_observable"]
    fit_rows = train.loc[fit_mask].copy()
    if fit_rows["_y"].nunique() != 2:
        raise ValueError("The observable Stuard training cohort must contain both target classes.")
    y_train = fit_rows["_y"].astype(int).to_numpy()
    global_prior = float(y_train.mean())
    line_priors = fit_rows.groupby("entity_id", sort=True)["_y"].mean().to_dict()
    categories = sorted(fit_rows["entity_id"].astype("string").unique().tolist())
    train_ids = fit_rows["sample_id"].astype("string").tolist()
    train_features = fit_rows.loc[:, feature_columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    evaluation_parts = frame.loc[frame["partition"].astype("string").isin(["validation", "test"])].copy()
    observable_eval = evaluation_parts.loc[evaluation_parts["_y"].notna() & evaluation_parts["_x_observable"]].copy()
    if observable_eval.empty:
        raise ValueError("No known, observable Stuard validation/test rows are available for controls.")
    sensor_predictions = pd.read_parquet(config.sensor_predictions_path)
    if "target" in sensor_predictions:
        sensor_predictions = sensor_predictions.loc[sensor_predictions["target"].astype("string").eq(config.target_column)]
    sensor_predictions = sensor_predictions.loc[:, ["sample_id", "positive_probability", "prediction_status"]]
    sensor_predictions["sample_id"] = sensor_predictions["sample_id"].astype("string")
    sensor_predictions = sensor_predictions.drop_duplicates("sample_id")
    sensor_map = sensor_predictions.set_index("sample_id")["positive_probability"]
    observable_eval["_sensor_score"] = observable_eval["sample_id"].astype("string").map(sensor_map)
    if observable_eval["_sensor_score"].isna().any():
        raise ValueError("Sensor-only predictions do not cover every known, observable comparison row.")

    eval_features = {
        partition: part.loc[:, feature_columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        for partition, part in evaluation_parts.groupby("partition", sort=True)
    }
    preprocessing = fit_preprocessing_bundle(
        train_features=train_features,
        evaluation_features=eval_features,
        feature_names=feature_columns,
        enable_scaling=profile.enable_scaling,
        enable_variance_threshold=profile.enable_variance_threshold,
    )
    if not preprocessing["selected_feature_names"]:
        raise ValueError("Sensor preprocessing removed all features for the line-plus-sensor arm.")
    entity_train = fit_rows["entity_id"].astype("string").to_numpy()
    train_entity_features = _one_hot_entities(entity_train, categories)
    train_x = np.column_stack([preprocessing["train_features"], train_entity_features])
    estimator, library_version = build_estimator(
        profile=profile,
        random_seed=config.random_seed,
        thread_count=config.thread_count,
        class_count=2,
    )
    estimator.fit(train_x, y_train)
    model_dir = config.output_root
    model_dir.mkdir(parents=True, exist_ok=False)
    model_path = model_dir / "line_plus_sensors_model.joblib"
    joblib.dump({
        "model": estimator,
        "imputer": preprocessing["imputer"],
        "scaler": preprocessing["scaler"],
        "selector": preprocessing["selector"],
        "selected_sensor_features": preprocessing["selected_feature_names"],
        "line_categories_fit_on_train": categories,
        "training_sample_hash": hash_sample_ids(train_ids),
    }, model_path)

    rows: list[dict[str, object]] = []
    for partition, part in observable_eval.groupby("partition", sort=True):
        sample_ids = part["sample_id"].astype("string").tolist()
        truth = part["_y"].astype(int).to_numpy()
        entities = part["entity_id"].astype("string").to_numpy()
        scores = {
            "global_train_prior": np.full(len(part), global_prior),
            "line_train_prior": np.asarray([float(line_priors.get(entity, global_prior)) for entity in entities]),
            "sensor_only": part["_sensor_score"].astype(float).to_numpy(),
        }
        full_partition_ids = evaluation_parts.loc[
            evaluation_parts["partition"].astype("string").eq(str(partition)), "sample_id"
        ].astype("string").tolist()
        eval_positions = pd.Index(full_partition_ids).get_indexer(sample_ids)
        if (eval_positions < 0).any():
            raise ValueError("Observable comparison IDs do not align to their evaluation feature block.")
        partition_features = preprocessing["evaluation_features"][str(partition)][eval_positions]
        partition_entities = _one_hot_entities(entities, categories)
        line_sensor_probabilities = estimator.predict_proba(np.column_stack([partition_features, partition_entities]))[:, 1]
        scores["line_plus_sensors"] = line_sensor_probabilities
        for arm, probability in scores.items():
            predicted = (probability >= 0.5).astype(int)
            metrics = binary_metrics(truth, predicted, probability)
            sensor_count = 0 if arm in {"global_train_prior", "line_train_prior"} else len(feature_columns)
            uses_entity = arm in {"line_train_prior", "line_plus_sensors"}
            model_dimension = {
                "global_train_prior": 0,
                "line_train_prior": 0,
                "sensor_only": len(preprocessing["selected_feature_names"]),
                "line_plus_sensors": len(preprocessing["selected_feature_names"]) + len(categories),
            }[arm]
            for sample_id, entity, y_value, score, prediction in zip(sample_ids, entities, truth, probability, predicted, strict=True):
                rows.append({
                    "fold_id": str(fold_id),
                    "partition": str(partition),
                    "sample_id": sample_id,
                    "entity_id": str(entity),
                    "target": config.target_column,
                    "arm": arm,
                    "sensor_feature_count": sensor_count,
                    "group_context_columns": "line" if uses_entity else "",
                    "group_context_count": int(uses_entity),
                    "transformed_model_dimension": model_dimension,
                    "uses_entity_identity": uses_entity,
                    "y_true": int(y_value),
                    "positive_probability": float(score),
                    "y_pred": int(prediction),
                    "probability_threshold": 0.5,
                    "metric_evaluation_count": metrics["sample_count"],
                    "positive_prevalence": metrics["positive_prevalence"],
                    "balanced_accuracy": metrics["supported_class_balanced_accuracy"],
                    "f1_positive": metrics["f1_positive"],
                    "roc_auc": metrics["roc_auc"],
                    "average_precision": metrics["average_precision"],
                    "brier_score": metrics["brier_score"],
                    "log_loss": metrics["log_loss"],
                })
    prediction_frame = pd.DataFrame(rows).convert_dtypes()
    predictions_path = model_dir / "control_predictions.csv"
    prediction_frame.to_csv(predictions_path, index=False)
    metric_columns = [
        "fold_id", "partition", "target", "arm", "metric_evaluation_count", "positive_prevalence",
        "balanced_accuracy", "f1_positive", "roc_auc", "average_precision", "brier_score", "log_loss",
        "sensor_feature_count", "group_context_columns", "group_context_count",
        "transformed_model_dimension", "uses_entity_identity",
    ]
    metrics = prediction_frame.loc[:, metric_columns].drop_duplicates().sort_values(["partition", "arm"])
    contrast_rows: list[dict[str, object]] = []
    if "timestamp" in source.columns:
        for partition in ("validation", "test"):
            point, low, high, cluster_count = _paired_day_log_loss_contrast(
                prediction_frame.loc[prediction_frame["partition"].astype("string").eq(partition)],
                source,
                baseline_arm="line_train_prior",
                augmented_arm="line_plus_sensors",
                repetitions=1000,
                seed=config.random_seed,
            )
            contrast_rows.append({
                "fold_id": str(fold_id),
                "partition": partition,
                "target": config.target_column,
                "baseline_arm": "line_train_prior",
                "augmented_arm": "line_plus_sensors",
                "delta_log_loss_baseline_minus_augmented": point,
                "delta_log_loss_ci_low": low,
                "delta_log_loss_ci_high": high,
                "cluster_count": cluster_count,
                "bootstrap_repetitions": 1000,
                "bootstrap_unit": "UTC calendar day",
            })
    metrics_path = model_dir / "control_metrics.csv"
    metrics.to_csv(metrics_path, index=False)
    contrasts_path = model_dir / "control_contrasts.csv"
    pd.DataFrame(contrast_rows).to_csv(contrasts_path, index=False)
    manifest = {
        "schema_version": 1,
        "status": "complete",
        "target": config.target_column,
        "fold_id": str(fold_id),
        "arms": ["global_train_prior", "line_train_prior", "sensor_only", "line_plus_sensors"],
        "comparison_population": "target_known AND any selected sensor feature observable; identical sample IDs for every arm",
        "train_population_count": int(len(fit_rows)),
        "train_no_x_excluded_count": int((train["_y"].notna() & ~train["_x_observable"]).sum()),
        "train_unknown_excluded_count": int(train["_y"].isna().sum()),
        "validation_test_comparison_count": int(len(observable_eval)),
        "global_train_prior": global_prior,
        "line_train_priors": {str(key): float(value) for key, value in line_priors.items()},
        "unknown_entity_prior_fallback": "global_train_prior",
        "model_key": profile.model_key,
        "model_hyperparameters": profile.hyperparameters,
        "balanced_sample_weight": False,
        "random_seed": config.random_seed,
        "thread_count": config.thread_count,
        "model_library_version": library_version,
        "audit_manifest_path": str((config.audit_dir / "audit_manifest.json").resolve()),
        "audit_manifest_sha256": sha256_file(config.audit_dir / "audit_manifest.json"),
        "sensor_predictions_path": str(config.sensor_predictions_path.resolve()),
        "sensor_predictions_sha256": sha256_file(config.sensor_predictions_path),
        "training_sample_hash": hash_sample_ids(train_ids),
        "artifacts": {
            "line_plus_sensors_model": {"path": model_path.name, "sha256": sha256_file(model_path)},
            "predictions": {"path": predictions_path.name, "sha256": sha256_file(predictions_path)},
            "metrics": {"path": metrics_path.name, "sha256": sha256_file(metrics_path)},
            "contrasts": {"path": contrasts_path.name, "sha256": sha256_file(contrasts_path)},
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (model_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    catalog = [
        {"path": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for path in (model_path, predictions_path, metrics_path, contrasts_path, model_dir / "run_manifest.json")
    ]
    (model_dir / "artifact_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return model_dir


def _one_hot_entities(entities: np.ndarray, categories: list[str]) -> np.ndarray:
    values = np.asarray(entities, dtype=str)
    return np.column_stack([values == category for category in categories]).astype(float)


def _paired_day_log_loss_contrast(
    partition_predictions: pd.DataFrame,
    source: pd.DataFrame,
    *,
    baseline_arm: str,
    augmented_arm: str,
    repetitions: int,
    seed: int,
) -> tuple[float, float, float, int]:
    scores = partition_predictions.pivot(index="sample_id", columns="arm", values="positive_probability")
    truth = partition_predictions.drop_duplicates("sample_id").set_index("sample_id")["y_true"]
    needed = {baseline_arm, augmented_arm}
    if not needed.issubset(scores.columns):
        raise ValueError("Paired control predictions are missing a required arm.")
    scored = scores.loc[:, [baseline_arm, augmented_arm]].join(truth).join(
        source.set_index("sample_id")["timestamp"], how="left"
    ).dropna()
    if scored.empty or scored["timestamp"].isna().any():
        raise ValueError("Paired control rows do not resolve to timestamped source outcomes.")
    y = scored["y_true"].astype(int).to_numpy()
    p_baseline = np.clip(scored[baseline_arm].astype(float).to_numpy(), 1e-15, 1 - 1e-15)
    p_augmented = np.clip(scored[augmented_arm].astype(float).to_numpy(), 1e-15, 1 - 1e-15)
    loss_baseline = -np.where(y == 1, np.log(p_baseline), np.log1p(-p_baseline))
    loss_augmented = -np.where(y == 1, np.log(p_augmented), np.log1p(-p_augmented))
    delta = loss_baseline - loss_augmented
    days = pd.to_datetime(scored["timestamp"], utc=True).dt.floor("D").astype("string").to_numpy()
    groups = [np.flatnonzero(days == day) for day in sorted(set(days))]
    if len(groups) < 2:
        return float(delta.mean()), float("nan"), float("nan"), len(groups)
    rng = np.random.default_rng(seed)
    draws = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        selected = rng.integers(0, len(groups), size=len(groups))
        sample = np.concatenate([groups[position] for position in selected])
        draws[index] = delta[sample].mean()
    return (
        float(delta.mean()),
        float(np.percentile(draws, 2.5)),
        float(np.percentile(draws, 97.5)),
        len(groups),
    )
