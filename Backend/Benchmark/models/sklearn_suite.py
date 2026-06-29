from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.utils.class_weight import compute_sample_weight

from Backend.Benchmark.shared.metrics import summarize_classification

try:
    import xgboost as xgb  # type: ignore
    XGBOOST_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    xgb = None
    XGBOOST_IMPORT_ERROR = exc


@dataclass
class SklearnModelResult:
    model_name: str
    artifact_path: Path
    metrics: dict[str, object]
    available: bool = True
    notes: str = ""


def train_model_suite(
    *,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    class_names: list[str],
    feature_names: list[str],
    output_dir: Path,
    seed: int,
    model_names: list[str],
    progress_prefix: str | None = None,
) -> list[SklearnModelResult]:
    results: list[SklearnModelResult] = []
    for model_name in model_names:
        if model_name != "xgboost":
            results.append(
                SklearnModelResult(
                    model_name=model_name,
                    artifact_path=output_dir / "models" / f"{model_name}.joblib",
                    metrics={},
                    available=False,
                    notes="Model not configured in the unified 3-model suite.",
                )
            )
            continue
        if xgb is None:
            notes = (
                "XGBoost import failed."
                if XGBOOST_IMPORT_ERROR is None
                else f"XGBoost import failed: {type(XGBOOST_IMPORT_ERROR).__name__}: {XGBOOST_IMPORT_ERROR}"
            )
            results.append(
                SklearnModelResult(
                    model_name=model_name,
                    artifact_path=output_dir / "models" / "xgboost.joblib",
                    metrics={},
                    available=False,
                    notes=notes,
                )
            )
            continue
        results.append(
            _fit_and_score_xgboost(
                train_features=train_features,
                train_labels=train_labels,
                validation_features=validation_features,
                validation_labels=validation_labels,
                test_features=test_features,
                test_labels=test_labels,
                class_names=class_names,
                feature_names=feature_names,
                artifact_path=output_dir / "models" / "xgboost.joblib",
                seed=seed,
                progress_prefix=progress_prefix,
            )
        )
    return results


def _fit_and_score_xgboost(
    *,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    class_names: list[str],
    feature_names: list[str],
    artifact_path: Path,
    seed: int,
    progress_prefix: str | None,
) -> SklearnModelResult:
    if xgb is None:
        raise RuntimeError("XGBoost is not available.")
    train_frame = pd.DataFrame(train_features, columns=feature_names)
    validation_frame = pd.DataFrame(validation_features, columns=feature_names)
    test_frame = pd.DataFrame(test_features, columns=feature_names)
    sample_weight = compute_sample_weight(class_weight="balanced", y=train_labels)
    label_count = len(class_names)
    kwargs: dict[str, Any] = {
        "n_estimators": 250,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "reg_lambda": 1.0,
        "objective": "multi:softprob" if label_count > 2 else "binary:logistic",
        "random_state": seed,
        "eval_metric": "mlogloss" if label_count > 2 else "logloss",
    }
    if label_count > 2:
        kwargs["num_class"] = label_count
    model = xgb.XGBClassifier(**kwargs)
    if progress_prefix:
        print(f"[{progress_prefix}] fitting xgboost...")
    try:
        model.fit(train_frame, train_labels, sample_weight=sample_weight)
    except TypeError:
        model.fit(train_frame, train_labels)

    validation_predictions = model.predict(validation_frame)
    test_predictions = model.predict(test_frame)
    validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)
    test_metrics = summarize_classification(test_labels, test_predictions, class_names)
    if progress_prefix:
        print(
            f"[{progress_prefix}] completed xgboost: "
            f"val_macro_f1={validation_metrics['macro_f1']:.4f}, "
            f"test_macro_f1={test_metrics['macro_f1']:.4f}"
        )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_path)
    return SklearnModelResult(
        model_name="xgboost",
        artifact_path=artifact_path,
        metrics={"validation": validation_metrics, "test": test_metrics},
        notes="Unified XGBoost control arm.",
    )
