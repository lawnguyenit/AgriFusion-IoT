from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.utils.class_weight import compute_sample_weight

from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification

try:
    import xgboost as xgb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    xgb = None

try:
    import lightgbm as lgb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    lgb = None


@dataclass
class SklearnModelResult:
    model_name: str
    artifact_path: Path
    metrics: dict[str, object]
    available: bool = True
    notes: str = ""


def _fit_and_score(
    model_name: str,
    model: Any,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    class_names: list[str],
    feature_names: list[str],
    artifact_path: Path,
) -> SklearnModelResult:
    train_frame = pd.DataFrame(train_features, columns=feature_names)
    validation_frame = pd.DataFrame(validation_features, columns=feature_names)
    test_frame = pd.DataFrame(test_features, columns=feature_names)
    sample_weight = compute_sample_weight(class_weight="balanced", y=train_labels)
    try:
        model.fit(train_frame, train_labels, sample_weight=sample_weight)
    except TypeError:
        model.fit(train_frame, train_labels)

    validation_predictions = model.predict(validation_frame)
    test_predictions = model.predict(test_frame)
    validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)
    test_metrics = summarize_classification(test_labels, test_predictions, class_names)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_path)
    return SklearnModelResult(
        model_name=model_name,
        artifact_path=artifact_path,
        metrics={
            "validation": validation_metrics,
            "test": test_metrics,
        },
    )


def train_model_suite(
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
) -> list[SklearnModelResult]:
    results: list[SklearnModelResult] = []
    available_label_count = len(class_names)

    candidates: dict[str, tuple[Any, bool, str]] = {
        "linear_probe": (
            LogisticRegression(max_iter=2000, random_state=seed),
            True,
            "Logistic regression probe on embedding.",
        ),
        "random_forest": (
            RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1),
            True,
            "Random forest on embedding.",
        ),
        "hist_gradient_boosting": (
            HistGradientBoostingClassifier(random_state=seed, max_depth=6, learning_rate=0.05),
            True,
            "Histogram gradient boosting on embedding.",
        ),
    }

    if xgb is not None:
        xgb_kwargs = {
            "n_estimators": 250,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "reg_lambda": 1.0,
            "objective": "multi:softprob" if available_label_count > 2 else "binary:logistic",
            "random_state": seed,
            "eval_metric": "mlogloss" if available_label_count > 2 else "logloss",
        }
        if available_label_count > 2:
            xgb_kwargs["num_class"] = available_label_count
        candidates["xgboost"] = (
            xgb.XGBClassifier(**xgb_kwargs),
            True,
            "Optional XGBoost model.",
        )

    if lgb is not None:
        lgb_kwargs = {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": -1,
            "random_state": seed,
            "objective": "multiclass" if available_label_count > 2 else "binary",
        }
        if available_label_count > 2:
            lgb_kwargs["num_class"] = available_label_count
        candidates["lightgbm"] = (
            lgb.LGBMClassifier(**lgb_kwargs),
            True,
            "Optional LightGBM model.",
        )

    for model_name in model_names:
        if model_name == "torch_probe":
            continue
        candidate = candidates.get(model_name)
        if candidate is None:
            results.append(
                SklearnModelResult(
                    model_name=model_name,
                    artifact_path=output_dir / "models" / f"{model_name}.joblib",
                    metrics={},
                    available=False,
                    notes="Model not configured in the suite.",
                )
            )
            continue
        model, available, notes = candidate
        if not available:
            results.append(
                SklearnModelResult(
                    model_name=model_name,
                    artifact_path=output_dir / "models" / f"{model_name}.joblib",
                    metrics={},
                    available=False,
                    notes=notes,
                )
            )
            continue
        result = _fit_and_score(
            model_name=model_name,
            model=model,
            train_features=train_features,
            train_labels=train_labels,
            validation_features=validation_features,
            validation_labels=validation_labels,
            test_features=test_features,
            test_labels=test_labels,
            class_names=class_names,
            feature_names=feature_names,
            artifact_path=output_dir / "models" / f"{model_name}.joblib",
        )
        result.notes = notes
        results.append(result)

    return results
