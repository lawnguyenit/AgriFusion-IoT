from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn import __version__ as sklearn_version
from sklearn.utils.class_weight import compute_sample_weight

from Backend.Benchmark.model_suite.contracts import ModelProfile, TabularTrainingResult
from Backend.Benchmark.model_suite.registries import build_estimator
from Backend.Benchmark.model_suite.utils.output_control import capture_python_output
from Backend.Benchmark.model_suite.utils.preprocessing import fit_preprocessing_bundle, hash_sample_ids


def train_tabular_classifier(
    *,
    profile: ModelProfile,
    train_features: np.ndarray,
    evaluation_features: dict[str, np.ndarray],
    train_labels: pd.Series,
    allowed_feature_columns: list[str],
    train_sample_ids: list[str],
    output_dir: Path,
    random_seed: int,
    thread_count: int,
    task_metadata: dict[str, object] | None = None,
) -> TabularTrainingResult:
    class_names = sorted(train_labels.astype("string").dropna().unique().tolist())
    class_lookup = {label_name: index for index, label_name in enumerate(class_names)}
    preprocessing_bundle = fit_preprocessing_bundle(
        train_features=train_features,
        evaluation_features=evaluation_features,
        feature_names=allowed_feature_columns,
        enable_scaling=profile.enable_scaling,
        enable_variance_threshold=profile.enable_variance_threshold,
    )
    selected_feature_names = preprocessing_bundle["selected_feature_names"]
    if not selected_feature_names:
        raise ValueError("zero_selected_features")

    estimator, model_library_version = build_estimator(
        profile=profile,
        random_seed=random_seed,
        thread_count=thread_count,
        class_count=len(class_names),
    )
    y_train = train_labels.map(class_lookup).to_numpy(dtype=np.int64)
    train_selected = preprocessing_bundle["train_features"]
    output_dir.mkdir(parents=True, exist_ok=True)
    console_log_path = output_dir / "training_console.log"
    evaluation_predictions: dict[str, list[int]] = {}
    evaluation_probabilities: dict[str, list[list[float]] | None] = {}
    transformed_evaluation_features = preprocessing_bundle["evaluation_features"]
    with capture_python_output(console_log_path):
        if profile.use_balanced_sample_weight:
            sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
            estimator.fit(train_selected, y_train, sample_weight=sample_weight)
        else:
            estimator.fit(train_selected, y_train)
        for partition_name, features in transformed_evaluation_features.items():
            predictions = estimator.predict(features)
            probabilities = _normalize_prediction_probabilities(estimator.predict_proba(features))
            evaluation_predictions[partition_name] = [int(value) for value in predictions.tolist()]
            evaluation_probabilities[partition_name] = probabilities

    train_sample_hash = hash_sample_ids(train_sample_ids)
    preprocessing_metadata = {
        "imputer_fit_sample_hash": train_sample_hash,
        "scaler_fit_sample_hash": train_sample_hash,
        "selector_fit_sample_hash": train_sample_hash,
        "model_fit_sample_hash": train_sample_hash,
        "random_seed": random_seed,
        "thread_count": thread_count,
        "selected_feature_count": int(len(selected_feature_names)),
        "selected_feature_names": selected_feature_names,
        "use_balanced_sample_weight": bool(profile.use_balanced_sample_weight),
        "preprocessing_library_version": sklearn_version,
        "semantic_arm_id": (task_metadata or {}).get("semantic_arm_id"),
        "feature_list_hash": (task_metadata or {}).get("feature_list_hash"),
        "source_feature_artifact_hash": (task_metadata or {}).get("source_feature_artifact_hash"),
    }
    model_metadata = {
        "model_key": profile.model_key,
        "display_name": profile.display_name,
        "family": profile.family,
        "library": profile.library,
        "hyperparameters": profile.hyperparameters,
        "class_names": class_names,
        "model_library_version": model_library_version,
        "preprocessing_library_version": sklearn_version,
        "task_metadata": task_metadata or {},
    }
    model_bundle = {
        "model": estimator,
        "imputer": preprocessing_bundle["imputer"],
        "scaler": preprocessing_bundle["scaler"],
        "selector": preprocessing_bundle["selector"],
        "class_names": class_names,
        "selected_feature_names": selected_feature_names,
        "model_profile": model_metadata,
        "preprocessing_metadata": preprocessing_metadata,
    }
    model_path = output_dir / f"{profile.model_key}.joblib"
    bundle_path = output_dir / "model_bundle.joblib"
    preprocessing_path = output_dir / "preprocessing_metadata.json"
    manifest_path = output_dir / "model_manifest.json"
    joblib.dump(estimator, model_path)
    joblib.dump(model_bundle, bundle_path)
    preprocessing_path.write_text(
        json.dumps(preprocessing_metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(model_metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return TabularTrainingResult(
        class_names=class_names,
        evaluation_predictions=evaluation_predictions,
        evaluation_probabilities=evaluation_probabilities,
        selected_feature_names=selected_feature_names,
        preprocessing_metadata=preprocessing_metadata,
        model_metadata=model_metadata,
        artifact_paths={
            "model_path": str(model_path),
            "bundle_path": str(bundle_path),
            "preprocessing_metadata_path": str(preprocessing_path),
            "model_manifest_path": str(manifest_path),
            "training_console_log_path": str(console_log_path),
        },
        output_dir=output_dir,
    )


def _normalize_prediction_probabilities(probabilities: np.ndarray | None) -> list[list[float]] | None:
    if probabilities is None:
        return None
    if probabilities.ndim == 1:
        return [[float(value)] for value in probabilities.tolist()]
    return [[float(value) for value in row] for row in probabilities.tolist()]
